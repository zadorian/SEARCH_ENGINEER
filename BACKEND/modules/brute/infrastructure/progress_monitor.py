#!/usr/bin/env python3
"""
Real-time Progress Monitor for Search Operations
Shows live statistics and progress bars
"""

import time
import threading
from datetime import datetime, timedelta
from typing import Dict, Any
import os
import sys


class ProgressMonitor:
    """Real-time progress monitoring with console updates"""
    
    def __init__(self):
        self.start_time = time.time()
        self.stats = {
            'engines_total': 0,
            'engines_completed': 0,
            'engines_failed': 0,
            'engines_running': 0,
            'queries_total': 0,
            'queries_completed': 0,
            'results_total': 0,
            'unique_urls': 0,
            'rate_limits_hit': 0,
            'current_qps': 0,  # Queries per second
            'avg_response_time': 0
        }
        self.engine_status = {}  # {engine: {'status': 'running/completed/failed', 'progress': 0-100}}
        self._lock = threading.Lock()
        self._running = False
        self._display_thread = None
    
    def start(self, engines: list):
        """Start monitoring with list of engines"""
        self.stats['engines_total'] = len(engines)
        for engine in engines:
            self.engine_status[engine] = {
                'status': 'pending',
                'progress': 0,
                'queries_done': 0,
                'queries_total': 0,
                'results': 0,
                'start_time': None,
                'end_time': None
            }
        
        self._running = True
        self._display_thread = threading.Thread(target=self._display_loop, daemon=True)
        self._display_thread.start()
    
    def stop(self):
        """Stop monitoring"""
        self._running = False
        if self._display_thread:
            self._display_thread.join(timeout=1)
    
    def update_engine_started(self, engine: str, total_queries: int):
        """Mark engine as started"""
        with self._lock:
            if engine in self.engine_status:
                self.engine_status[engine]['status'] = 'running'
                self.engine_status[engine]['queries_total'] = total_queries
                self.engine_status[engine]['start_time'] = time.time()
                self.stats['engines_running'] += 1
                self.stats['queries_total'] += total_queries
    
    def update_query_completed(self, engine: str, results: int = 0):
        """Update when a query completes"""
        with self._lock:
            if engine in self.engine_status:
                self.engine_status[engine]['queries_done'] += 1
                self.engine_status[engine]['results'] += results
                self.stats['queries_completed'] += 1
                self.stats['results_total'] += results
                
                # Update progress
                total = self.engine_status[engine]['queries_total']
                if total > 0:
                    self.engine_status[engine]['progress'] = (
                        self.engine_status[engine]['queries_done'] / total * 100
                    )
    
    def update_engine_completed(self, engine: str):
        """Mark engine as completed"""
        with self._lock:
            if engine in self.engine_status:
                self.engine_status[engine]['status'] = 'completed'
                self.engine_status[engine]['progress'] = 100
                self.engine_status[engine]['end_time'] = time.time()
                self.stats['engines_completed'] += 1
                self.stats['engines_running'] -= 1
    
    def update_engine_failed(self, engine: str):
        """Mark engine as failed"""
        with self._lock:
            if engine in self.engine_status:
                self.engine_status[engine]['status'] = 'failed'
                self.engine_status[engine]['end_time'] = time.time()
                self.stats['engines_failed'] += 1
                if self.engine_status[engine]['status'] == 'running':
                    self.stats['engines_running'] -= 1
    
    def update_unique_urls(self, count: int):
        """Update unique URL count"""
        with self._lock:
            self.stats['unique_urls'] = count
    
    def update_rate_limit(self):
        """Increment rate limit counter"""
        with self._lock:
            self.stats['rate_limits_hit'] += 1
    
    def _calculate_stats(self):
        """Calculate current statistics"""
        elapsed = time.time() - self.start_time
        if elapsed > 0:
            self.stats['current_qps'] = self.stats['queries_completed'] / elapsed
        
        # Calculate ETA
        if self.stats['queries_completed'] > 0 and self.stats['queries_total'] > 0:
            avg_time_per_query = elapsed / self.stats['queries_completed']
            remaining_queries = self.stats['queries_total'] - self.stats['queries_completed']
            eta_seconds = remaining_queries * avg_time_per_query
            return eta_seconds
        return None
    
    def _display_loop(self):
        """Main display loop that updates console"""
        while self._running:
            self._display_status()
            time.sleep(0.5)  # Update twice per second
    
    def _display_status(self):
        """Display current status to console"""
        # Clear screen (works on Unix/Linux/Mac)
        if os.name == 'posix':
            os.system('clear')
        else:
            os.system('cls')
        
        with self._lock:
            elapsed = time.time() - self.start_time
            eta = self._calculate_stats()
            
            # Header
            print("=" * 80)
            print(f"🔍 SEARCH PROGRESS MONITOR - Elapsed: {self._format_time(elapsed)}")
            print("=" * 80)
            
            # Overall progress
            engines_progress = (self.stats['engines_completed'] / self.stats['engines_total'] * 100 
                              if self.stats['engines_total'] > 0 else 0)
            queries_progress = (self.stats['queries_completed'] / self.stats['queries_total'] * 100 
                              if self.stats['queries_total'] > 0 else 0)
            
            print(f"\n📊 OVERALL PROGRESS:")
            print(f"  Engines: {self._progress_bar(engines_progress)} {engines_progress:.1f}% "
                  f"({self.stats['engines_completed']}/{self.stats['engines_total']})")
            print(f"  Queries: {self._progress_bar(queries_progress)} {queries_progress:.1f}% "
                  f"({self.stats['queries_completed']}/{self.stats['queries_total']})")
            
            if eta:
                print(f"  ETA: {self._format_time(eta)}")
            
            # Statistics
            print(f"\n📈 STATISTICS:")
            print(f"  Results Found: {self.stats['results_total']:,}")
            print(f"  Unique URLs: {self.stats['unique_urls']:,}")
            print(f"  Queries/Second: {self.stats['current_qps']:.2f}")
            print(f"  Rate Limits Hit: {self.stats['rate_limits_hit']}")
            
            # Engine status
            print(f"\n🔧 ENGINE STATUS:")
            print(f"  Running: {self.stats['engines_running']} | "
                  f"Completed: {self.stats['engines_completed']} | "
                  f"Failed: {self.stats['engines_failed']}")
            
            # Individual engine progress
            print(f"\n📋 ENGINE DETAILS:")
            for engine, status in sorted(self.engine_status.items()):
                icon = self._get_status_icon(status['status'])
                progress = status['progress']
                bar = self._progress_bar(progress, width=20)
                
                details = f"{icon} {engine}: {bar} {progress:.0f}%"
                if status['status'] == 'running':
                    details += f" ({status['queries_done']}/{status['queries_total']} queries)"
                elif status['status'] == 'completed':
                    details += f" - {status['results']} results"
                elif status['status'] == 'failed':
                    details += " - FAILED"
                
                print(f"  {details}")
            
            # Footer
            print("\n" + "=" * 80)
            print("Press Ctrl+C to pause and save progress")
    
    def _progress_bar(self, percent: float, width: int = 30) -> str:
        """Create a progress bar string"""
        filled = int(width * percent / 100)
        bar = '█' * filled + '░' * (width - filled)
        return f"[{bar}]"
    
    def _get_status_icon(self, status: str) -> str:
        """Get icon for status"""
        icons = {
            'pending': '⏳',
            'running': '🔄',
            'completed': '✅',
            'failed': '❌'
        }
        return icons.get(status, '❓')
    
    def _format_time(self, seconds: float) -> str:
        """Format seconds into human readable time"""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            return f"{seconds/60:.0f}m {seconds%60:.0f}s"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours:.0f}h {minutes:.0f}m"


class SimpleProgressBar:
    """Simple progress bar for engines that don't need full monitoring"""
    
    def __init__(self, total: int, prefix: str = "Progress"):
        self.total = total
        self.current = 0
        self.prefix = prefix
        self.start_time = time.time()
    
    def update(self, increment: int = 1):
        """Update progress"""
        self.current += increment
        self._display()
    
    def _display(self):
        """Display progress bar"""
        if self.total == 0:
            return
            
        percent = self.current / self.total * 100
        filled = int(40 * self.current / self.total)
        bar = '█' * filled + '░' * (40 - filled)
        
        elapsed = time.time() - self.start_time
        if self.current > 0:
            eta = (elapsed / self.current) * (self.total - self.current)
            eta_str = f"ETA: {eta:.0f}s"
        else:
            eta_str = "ETA: calculating..."
        
        print(f"\r{self.prefix}: [{bar}] {percent:.1f}% ({self.current}/{self.total}) {eta_str}", 
              end='', flush=True)
        
        if self.current >= self.total:
            print()  # New line when complete