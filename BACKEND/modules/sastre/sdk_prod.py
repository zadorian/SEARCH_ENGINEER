"""
SASTRE SDK Production Wrapper

Imports the base SDK and wraps all tools with production hardening:
- Retries with exponential backoff
- Circuit breakers for external services
- Input validation
- Structured logging with correlation IDs
- Timeouts
- Metrics collection

Usage:
    from SASTRE.sdk_prod import SastreProductionAgent
    agent = SastreProductionAgent(config)
    await agent.run("query")
"""

import asyncio
import time
import logging
from typing import Dict, Any, Optional, Callable
from functools import wraps

# Import base SDK components
from . import sdk
from .sdk import (
    AGENT_CONFIGS,
    SastreAgent,
    AgentConfig,
    tool,
    create_sdk_mcp_server,
    # Tools
    execute_tool,
    assess_tool,
    query_lab_build_tool,
    get_watchers_tool,
    create_watcher_tool,
    stream_finding_tool,
    resolve_tool,
    edith_rewrite_tool,
    edith_answer_tool,
    edith_edit_section_tool,
    edith_read_url_tool,
    edith_template_ops_tool,
    investigate_person_tool,
    investigate_company_tool,
    investigate_domain_tool,
    investigate_phone_tool,
    investigate_email_tool,
    torpedo_search_tool,
    torpedo_process_tool,
    torpedo_template_tool,
    nexus_brute_tool,
)

# Import production utilities
from .production import (
    production_tool,
    RetryConfig,
    logger,
    CorrelationContext,
    metrics,
    get_circuit_breaker,
    check_health,
    config as prod_config,
)

# Import validators
from .validators import VALIDATORS, ValidationError


# =============================================================================
# TOOL PRODUCTION CONFIGS
# =============================================================================

TOOL_CONFIGS = {
    "execute": {"timeout": 120.0, "circuit": "io_bridge"},
    "assess": {"timeout": 60.0, "circuit": "watcher_bridge"},
    "query_lab_build": {"timeout": 30.0, "circuit": None},
    "get_watchers": {"timeout": 30.0, "circuit": "watcher_bridge"},
    "create_watcher": {"timeout": 30.0, "circuit": "watcher_bridge"},
    "stream_finding": {"timeout": 60.0, "circuit": "watcher_bridge"},
    "resolve": {"timeout": 90.0, "circuit": "cymonides_bridge"},
    "edith_rewrite": {"timeout": 90.0, "circuit": "anthropic_api"},
    "edith_answer": {"timeout": 60.0, "circuit": "anthropic_api"},
    "edith_edit_section": {"timeout": 60.0, "circuit": "watcher_bridge"},
    "edith_read_url": {"timeout": 45.0, "circuit": None},
    "edith_template_ops": {"timeout": 30.0, "circuit": None},
    "investigate_person": {"timeout": 180.0, "circuit": "io_bridge"},
    "investigate_company": {"timeout": 180.0, "circuit": "io_bridge"},
    "investigate_domain": {"timeout": 180.0, "circuit": "io_bridge"},
    "investigate_phone": {"timeout": 120.0, "circuit": "io_bridge"},
    "investigate_email": {"timeout": 120.0, "circuit": "io_bridge"},
    "torpedo_search": {"timeout": 120.0, "circuit": "torpedo_bridge"},
    "torpedo_process": {"timeout": 90.0, "circuit": "torpedo_bridge"},
    "torpedo_template": {"timeout": 60.0, "circuit": None},
    "nexus_brute": {"timeout": 300.0, "circuit": "brute_search"},
}


def make_production_wrapper(tool_name: str, original_fn: Callable) -> Callable:
    """Wrap a tool function with production hardening."""
    
    config = TOOL_CONFIGS.get(tool_name, {"timeout": 60.0, "circuit": None})
    validator = VALIDATORS.get(tool_name)
    timeout = config["timeout"]
    circuit_name = config["circuit"]
    retry_config = RetryConfig(max_attempts=3, base_delay=1.0, max_delay=30.0)
    
    @wraps(original_fn)
    async def wrapper(args: Dict[str, Any]) -> Dict[str, Any]:
        corr_id = CorrelationContext.get_id()
        start_time = time.time()
        
        logger.info(
            f"Tool {tool_name} starting",
            extra={"correlation_id": corr_id, "tool": tool_name}
        )
        
        # Input validation
        if validator:
            try:
                args = validator(args)
            except ValidationError as e:
                logger.warning(
                    f"Tool {tool_name} validation failed: {e}",
                    extra={"correlation_id": corr_id, "tool": tool_name, "error": str(e)}
                )
                return {"content": [{"type": "text", "text": f"Validation error: {e}"}], "is_error": True}
        
        # Check circuit breaker
        if circuit_name:
            cb = get_circuit_breaker(circuit_name)
            if not cb.allow_request():
                logger.warning(
                    f"Tool {tool_name} circuit open for {circuit_name}",
                    extra={"correlation_id": corr_id, "tool": tool_name, "circuit": circuit_name}
                )
                return {"content": [{"type": "text", "text": f"Service {circuit_name} temporarily unavailable"}], "is_error": True}
        
        # Execute with retry
        last_error = None
        for attempt in range(retry_config.max_attempts):
            try:
                # Apply timeout
                result = await asyncio.wait_for(
                    original_fn(args),
                    timeout=timeout
                )
                
                # Record success
                duration_ms = (time.time() - start_time) * 1000
                metrics.record(tool_name, duration_ms, success=True)
                if circuit_name:
                    get_circuit_breaker(circuit_name).record_success()
                
                logger.info(
                    f"Tool {tool_name} completed",
                    extra={"correlation_id": corr_id, "tool": tool_name, "duration_ms": duration_ms}
                )
                return result
                
            except asyncio.TimeoutError:
                last_error = f"Timeout after {timeout}s"
                logger.warning(
                    f"Tool {tool_name} timeout (attempt {attempt + 1})",
                    extra={"correlation_id": corr_id, "tool": tool_name, "attempt": attempt + 1}
                )
                
            except (ConnectionError, OSError) as e:
                last_error = str(e)
                delay = min(
                    retry_config.base_delay * (retry_config.exponential_base ** attempt),
                    retry_config.max_delay
                )
                logger.warning(
                    f"Tool {tool_name} retrying in {delay}s (attempt {attempt + 1}): {e}",
                    extra={"correlation_id": corr_id, "tool": tool_name, "attempt": attempt + 1}
                )
                await asyncio.sleep(delay)
                
            except Exception as e:
                # Non-retryable error
                last_error = str(e)
                break
        
        # All retries failed
        duration_ms = (time.time() - start_time) * 1000
        metrics.record(tool_name, duration_ms, success=False)
        if circuit_name:
            get_circuit_breaker(circuit_name).record_failure()
        
        logger.error(
            f"Tool {tool_name} failed after retries: {last_error}",
            extra={"correlation_id": corr_id, "tool": tool_name, "duration_ms": duration_ms, "error": last_error}
        )
        
        return {"content": [{"type": "text", "text": f"Error: {last_error}"}], "is_error": True}
    
    return wrapper


