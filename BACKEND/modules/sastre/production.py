"""
SASTRE Production Hardening Module

Provides:
- Structured logging with correlation IDs
- Retry logic with exponential backoff
- Circuit breaker for external services
- Input validation
- Timeouts
- Health checks
- Metrics collection
"""

import os
import sys
import json
import time
import uuid
import asyncio
import logging
import functools
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable, TypeVar, Awaitable
from dataclasses import dataclass, field, asdict
from enum import Enum
from contextlib import asynccontextmanager

# =============================================================================
# STRUCTURED LOGGING
# =============================================================================

class JSONFormatter(logging.Formatter):
    """JSON log formatter for production."""
    
    def format(self, record):
        log_obj = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add extra fields
        if hasattr(record, "correlation_id"):
            log_obj["correlation_id"] = record.correlation_id
        if hasattr(record, "agent"):
            log_obj["agent"] = record.agent
        if hasattr(record, "tool"):
            log_obj["tool"] = record.tool
        if hasattr(record, "duration_ms"):
            log_obj["duration_ms"] = record.duration_ms
        if hasattr(record, "error"):
            log_obj["error"] = record.error
            
        return json.dumps(log_obj)


def setup_production_logging(level: str = "INFO"):
    """Configure production logging."""
    logger = logging.getLogger("sastre")
    logger.setLevel(getattr(logging, level.upper()))
    
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)
    
    return logger


# Global logger
logger = setup_production_logging(os.getenv("SASTRE_LOG_LEVEL", "INFO"))


# =============================================================================
# CORRELATION CONTEXT
# =============================================================================

class CorrelationContext:
    """Thread-local correlation ID for request tracing."""
    _context: Dict[str, str] = {}
    
    @classmethod
    def set_id(cls, correlation_id: str = None):
        cls._context["id"] = correlation_id or str(uuid.uuid4())[:8]
        
    @classmethod
    def get_id(cls) -> str:
        return cls._context.get("id", "no-corr")
    
    @classmethod
    def clear(cls):
        cls._context.clear()


# =============================================================================
# RETRY LOGIC
# =============================================================================

@dataclass
class RetryConfig:
    """Retry configuration."""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0
    retryable_exceptions: tuple = (asyncio.TimeoutError, ConnectionError, OSError)


async def retry_async(
    func: Callable[..., Awaitable],
    *args,
    config: RetryConfig = None,
    **kwargs
) -> Any:
    """Execute async function with retry logic."""
    config = config or RetryConfig()
    last_exception = None
    
    for attempt in range(1, config.max_attempts + 1):
        try:
            return await func(*args, **kwargs)
        except config.retryable_exceptions as e:
            last_exception = e
            if attempt < config.max_attempts:
                delay = min(
                    config.base_delay * (config.exponential_base ** (attempt - 1)),
                    config.max_delay
                )
                logger.warning(
                    f"Retry {attempt}/{config.max_attempts} after {delay:.1f}s",
                    extra={
                        "correlation_id": CorrelationContext.get_id(),
                        "error": str(e)
                    }
                )
                await asyncio.sleep(delay)
            else:
                raise
    
    raise last_exception


def with_retry(config: RetryConfig = None):
    """Decorator for async functions with retry."""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            return await retry_async(func, *args, config=config, **kwargs)
        return wrapper
    return decorator


# =============================================================================
# CIRCUIT BREAKER
# =============================================================================

class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open" # Testing if recovered


