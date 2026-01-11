#!/usr/bin/env python3
"""
Entity Watchers Integration
===========================

Automatically watches for known entities in search queries and provides alerts.
Currently supports:
- Hungarian entities (K-Monitor corruption data)
- Can be extended for other watchlists
"""

from typing import Dict, List, Optional
import json
from pathlib import Path

# Import specific watchers
from brute.targeted_searches.special.hungarian_watcher import KMonitorWatcher, integrate_with_search


class EntityWatcherSystem:
    """Master entity watching system that coordinates multiple watchers."""
    
    def __init__(self):
        self.watchers = {}
        self.alerts = []
        
        # Initialize available watchers
        self._init_watchers()
    
    def _init_watchers(self):
        """Initialize all available entity watchers."""
        
        # Hungarian entities watcher
        try:
            self.watchers['hungarian'] = KMonitorWatcher()
            print("✅ Hungarian entity watcher initialized")
        except Exception as e:
            print(f"⚠️ Could not initialize Hungarian watcher: {e}")
        
        # Add more watchers here as needed:
        # self.watchers['sanctions'] = SanctionsWatcher()
        # self.watchers['pep'] = PEPWatcher()
        # self.watchers['offshore'] = OffshoreWatcher()
    
    def check_query(self, query: str) -> Dict:
        """Check query against all active watchers.
        
        Returns consolidated alerts from all watchers.
        """
        
        all_alerts = {
            'query': query,
            'alerts': [],
            'entities': [],
            'total_risk': 0,
            'watchers_triggered': []
        }
        
        # Run each watcher
        for name, watcher in self.watchers.items():
            try:
                if name == 'hungarian':
                    results = watcher.watch_query(query)
                    
                    if results['entities_found']:
                        all_alerts['watchers_triggered'].append(name)
                        all_alerts['entities'].extend(results['entities_found'])
                        all_alerts['total_risk'] = max(all_alerts['total_risk'], results['total_risk'])
                        
                        # Create alert
                        alert = {
                            'watcher': 'K-Monitor Hungarian',
                            'severity': self._get_severity(results['total_risk']),
                            'entities': results['entities_found'],
                            'warnings': results.get('warnings', [])
                        }
                        all_alerts['alerts'].append(alert)
                
                # Add other watchers here
                
            except Exception as e:
                print(f"Error in {name} watcher: {e}")
        
        return all_alerts
    
    def _get_severity(self, risk_score: float) -> str:
        """Convert risk score to severity level."""
        if risk_score > 0.7:
            return "HIGH"
        elif risk_score > 0.4:
            return "MEDIUM"
        else:
            return "LOW"
    
    def display_alerts(self, alerts: Dict):
        """Display alerts in a formatted way."""
        
        if not alerts['alerts']:
            return
        
        print("\n" + "="*60)
        print("🔍 ENTITY WATCH ALERTS")
        print("="*60)
        
        for alert in alerts['alerts']:
            severity_emoji = {
                'HIGH': '🔴',
                'MEDIUM': '🟡', 
                'LOW': '🟢'
            }.get(alert['severity'], '⚪')
            
            print(f"\n{severity_emoji} {alert['watcher']} Alert - {alert['severity']} Risk")
            print("-" * 40)
            
            for entity in alert['entities'][:5]:  # Show top 5
                print(f"📌 {entity['name']} ({entity['type']})")
                print(f"   Risk Score: {entity['risk_score']:.2f}")
                if entity.get('red_flags'):
                    print(f"   Red Flags: {', '.join(entity['red_flags'][:3])}")
            
            if alert.get('warnings'):
                print("\n⚠️ Warnings:")
                for warning in alert['warnings']:
                    print(f"   • {warning}")
        
        print("\n" + "="*60)
        print(f"Total entities flagged: {len(alerts['entities'])}")
        print("="*60 + "\n")


# Global watcher instance
_global_watcher = None

def get_entity_watcher() -> EntityWatcherSystem:
    """Get or create global entity watcher instance."""
    global _global_watcher
    if _global_watcher is None:
        _global_watcher = EntityWatcherSystem()
    return _global_watcher


def watch_search_query(query: str) -> Dict:
    """Main entry point for entity watching in searches.
    
    This should be called from main.py or search handlers.
    """
    watcher = get_entity_watcher()
    alerts = watcher.check_query(query)
    
    # Display alerts if any
    if alerts['alerts']:
        watcher.display_alerts(alerts)
    
    return alerts


# Storage requirement estimation
def estimate_storage_requirements():
    """Estimate storage needed for entity watching databases."""
    
    estimates = {
        'hungarian_kmonitor': {
            'entities': '~50MB',  # ~50k entities with metadata
            'tenders': '~100MB',  # ~100k tenders
            'connections': '~20MB',  # Relationship graph
            'models': '~500MB',  # HuBERT model if downloaded
            'total': '~670MB'
        },
        'total_estimated': '670MB - 1GB with indexes'
    }
    
    return estimates


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Entity Watcher System")
        print("Usage:")
        print("  python entity_watchers.py check <query>")
        print("  python entity_watchers.py storage")
        print("  python entity_watchers.py download")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "check":
        query = " ".join(sys.argv[2:])
        alerts = watch_search_query(query)
        
        if not alerts['alerts']:
            print("✅ No entity alerts for this query")
    
    elif command == "storage":
        estimates = estimate_storage_requirements()
        print("📊 Storage Requirements:")
        print(json.dumps(estimates, indent=2))
    
    elif command == "download":
        print("📥 Downloading entity watch databases...")
        watcher = get_entity_watcher()
        
        if 'hungarian' in watcher.watchers:
            watcher.watchers['hungarian'].download_kmonitor_data(limit=5000)
            print("✅ Hungarian entities indexed")