# =============================================================================
# PRODUCTION TOOL REGISTRY
# =============================================================================

# Map tool names to their original functions
ORIGINAL_TOOLS = {
    "execute": execute_tool,
    "assess": assess_tool,
    "query_lab_build": query_lab_build_tool,
    "get_watchers": get_watchers_tool,
    "create_watcher": create_watcher_tool,
    "stream_finding": stream_finding_tool,
    "resolve": resolve_tool,
    "edith_rewrite": edith_rewrite_tool,
    "edith_answer": edith_answer_tool,
    "edith_edit_section": edith_edit_section_tool,
    "edith_read_url": edith_read_url_tool,
    "edith_template_ops": edith_template_ops_tool,
    "investigate_person": investigate_person_tool,
    "investigate_company": investigate_company_tool,
    "investigate_domain": investigate_domain_tool,
    "investigate_phone": investigate_phone_tool,
    "investigate_email": investigate_email_tool,
    "torpedo_search": torpedo_search_tool,
    "torpedo_process": torpedo_process_tool,
    "torpedo_template": torpedo_template_tool,
    "nexus_brute": nexus_brute_tool,
}

# Create production-wrapped versions
PRODUCTION_TOOLS = {
    name: make_production_wrapper(name, fn)
    for name, fn in ORIGINAL_TOOLS.items()
}


# =============================================================================
# PRODUCTION AGENT WRAPPER
# =============================================================================

class SastreProductionAgent:
    """Production-hardened SASTRE agent wrapper."""
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.base_agent = SastreAgent(config)
        
    async def run(self, prompt: str, correlation_id: str = None) -> str:
        """Run agent with production hardening."""
        # Set correlation ID for request tracing
        CorrelationContext.set_id(correlation_id)
        
        logger.info(
            f"Agent {self.config.name} starting",
            extra={"correlation_id": CorrelationContext.get_id(), "agent": self.config.name}
        )
        
        start_time = time.time()
        try:
            result = await self.base_agent.run(prompt)
            duration_ms = (time.time() - start_time) * 1000
            
            logger.info(
                f"Agent {self.config.name} completed",
                extra={
                    "correlation_id": CorrelationContext.get_id(),
                    "agent": self.config.name,
                    "duration_ms": duration_ms
                }
            )
            return result
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                f"Agent {self.config.name} failed: {e}",
                extra={
                    "correlation_id": CorrelationContext.get_id(),
                    "agent": self.config.name,
                    "duration_ms": duration_ms,
                    "error": str(e)
                }
            )
            raise
        finally:
            CorrelationContext.clear()


# =============================================================================
# HEALTH CHECK ENDPOINT
# =============================================================================

async def get_production_health() -> Dict[str, Any]:
    """Get production health status."""
    health = await check_health()
    return {
        "healthy": health.healthy,
        "checks": health.checks,
        "details": health.details,
        "metrics": metrics.get_summary(),
        "config_valid": prod_config.is_valid(),
        "config_errors": prod_config.validate(),
    }


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Production agent
    "SastreProductionAgent",
    
    # Production tools
    "PRODUCTION_TOOLS",
    "make_production_wrapper",
    
    # Health
    "get_production_health",
    
    # Utilities
    "CorrelationContext",
    "logger",
    "metrics",
]


if __name__ == "__main__":
    import asyncio
    
    async def test():
        print("Testing production SDK wrapper...")
        
        # Test health check
        health = await get_production_health()
        print(f"Health: {health}")
        
        # Test wrapped tool
        exec_wrapped = PRODUCTION_TOOLS["execute"]
        print(f"Wrapped execute tool: {exec_wrapped}")
        
        print("Production SDK wrapper OK")
    
    asyncio.run(test())