@dataclass
class CircuitBreaker:
    """Circuit breaker for external services."""
    name: str
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 3
    
    state: CircuitState = field(default=CircuitState.CLOSED)
    failure_count: int = 0
    last_failure_time: float = 0
    half_open_calls: int = 0
    
    def can_execute(self) -> bool:
        """Check if request can proceed."""
        if self.state == CircuitState.CLOSED:
            return True
        
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                return True
            return False
        
        if self.state == CircuitState.HALF_OPEN:
            return self.half_open_calls < self.half_open_max_calls
        
        return False
    
    def record_success(self):
        """Record successful call."""
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_calls += 1
            if self.half_open_calls >= self.half_open_max_calls:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                logger.info(f"Circuit {self.name} CLOSED (recovered)")
        else:
            self.failure_count = 0
    
    def record_failure(self):
        """Record failed call."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            logger.warning(f"Circuit {self.name} OPEN (half-open failed)")
        elif self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(f"Circuit {self.name} OPEN (threshold reached)")


# Global circuit breakers
_circuit_breakers: Dict[str, CircuitBreaker] = {}


def get_circuit_breaker(name: str) -> CircuitBreaker:
    """Get or create circuit breaker."""
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(name=name)
    return _circuit_breakers[name]


# =============================================================================
# INPUT VALIDATION
# =============================================================================

class ValidationError(Exception):
    """Input validation error."""
    pass


def validate_string(value: Any, name: str, min_len: int = 1, max_len: int = 10000) -> str:
    """Validate string input."""
    if value is None:
        raise ValidationError(f"{name} is required")
    val = str(value).strip()
    if len(val) < min_len:
        raise ValidationError(f"{name} must be at least {min_len} characters")
    if len(val) > max_len:
        raise ValidationError(f"{name} must be at most {max_len} characters")
    return val


def validate_enum(value: Any, name: str, allowed: List[str]) -> str:
    """Validate enum input."""
    val = str(value).strip().lower()
    if val not in [a.lower() for a in allowed]:
        raise ValidationError(f"{name} must be one of: {allowed}")
    return val


def validate_project_id(value: Any) -> str:
    """Validate project ID."""
    val = validate_string(value, "project_id", min_len=1, max_len=100)
    # Allow alphanumeric, dash, underscore
    import re
    if not re.match(r"^[a-zA-Z0-9_-]+$", val):
        raise ValidationError("project_id must be alphanumeric with dash/underscore")
    return val


# =============================================================================
# TIMEOUT WRAPPER
# =============================================================================

DEFAULT_TIMEOUT = float(os.getenv("SASTRE_DEFAULT_TIMEOUT", "60"))


async def with_timeout(coro, timeout: float = None, name: str = "operation"):
    """Execute coroutine with timeout."""
    timeout = timeout or DEFAULT_TIMEOUT
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.error(
            f"{name} timed out after {timeout}s",
            extra={"correlation_id": CorrelationContext.get_id()}
        )
        raise


# =============================================================================
# METRICS COLLECTION
# =============================================================================

@dataclass
class ToolMetrics:
    """Metrics for a single tool."""
    name: str
    total_calls: int = 0
    success_count: int = 0
    error_count: int = 0
    total_duration_ms: float = 0
    
    @property
    def avg_duration_ms(self) -> float:
        return self.total_duration_ms / max(self.total_calls, 1)
    
    @property
    def success_rate(self) -> float:
        return self.success_count / max(self.total_calls, 1)


class MetricsCollector:
    """Collects metrics for all tools."""
    
    def __init__(self):
        self._metrics: Dict[str, ToolMetrics] = {}
        self._start_time = time.time()
    
    def record(self, tool: str, duration_ms: float, success: bool):
        """Record a tool execution."""
        if tool not in self._metrics:
            self._metrics[tool] = ToolMetrics(name=tool)
        
        m = self._metrics[tool]
        m.total_calls += 1
        m.total_duration_ms += duration_ms
        if success:
            m.success_count += 1
        else:
            m.error_count += 1
    
    def get_all(self) -> Dict[str, Dict]:
        """Get all metrics."""
        return {
            name: asdict(m) for name, m in self._metrics.items()
        }
    
    def get_summary(self) -> Dict:
        """Get summary metrics."""
        total_calls = sum(m.total_calls for m in self._metrics.values())
        total_errors = sum(m.error_count for m in self._metrics.values())
        return {
            "uptime_seconds": time.time() - self._start_time,
            "total_tool_calls": total_calls,
            "total_errors": total_errors,
            "error_rate": total_errors / max(total_calls, 1),
            "tools": len(self._metrics),
        }


# Global metrics
metrics = MetricsCollector()


# =============================================================================
# PRODUCTION TOOL WRAPPER
# =============================================================================

def production_tool(
    timeout: float = None,
    retry_config: RetryConfig = None,
    circuit_breaker: str = None,
    validate_inputs: Callable = None,
):
    """
    Decorator to make a tool production-ready.
    
    Adds:
    - Correlation ID tracking
    - Structured logging
    - Input validation
    - Timeout
    - Retry logic
    - Circuit breaker
    - Metrics collection
    """
    def decorator(func):
        tool_name = func.__name__
        
        @functools.wraps(func)
        async def wrapper(args: Dict[str, Any]) -> Dict[str, Any]:
            # Set correlation ID if not set
            if not CorrelationContext.get_id() or CorrelationContext.get_id() == "no-corr":
                CorrelationContext.set_id()
            
            corr_id = CorrelationContext.get_id()
            start_time = time.time()
            
            logger.info(
                f"Tool {tool_name} started",
                extra={
                    "correlation_id": corr_id,
                    "tool": tool_name,
                    "args": {k: str(v)[:100] for k, v in args.items()}
                }
            )
            
            try:
                # Input validation
                if validate_inputs:
                    args = validate_inputs(args)
                
                # Circuit breaker check
                if circuit_breaker:
                    cb = get_circuit_breaker(circuit_breaker)
                    if not cb.can_execute():
                        raise Exception(f"Circuit {circuit_breaker} is OPEN")
                
                # Execute with timeout and retry
                coro = func(args)
                if retry_config:
                    result = await retry_async(
                        with_timeout, coro, timeout=timeout, name=tool_name,
                        config=retry_config
                    )
                else:
                    result = await with_timeout(coro, timeout=timeout, name=tool_name)
                
                # Record success
                duration_ms = (time.time() - start_time) * 1000
                metrics.record(tool_name, duration_ms, success=True)
                
                if circuit_breaker:
                    get_circuit_breaker(circuit_breaker).record_success()
                
                logger.info(
                    f"Tool {tool_name} completed",
                    extra={
                        "correlation_id": corr_id,
                        "tool": tool_name,
                        "duration_ms": duration_ms
                    }
                )
                
                return result
                
            except Exception as e:
                duration_ms = (time.time() - start_time) * 1000
                metrics.record(tool_name, duration_ms, success=False)
                
                if circuit_breaker:
                    get_circuit_breaker(circuit_breaker).record_failure()
                
                logger.error(
                    f"Tool {tool_name} failed: {e}",
                    extra={
                        "correlation_id": corr_id,
                        "tool": tool_name,
                        "duration_ms": duration_ms,
                        "error": str(e)
                    }
                )
                
                return {
                    "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                    "is_error": True
                }
        
        return wrapper
    return decorator


# =============================================================================
# HEALTH CHECK
# =============================================================================

@dataclass
class HealthStatus:
    """Health check status."""
    healthy: bool
    checks: Dict[str, bool] = field(default_factory=dict)
    details: Dict[str, str] = field(default_factory=dict)


async def check_health() -> HealthStatus:
    """Run health checks."""
    status = HealthStatus(healthy=True)
    
    # Check SDK imports
    try:
        from SASTRE import sdk
        status.checks["sdk_import"] = True
    except Exception as e:
        status.checks["sdk_import"] = False
        status.details["sdk_import"] = str(e)
        status.healthy = False
    
    # Check circuit breakers
    open_circuits = [name for name, cb in _circuit_breakers.items() if cb.state == CircuitState.OPEN]
    if open_circuits:
        status.checks["circuits"] = False
        status.details["circuits"] = f"Open: {open_circuits}"
        status.healthy = False
    else:
        status.checks["circuits"] = True
    
    # Check metrics
    summary = metrics.get_summary()
    if summary["error_rate"] > 0.5:
        status.checks["error_rate"] = False
        status.details["error_rate"] = f"{summary['error_rate']:.1%} errors"
        status.healthy = False
    else:
        status.checks["error_rate"] = True
    
    return status


# =============================================================================
# PRODUCTION CONFIG
# =============================================================================

@dataclass
class ProductionConfig:
    """Production configuration with validation."""
    
    # API Keys (required)
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    
    # Timeouts
    default_timeout: float = field(default_factory=lambda: float(os.getenv("SASTRE_DEFAULT_TIMEOUT", "60")))
    tool_timeout: float = field(default_factory=lambda: float(os.getenv("SASTRE_TOOL_TIMEOUT", "120")))
    
    # Retry
    max_retries: int = field(default_factory=lambda: int(os.getenv("SASTRE_MAX_RETRIES", "3")))
    retry_base_delay: float = field(default_factory=lambda: float(os.getenv("SASTRE_RETRY_DELAY", "1.0")))
    
    # Circuit breaker
    circuit_failure_threshold: int = field(default_factory=lambda: int(os.getenv("SASTRE_CIRCUIT_THRESHOLD", "5")))
    circuit_recovery_timeout: float = field(default_factory=lambda: float(os.getenv("SASTRE_CIRCUIT_RECOVERY", "30")))
    
    # Logging
    log_level: str = field(default_factory=lambda: os.getenv("SASTRE_LOG_LEVEL", "INFO"))
    
    # External services
    node_api_url: str = field(default_factory=lambda: os.getenv("NODE_API_BASE_URL", "http://localhost:3000"))
    cymonides_api: str = field(default_factory=lambda: os.getenv("CYMONIDES_API", "http://localhost:3001/api/graph"))
    
    def validate(self) -> List[str]:
        """Validate config, return list of errors."""
        errors = []
        
        if not self.anthropic_api_key:
            errors.append("ANTHROPIC_API_KEY is required")
        
        if self.default_timeout <= 0:
            errors.append("default_timeout must be positive")
        
        if self.max_retries < 0:
            errors.append("max_retries must be non-negative")
        
        return errors
    
    def is_valid(self) -> bool:
        return len(self.validate()) == 0


# Global config
config = ProductionConfig()


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Logging
    "logger",
    "setup_production_logging",
    "CorrelationContext",
    
    # Retry
    "RetryConfig",
    "retry_async",
    "with_retry",
    
    # Circuit breaker
    "CircuitBreaker",
    "CircuitState",
    "get_circuit_breaker",
    
    # Validation
    "ValidationError",
    "validate_string",
    "validate_enum",
    "validate_project_id",
    
    # Timeout
    "with_timeout",
    "DEFAULT_TIMEOUT",
    
    # Metrics
    "metrics",
    "MetricsCollector",
    "ToolMetrics",
    
    # Production wrapper
    "production_tool",
    
    # Health
    "check_health",
    "HealthStatus",
    
    # Config
    "config",
    "ProductionConfig",
]


if __name__ == "__main__":
    # Quick test
    import asyncio
    
    async def test():
        print("Config valid:", config.is_valid())
        print("Config errors:", config.validate())
        
        health = await check_health()
        print("Health:", asdict(health))
        
        print("Metrics:", metrics.get_summary())
    
    asyncio.run(test())
