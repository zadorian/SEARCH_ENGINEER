#!/usr/bin/env python3
"""
Base Event Streaming for Search Types
Provides event emission capability for search types to stream results and filtered results
"""

import asyncio
import threading
import queue
import logging
from typing import Dict, Any, Optional, Callable
from datetime import datetime
import json

logger = logging.getLogger(__name__)

class BaseStreamer:
    """Base class for search types that need to emit streaming events"""
    
    def __init__(self):
        # Event emission setup
        self.event_handlers = {}
        self.event_queue = queue.Queue(maxsize=1000)
        self._streaming_enabled = False
        self._stop_streaming = False
        self._streaming_thread = None
        
        # Statistics tracking
        self.stats = {
            'total_events': 0,
            'results_streamed': 0,
            'filtered_streamed': 0,
            'errors': 0
        }
        
        logger.debug("BaseStreamer initialized")
    
    def enable_streaming(self, event_handler: Optional[Callable] = None):
        """Enable event streaming with optional handler"""
        self._streaming_enabled = True
        
        if event_handler:
            self.set_event_handler('all', event_handler)
        
        # Start streaming thread if not already running
        if not self._streaming_thread or not self._streaming_thread.is_alive():
            self._stop_streaming = False
            self._streaming_thread = threading.Thread(target=self._streaming_worker, daemon=True)
            self._streaming_thread.start()
        
        logger.info("Streaming enabled for search type")
    
    def disable_streaming(self):
        """Disable event streaming"""
        self._streaming_enabled = False
        self._stop_streaming = True
        
        if self._streaming_thread and self._streaming_thread.is_alive():
            # Give thread time to finish
            self._streaming_thread.join(timeout=1.0)
        
        logger.info("Streaming disabled for search type")
    
    def set_event_handler(self, event_type: str, handler: Callable):
        """Set event handler for specific event type or 'all' for all events"""
        self.event_handlers[event_type] = handler
        logger.debug(f"Event handler set for: {event_type}")
    
    def emit_event(self, event_type: str, data: Dict[str, Any]):
        """Emit an event with data"""
        if not self._streaming_enabled:
            return
        
        try:
            event = {
                'type': event_type,
                'timestamp': datetime.now().isoformat(),
                'data': data
            }
            
            # Add to queue for async processing
            self.event_queue.put_nowait(event)
            self.stats['total_events'] += 1
            
            if event_type == 'result':
                self.stats['results_streamed'] += 1
            elif event_type == 'filtered':
                self.stats['filtered_streamed'] += 1
                
        except queue.Full:
            logger.warning("Event queue full, dropping event")
            self.stats['errors'] += 1
        except Exception as e:
            logger.error(f"Error emitting event: {e}")
            self.stats['errors'] += 1
    
    def emit_result(self, result: Dict[str, Any], count: int = 0):
        """Convenience method to emit a result event"""
        self.emit_event('result', {
            'result': result,
            'count': count
        })
    
    def emit_filtered_result(self, result: Dict[str, Any], count: int = 0):
        """Convenience method to emit a filtered result event"""
        self.emit_event('filtered', {
            'result': result,
            'count': count,
            'filter_reason': result.get('filter_reason', 'Unknown'),
            'filter_type': result.get('filter_type', 'unknown')
        })
    
    def emit_engine_status(self, engine: str, status: str, results: int = 0):
        """Convenience method to emit engine status"""
        self.emit_event('engine_status', {
            'engine': engine,
            'status': status,
            'results': results
        })
    
    def emit_progress(self, current: int, total: int, message: str = ""):
        """Convenience method to emit progress updates"""
        percentage = (current / total * 100) if total > 0 else 0
        self.emit_event('progress', {
            'current': current,
            'total': total,
            'percentage': percentage,
            'message': message
        })
    
    def emit_completed(self, summary: Dict[str, Any]):
        """Convenience method to emit completion event"""
        # Add streaming stats to summary
        summary['streaming_stats'] = self.get_streaming_stats()
        self.emit_event('completed', summary)
    
    def _streaming_worker(self):
        """Background thread to process event queue"""
        logger.debug("Streaming worker thread started")
        
        while not self._stop_streaming:
            try:
                # Get event from queue with timeout
                event = self.event_queue.get(timeout=0.1)
                
                # Process event
                self._process_event(event)
                
                # Mark task as done
                self.event_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in streaming worker: {e}")
                self.stats['errors'] += 1
        
        logger.debug("Streaming worker thread stopped")
    
    def _process_event(self, event: Dict[str, Any]):
        """Process a single event"""
        event_type = event.get('type')
        
        try:
            # Call specific handler if available
            if event_type in self.event_handlers:
                handler = self.event_handlers[event_type]
                handler(event)
            
            # Call 'all' handler if available
            if 'all' in self.event_handlers:
                handler = self.event_handlers['all']
                handler(event)
                
        except Exception as e:
            logger.error(f"Error processing event {event_type}: {e}")
            self.stats['errors'] += 1
    
    def get_streaming_stats(self) -> Dict[str, Any]:
        """Get streaming statistics"""
        return {
            'enabled': self._streaming_enabled,
            'queue_size': self.event_queue.qsize(),
            'total_events': self.stats['total_events'],
            'results_streamed': self.stats['results_streamed'],
            'filtered_streamed': self.stats['filtered_streamed'],
            'errors': self.stats['errors']
        }
    
    def wait_for_queue_empty(self, timeout: float = 5.0):
        """Wait for event queue to be processed"""
        try:
            # Wait for all events to be processed
            self.event_queue.join()
            return True
        except Exception as e:
            logger.warning(f"Timeout waiting for queue to empty: {e}")
            return False


