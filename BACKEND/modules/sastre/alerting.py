#!/usr/bin/env python3
"""
SASTRE Alerting Module

Sends alerts to Slack/Discord when:
- Circuit breaker trips to OPEN
- Error rate exceeds threshold
- Investigation fails
"""

import os
import json
import asyncio
import aiohttp
from datetime import datetime
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum


class AlertSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AlertConfig:
    """Alerting configuration."""
    slack_webhook: str = ""
    discord_webhook: str = ""
    error_rate_threshold: float = 0.3  # 30%
    alert_cooldown_seconds: int = 300  # 5 min between same alerts
    enabled: bool = True
    
    @classmethod
    def from_env(cls) -> "AlertConfig":
        return cls(
            slack_webhook=os.getenv("SASTRE_SLACK_WEBHOOK", ""),
            discord_webhook=os.getenv("SASTRE_DISCORD_WEBHOOK", ""),
            error_rate_threshold=float(os.getenv("SASTRE_ALERT_ERROR_THRESHOLD", "0.3")),
            alert_cooldown_seconds=int(os.getenv("SASTRE_ALERT_COOLDOWN", "300")),
            enabled=os.getenv("SASTRE_ALERTING_ENABLED", "true").lower() == "true"
        )


class Alerter:
    """Alert sender."""
    
    def __init__(self, config: AlertConfig = None):
        self.config = config or AlertConfig.from_env()
        self._last_alerts: Dict[str, datetime] = {}
    
    def _should_alert(self, alert_key: str) -> bool:
        """Check cooldown."""
        if not self.config.enabled:
            return False
        
        last = self._last_alerts.get(alert_key)
        if last:
            elapsed = (datetime.utcnow() - last).total_seconds()
            if elapsed < self.config.alert_cooldown_seconds:
                return False
        
        self._last_alerts[alert_key] = datetime.utcnow()
        return True
    
    async def send_alert(
        self,
        title: str,
        message: str,
        severity: AlertSeverity = AlertSeverity.WARNING,
        fields: Dict[str, str] = None
    ):
        """Send alert to configured channels."""
        alert_key = f"{title}:{severity.value}"
        if not self._should_alert(alert_key):
            return
        
        if self.config.slack_webhook:
            await self._send_slack(title, message, severity, fields)
        
        if self.config.discord_webhook:
            await self._send_discord(title, message, severity, fields)
    
    async def _send_slack(
        self,
        title: str,
        message: str,
        severity: AlertSeverity,
        fields: Dict[str, str] = None
    ):
        """Send Slack alert."""
        color_map = {
            AlertSeverity.INFO: "#36a64f",
            AlertSeverity.WARNING: "#ffcc00",
            AlertSeverity.ERROR: "#ff6600",
            AlertSeverity.CRITICAL: "#ff0000"
        }
        
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"🚨 SASTRE Alert: {title}"}
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": message}
            }
        ]
        
        if fields:
            field_blocks = [
                {"type": "mrkdwn", "text": f"*{k}:* {v}"}
                for k, v in fields.items()
            ]
            blocks.append({
                "type": "section",
                "fields": field_blocks[:10]  # Slack limit
            })
        
        payload = {
            "attachments": [{
                "color": color_map[severity],
                "blocks": blocks
            }]
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.config.slack_webhook,
                    json=payload,
                    timeout=10
                ) as resp:
                    if resp.status != 200:
                        print(f"Slack alert failed: {resp.status}")
        except Exception as e:
            print(f"Slack alert error: {e}")
    
    async def _send_discord(
        self,
        title: str,
        message: str,
        severity: AlertSeverity,
        fields: Dict[str, str] = None
    ):
        """Send Discord alert."""
        color_map = {
            AlertSeverity.INFO: 0x36a64f,
            AlertSeverity.WARNING: 0xffcc00,
            AlertSeverity.ERROR: 0xff6600,
            AlertSeverity.CRITICAL: 0xff0000
        }
        
        embed = {
            "title": f"🚨 SASTRE Alert: {title}",
            "description": message,
            "color": color_map[severity],
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if fields:
            embed["fields"] = [
                {"name": k, "value": v, "inline": True}
                for k, v in list(fields.items())[:25]
            ]
        
        payload = {"embeds": [embed]}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.config.discord_webhook,
                    json=payload,
                    timeout=10
                ) as resp:
                    if resp.status not in (200, 204):
                        print(f"Discord alert failed: {resp.status}")
        except Exception as e:
            print(f"Discord alert error: {e}")
    
    # ==========================================================================
    # SPECIFIC ALERT TYPES
    # ==========================================================================
    
    async def alert_circuit_open(self, circuit_name: str, failure_count: int):
        """Alert when circuit breaker opens."""
        await self.send_alert(
            title="Circuit Breaker Open",
            message=f"Circuit `{circuit_name}` has tripped to OPEN state after {failure_count} failures.",
            severity=AlertSeverity.ERROR,
            fields={
                "Circuit": circuit_name,
                "Failures": str(failure_count),
                "Status": "OPEN"
            }
        )
    
    async def alert_high_error_rate(self, tool_name: str, error_rate: float, period: str):
        """Alert when error rate exceeds threshold."""
        await self.send_alert(
            title="High Error Rate",
            message=f"Tool `{tool_name}` has error rate of {error_rate:.1%} over {period}.",
            severity=AlertSeverity.WARNING,
            fields={
                "Tool": tool_name,
                "Error Rate": f"{error_rate:.1%}",
                "Period": period,
                "Threshold": f"{self.config.error_rate_threshold:.1%}"
            }
        )
    
    async def alert_investigation_failed(self, project_id: str, error: str):
        """Alert when investigation fails."""
        await self.send_alert(
            title="Investigation Failed",
            message=f"Investigation `{project_id}` failed: {error[:200]}",
            severity=AlertSeverity.ERROR,
            fields={
                "Project ID": project_id,
                "Error": error[:100]
            }
        )


# Global alerter
alerter = Alerter()


# =============================================================================
# INTEGRATION WITH PRODUCTION.PY
# =============================================================================

def integrate_with_production():
    """Monkey-patch production.py to add alerting."""
    try:
        from . import production
        
        original_record_failure = production.CircuitBreaker.record_failure
        
        def patched_record_failure(self):
            original_record_failure(self)
            if self.state == production.CircuitState.OPEN:
                asyncio.create_task(
                    alerter.alert_circuit_open(self.name, self.failure_count)
                )
        
        production.CircuitBreaker.record_failure = patched_record_failure
        print("Alerting integrated with production.py")
    except Exception as e:
        print(f"Failed to integrate alerting: {e}")


if __name__ == "__main__":
    # Test alert
    async def test():
        test_alerter = Alerter(AlertConfig(
            slack_webhook=os.getenv("SASTRE_SLACK_WEBHOOK", ""),
            enabled=True
        ))
        await test_alerter.alert_circuit_open("test_circuit", 5)
        print("Test alert sent (if webhook configured)")
    
    asyncio.run(test())
