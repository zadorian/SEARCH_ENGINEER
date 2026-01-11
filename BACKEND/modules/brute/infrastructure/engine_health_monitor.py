"""
Engine Health Monitoring and Circuit Breaker System
Prevents cascade failures and manages engine reliability
"""

import time
import threading
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class EngineStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    CIRCUIT_OPEN = "circuit_open"

@dataclass
class EngineMetrics:
    """Metrics for a single engine"""
    engine_code: str
    engine_name: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    timeout_requests: int = 0
    rate_limited_requests: int = 0
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    average_response_time: float = 0.0
    current_status: EngineStatus = EngineStatus.HEALTHY
    circuit_open_until: Optional[datetime] = None
    consecutive_failures: int = 0
    response_times: List[float] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage"""
        if self.total_requests == 0:
            return 100.0
        return (self.successful_requests / self.total_requests) * 100.0

    @property
    def failure_rate(self) -> float:
        """Calculate failure rate percentage"""
        return 100.0 - self.success_rate

    def update_response_time(self, response_time: float):
        """Update average response time with new measurement"""
        self.response_times.append(response_time)
        # Keep only last 100 measurements for efficiency
        if len(self.response_times) > 100:
            self.response_times = self.response_times[-100:]
        self.average_response_time = sum(self.response_times) / len(self.response_times)

class CircuitBreaker:
    """Circuit breaker for individual engines"""
    
    def __init__(self, engine_code: str, 
                 failure_threshold: int = 5,
                 timeout_threshold: int = 3,
                 recovery_timeout: int = 60,
                 min_requests: int = 10):
        self.engine_code = engine_code
        self.failure_threshold = failure_threshold
        self.timeout_threshold = timeout_threshold  
        self.recovery_timeout = recovery_timeout
        self.min_requests = min_requests
        self.lock = threading.Lock()

    def should_allow_request(self, metrics: EngineMetrics) -> bool:
        """Check if request should be allowed through circuit breaker"""
        with self.lock:
            # If circuit is open, check if recovery time has passed
            if metrics.current_status == EngineStatus.CIRCUIT_OPEN:
                if metrics.circuit_open_until and datetime.now() > metrics.circuit_open_until:
                    # Try to close circuit - move to half-open state
                    metrics.current_status = EngineStatus.DEGRADED
                    metrics.consecutive_failures = 0
                    logger.info(f"Circuit breaker for {self.engine_code} moving to half-open state")
                    return True
                return False

            # Allow requests if we haven't hit minimum request threshold
            if metrics.total_requests < self.min_requests:
                return True

            # Check consecutive failures
            if metrics.consecutive_failures >= self.failure_threshold:
                self._open_circuit(metrics)
                return False

            # Check timeout rate
            if metrics.total_requests > 0:
                timeout_rate = (metrics.timeout_requests / metrics.total_requests) * 100
                if timeout_rate > 50 and metrics.timeout_requests >= self.timeout_threshold:
                    self._open_circuit(metrics)
                    return False

            return True

    def _open_circuit(self, metrics: EngineMetrics):
        """Open the circuit breaker"""
        metrics.current_status = EngineStatus.CIRCUIT_OPEN
        metrics.circuit_open_until = datetime.now() + timedelta(seconds=self.recovery_timeout)
        logger.warning(f"Circuit breaker OPENED for {self.engine_code} - recovery in {self.recovery_timeout}s")

class EngineHealthMonitor:
    """Central health monitoring system for all engines"""
    
    def __init__(self):
        self.metrics: Dict[str, EngineMetrics] = {}
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.lock = threading.Lock()
        self.start_time = datetime.now()

    def register_engine(self, engine_code: str, engine_name: str):
        """Register a new engine for monitoring"""
        with self.lock:
            if engine_code not in self.metrics:
                self.metrics[engine_code] = EngineMetrics(
                    engine_code=engine_code,
                    engine_name=engine_name
                )
                self.circuit_breakers[engine_code] = CircuitBreaker(engine_code)
                logger.info(f"Registered engine for monitoring: {engine_code} ({engine_name})")

    def should_allow_request(self, engine_code: str) -> bool:
        """Check if a request should be allowed for this engine"""
        if engine_code not in self.metrics:
            return True  # Allow if not monitored
        
        metrics = self.metrics[engine_code]
        circuit_breaker = self.circuit_breakers[engine_code]
        return circuit_breaker.should_allow_request(metrics)

    def record_request_start(self, engine_code: str) -> float:
        """Record the start of a request and return start time"""
        with self.lock:
            if engine_code in self.metrics:
                self.metrics[engine_code].total_requests += 1
        return time.time()

    def record_request_success(self, engine_code: str, start_time: float, result_count: int = 0):
        """Record a successful request"""
        response_time = time.time() - start_time
        
        with self.lock:
            if engine_code in self.metrics:
                metrics = self.metrics[engine_code]
                metrics.successful_requests += 1
                metrics.last_success = datetime.now()
                metrics.consecutive_failures = 0  # Reset failure counter
                metrics.update_response_time(response_time)
                
                # Update status based on performance
                if metrics.current_status == EngineStatus.CIRCUIT_OPEN:
                    pass  # Keep circuit open until timeout
                elif metrics.success_rate >= 95:
                    metrics.current_status = EngineStatus.HEALTHY
                elif metrics.success_rate >= 80:
                    metrics.current_status = EngineStatus.DEGRADED
                else:
                    metrics.current_status = EngineStatus.DOWN

    def record_request_failure(self, engine_code: str, start_time: float, 
                             error_type: str = "unknown", error_msg: str = ""):
        """Record a failed request"""
        response_time = time.time() - start_time
        
        with self.lock:
            if engine_code in self.metrics:
                metrics = self.metrics[engine_code]
                metrics.failed_requests += 1
                metrics.last_failure = datetime.now()
                metrics.consecutive_failures += 1
                metrics.update_response_time(response_time)
                
                # Categorize failure types
                if "timeout" in error_type.lower() or "timed out" in error_msg.lower():
                    metrics.timeout_requests += 1
                elif "429" in error_msg or "rate limit" in error_msg.lower():
                    metrics.rate_limited_requests += 1

                # Update status
                if metrics.failure_rate > 50:
                    metrics.current_status = EngineStatus.DOWN
                elif metrics.failure_rate > 20:
                    metrics.current_status = EngineStatus.DEGRADED

    def get_engine_status(self, engine_code: str) -> EngineStatus:
        """Get current status of an engine"""
        if engine_code not in self.metrics:
            return EngineStatus.HEALTHY
        return self.metrics[engine_code].current_status

    def get_health_summary(self) -> Dict[str, Dict]:
        """Get health summary for all engines"""
        with self.lock:
            summary = {}
            for code, metrics in self.metrics.items():
                summary[code] = {
                    'name': metrics.engine_name,
                    'status': metrics.current_status.value,
                    'success_rate': f"{metrics.success_rate:.1f}%",
                    'total_requests': metrics.total_requests,
                    'avg_response_time': f"{metrics.average_response_time:.2f}s",
                    'consecutive_failures': metrics.consecutive_failures,
                    'last_success': metrics.last_success.strftime('%H:%M:%S') if metrics.last_success else 'Never',
                    'last_failure': metrics.last_failure.strftime('%H:%M:%S') if metrics.last_failure else 'Never'
                }
            return summary

    def print_health_dashboard(self):
        """Print a formatted health dashboard"""
        print("\n" + "="*80)
        print("🏥 ENGINE HEALTH DASHBOARD")
        print("="*80)
        
        summary = self.get_health_summary()
        if not summary:
            print("No engines registered for monitoring")
            return

        # Status emoji mapping
        status_emoji = {
            'healthy': '✅',
            'degraded': '⚠️',
            'down': '❌',
            'circuit_open': '🔴'
        }

        for code, data in summary.items():
            emoji = status_emoji.get(data['status'], '❓')
            print(f"{emoji} [{code}] {data['name']}")
            print(f"    Status: {data['status'].upper()}")
            print(f"    Success Rate: {data['success_rate']}")
            print(f"    Requests: {data['total_requests']} | Avg Response: {data['avg_response_time']}")
            print(f"    Last Success: {data['last_success']} | Last Failure: {data['last_failure']}")
            if data['consecutive_failures'] > 0:
                print(f"    ⚠️  Consecutive Failures: {data['consecutive_failures']}")
            print()

        # Overall statistics
        total_requests = sum(data['total_requests'] for data in summary.values())
        healthy_count = sum(1 for data in summary.values() if data['status'] == 'healthy')
        total_engines = len(summary)
        
        print(f"📊 OVERALL: {healthy_count}/{total_engines} engines healthy | {total_requests} total requests")
        print(f"⏱️  Monitoring since: {self.start_time.strftime('%H:%M:%S')}")
        print("="*80)

# Global health monitor instance
health_monitor = EngineHealthMonitor()