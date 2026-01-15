#!/usr/bin/env python3
"""
Progress Indicator - Real-time search progress feedback
"""

import asyncio
import sys
import time
from typing import Dict, List, Optional, Any
from threading import Lock
from datetime import datetime


class SearchProgress:
    """Track and display search progress across engines"""
    
    def __init__(self, engines: List[str], verbose: bool = False):
        self.engines = engines
        self.verbose = verbose
        self.status: Dict[str, str] = {engine: "waiting" for engine in engines}
        self.results_count: Dict[str, int] = {engine: 0 for engine in engines}
        self.start_time = time.time()
        self.lock = Lock()
        self._last_update = 0
        self._min_update_interval = 0.1  # Update at most 10 times per second
        
    def update_status(self, engine: str, status: str, results: Optional[int] = None):
        """Update status for an engine"""
        with self.lock:
            if engine in self.status:
                self.status[engine] = status
                if results is not None:
                    self.results_count[engine] = results
        
        # Throttle display updates
        current_time = time.time()
        if current_time - self._last_update >= self._min_update_interval:
            self._last_update = current_time
            self._display()
    
    def _display(self):
        """Display current progress"""
        if not self.verbose and not sys.stdout.isatty():
            return  # Don't display progress in non-interactive mode
        
        # Clear line and return to start
        sys.stdout.write('\r' + ' ' * 100 + '\r')
        
        # Build status line
        parts = []
        for engine in self.engines:
            status = self.status.get(engine, "waiting")
            count = self.results_count.get(engine, 0)
            
            if status == "waiting":
                parts.append(f"{engine}: ⏳")
            elif status == "searching":
                parts.append(f"{engine}: 🔍")
            elif status == "done":
                parts.append(f"{engine}: ✅({count})")
            elif status == "error":
                parts.append(f"{engine}: ❌")
            else:
                parts.append(f"{engine}: {status}")
        
        # Show elapsed time
        elapsed = int(time.time() - self.start_time)
        status_line = f"🔎 Search Progress [{elapsed}s]: " + " | ".join(parts)
        
        # Truncate if too long
        max_width = 120
        if len(status_line) > max_width:
            status_line = status_line[:max_width-3] + "..."
        
        sys.stdout.write(status_line)
        sys.stdout.flush()
    
    def finish(self):
        """Finish progress display"""
        self._display()
        sys.stdout.write('\n')
        sys.stdout.flush()
        
        # Show summary if verbose
        if self.verbose:
            total_results = sum(self.results_count.values())
            total_time = time.time() - self.start_time
            successful = sum(1 for s in self.status.values() if s == "done")
            
            print(f"\n📊 Search Summary:")
            print(f"  • Total Results: {total_results}")
            print(f"  • Successful Engines: {successful}/{len(self.engines)}")
            print(f"  • Total Time: {total_time:.2f}s")


class AsyncSearchProgress:
    """Async version for use with asyncio searches"""
    
    def __init__(self, engines: List[str], verbose: bool = False):
        self.progress = SearchProgress(engines, verbose)
        self.update_task = None
        
    async def __aenter__(self):
        """Start progress tracking"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Finish progress tracking"""
        self.progress.finish()
        if self.update_task:
            self.update_task.cancel()
            try:
                await self.update_task
            except asyncio.CancelledError:
                pass
    
    def update(self, engine: str, status: str, results: Optional[int] = None):
        """Update engine status"""
        self.progress.update_status(engine, status, results)
    
    async def animate(self):
        """Animate progress while searches run"""
        animation = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        frame = 0
        
        while True:
            # Update searching engines with animation
            with self.progress.lock:
                for engine, status in self.progress.status.items():
                    if status == "searching":
                        # Show animated spinner
                        self.progress.status[engine] = f"searching {animation[frame]}"
            
            self.progress._display()
            frame = (frame + 1) % len(animation)
            await asyncio.sleep(0.1)


def progress_wrapper(search_func):
    """Decorator to add progress tracking to search functions"""
    async def wrapped(*args, **kwargs):
        # Extract engine information
        engines = kwargs.get('engines', ['search'])
        verbose = kwargs.get('verbose', False)
        
        async with AsyncSearchProgress(engines, verbose) as progress:
            # Start animation task
            progress.update_task = asyncio.create_task(progress.animate())
            
            # Inject progress callback
            kwargs['progress_callback'] = progress.update
            
            # Run search
            results = await search_func(*args, **kwargs)
            
            return results
    
    return wrapped


# Simple progress bar for non-async operations
class SimpleProgressBar:
    """Simple progress bar for sequential operations"""
    
    def __init__(self, total: int, description: str = "Progress"):
        self.total = total
        self.current = 0
        self.description = description
        self.start_time = time.time()
        
    def update(self, increment: int = 1):
        """Update progress"""
        self.current += increment
        self._display()
    
    def _display(self):
        """Display progress bar"""
        if not sys.stdout.isatty():
            return
        
        # Calculate percentage
        if self.total > 0:
            percentage = (self.current / self.total) * 100
        else:
            percentage = 0
        
        # Build progress bar
        bar_width = 30
        filled = int(bar_width * self.current / self.total) if self.total > 0 else 0
        bar = "█" * filled + "░" * (bar_width - filled)
        
        # Calculate time
        elapsed = time.time() - self.start_time
        if self.current > 0:
            rate = self.current / elapsed
            eta = (self.total - self.current) / rate if rate > 0 else 0
        else:
            eta = 0
        
        # Display
        sys.stdout.write(f'\r{self.description}: [{bar}] {percentage:3.0f}% ({self.current}/{self.total}) ETA: {eta:.1f}s')
        sys.stdout.flush()
    
    def finish(self):
        """Complete progress bar"""
        self.current = self.total
        self._display()
        sys.stdout.write('\n')
        sys.stdout.flush()


# Example usage
if __name__ == "__main__":
    import random
    
    # Test simple progress bar
    print("Testing simple progress bar:")
    progress = SimpleProgressBar(100, "Processing")
    for i in range(100):
        time.sleep(0.01)
        progress.update()
    progress.finish()
    
    # Test search progress
    print("\nTesting search progress:")
    engines = ['Google', 'Bing', 'Yandex', 'DuckDuckGo']
    progress = SearchProgress(engines, verbose=True)
    
    # Simulate searches
    for engine in engines:
        progress.update_status(engine, "searching")
        time.sleep(random.uniform(0.5, 1.5))
        if random.random() > 0.2:
            results = random.randint(10, 100)
            progress.update_status(engine, "done", results)
        else:
            progress.update_status(engine, "error")
    
    progress.finish()