class SearchTypeEventEmitter(BaseStreamer):
    """
    Enhanced event emitter specifically for search types
    Includes search-specific event types and formatting
    """
    
    def __init__(self, search_type: str = "unknown"):
        super().__init__()
        self.search_type = search_type
        
        # Search-specific stats
        self.search_stats = {
            'engines_queried': 0,
            'engines_completed': 0,
            'engines_failed': 0,
            'total_results': 0,
            'total_filtered': 0,
            'unique_urls': set(),
            'start_time': None,
            'end_time': None
        }
    
    def start_search(self, query: str, engines: list = None):
        """Mark search as started"""
        self.search_stats['start_time'] = datetime.now()
        self.search_stats['engines_queried'] = len(engines) if engines else 0
        
        self.emit_event('search_started', {
            'search_type': self.search_type,
            'query': query,
            'engines': engines or [],
            'timestamp': self.search_stats['start_time'].isoformat()
        })
    
    def complete_search(self, final_summary: Dict[str, Any] = None):
        """Mark search as completed"""
        self.search_stats['end_time'] = datetime.now()
        
        # Calculate duration
        if self.search_stats['start_time']:
            duration = (self.search_stats['end_time'] - self.search_stats['start_time']).total_seconds()
        else:
            duration = 0
        
        # Prepare completion summary
        summary = {
            'search_type': self.search_type,
            'duration_seconds': duration,
            'engines_completed': self.search_stats['engines_completed'],
            'engines_failed': self.search_stats['engines_failed'],
            'total_results': self.search_stats['total_results'],
            'total_filtered': self.search_stats['total_filtered'],
            'unique_urls': len(self.search_stats['unique_urls']),
            'timestamp': self.search_stats['end_time'].isoformat()
        }
        
        # Merge with provided summary
        if final_summary:
            summary.update(final_summary)
        
        self.emit_completed(summary)
    
    def emit_search_result(self, result: Dict[str, Any], engine: str = None):
        """Emit a search result with search-specific formatting"""
        # Track stats
        self.search_stats['total_results'] += 1
        if result.get('url'):
            self.search_stats['unique_urls'].add(result['url'])
        
        # Add search metadata
        enhanced_result = result.copy()
        enhanced_result['search_type'] = self.search_type
        if engine:
            enhanced_result['source_engine'] = engine
        
        self.emit_result(enhanced_result, self.search_stats['total_results'])
    
    def emit_search_filtered_result(self, result: Dict[str, Any], engine: str = None):
        """Emit a filtered result with search-specific formatting"""
        # Track stats
        self.search_stats['total_filtered'] += 1
        
        # Add search metadata
        enhanced_result = result.copy()
        enhanced_result['search_type'] = self.search_type
        if engine:
            enhanced_result['source_engine'] = engine
        
        self.emit_filtered_result(enhanced_result, self.search_stats['total_filtered'])
    
    def mark_engine_complete(self, engine: str, results_count: int = 0, success: bool = True):
        """Mark an engine as completed"""
        if success:
            self.search_stats['engines_completed'] += 1
            status = 'completed'
        else:
            self.search_stats['engines_failed'] += 1
            status = 'failed'
        
        self.emit_engine_status(engine, status, results_count)
    
    def get_search_summary(self) -> Dict[str, Any]:
        """Get comprehensive search summary"""
        base_stats = self.get_streaming_stats()
        
        return {
            **base_stats,
            'search_type': self.search_type,
            'search_stats': {
                **self.search_stats,
                'unique_urls': len(self.search_stats['unique_urls']),  # Convert set to count
                'start_time': self.search_stats['start_time'].isoformat() if self.search_stats['start_time'] else None,
                'end_time': self.search_stats['end_time'].isoformat() if self.search_stats['end_time'] else None
            }
        }