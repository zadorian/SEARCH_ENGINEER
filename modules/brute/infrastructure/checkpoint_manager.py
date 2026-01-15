#!/usr/bin/env python3
"""
Checkpoint Manager for Search Recovery
Saves search progress and allows resuming interrupted searches
"""

import json
import os
import pickle
from datetime import datetime
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)


class CheckpointManager:
    """Manages checkpoints for search progress"""
    
    def __init__(self, search_id: str, checkpoint_dir: str = "./checkpoints"):
        self.search_id = search_id
        self.checkpoint_dir = checkpoint_dir
        self.checkpoint_file = os.path.join(checkpoint_dir, f"{search_id}.checkpoint")
        
        # Create checkpoint directory if it doesn't exist
        os.makedirs(checkpoint_dir, exist_ok=True)
        
        # Initialize checkpoint data
        self.checkpoint_data = {
            'search_id': search_id,
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat(),
            'query': '',
            'engines': [],
            'completed_engines': [],
            'failed_engines': [],
            'results_count': 0,
            'unique_urls': 0,
            'engine_progress': {},  # {engine: {'completed_queries': [], 'pending_queries': []}}
            'partial_results': [],
            'metadata': {}
        }
        
        # Load existing checkpoint if available
        self.load_checkpoint()
    
    def save_checkpoint(self):
        """Save current checkpoint to disk"""
        try:
            self.checkpoint_data['updated_at'] = datetime.utcnow().isoformat()
            
            # Save as JSON for readability
            with open(self.checkpoint_file, 'w') as f:
                json.dump(self.checkpoint_data, f, indent=2)
            
            # Also save a binary backup
            with open(f"{self.checkpoint_file}.pkl", 'wb') as f:
                pickle.dump(self.checkpoint_data, f)
                
            logger.info(f"Checkpoint saved: {self.search_id}")
            
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
    
    def load_checkpoint(self) -> bool:
        """Load checkpoint from disk if it exists"""
        try:
            if os.path.exists(self.checkpoint_file):
                with open(self.checkpoint_file, 'r') as f:
                    self.checkpoint_data = json.load(f)
                logger.info(f"Checkpoint loaded: {self.search_id}")
                return True
            elif os.path.exists(f"{self.checkpoint_file}.pkl"):
                # Fallback to pickle if JSON is corrupted
                with open(f"{self.checkpoint_file}.pkl", 'rb') as f:
                    self.checkpoint_data = pickle.load(f)
                logger.info(f"Checkpoint loaded from backup: {self.search_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}")
        
        return False
    
    def update_query_info(self, query: str, engines: List[str]):
        """Update query and engine information"""
        self.checkpoint_data['query'] = query
        self.checkpoint_data['engines'] = engines
        
        # Initialize engine progress
        for engine in engines:
            if engine not in self.checkpoint_data['engine_progress']:
                self.checkpoint_data['engine_progress'][engine] = {
                    'completed_queries': [],
                    'pending_queries': [],
                    'total_queries': 0,
                    'results_found': 0
                }
        
        self.save_checkpoint()
    
    def mark_engine_started(self, engine: str, total_queries: int):
        """Mark an engine as started with its total query count"""
        if engine in self.checkpoint_data['engine_progress']:
            self.checkpoint_data['engine_progress'][engine]['total_queries'] = total_queries
            self.checkpoint_data['engine_progress'][engine]['started_at'] = datetime.utcnow().isoformat()
    
    def mark_query_completed(self, engine: str, query: str, results_count: int):
        """Mark a specific query as completed for an engine"""
        if engine in self.checkpoint_data['engine_progress']:
            progress = self.checkpoint_data['engine_progress'][engine]
            
            # Move from pending to completed
            if query in progress['pending_queries']:
                progress['pending_queries'].remove(query)
            
            if query not in progress['completed_queries']:
                progress['completed_queries'].append(query)
            
            progress['results_found'] += results_count
            
            # Save checkpoint every 10 queries
            if len(progress['completed_queries']) % 10 == 0:
                self.save_checkpoint()
    
    def mark_engine_completed(self, engine: str):
        """Mark an engine as fully completed"""
        if engine not in self.checkpoint_data['completed_engines']:
            self.checkpoint_data['completed_engines'].append(engine)
            self.checkpoint_data['engine_progress'][engine]['completed_at'] = datetime.utcnow().isoformat()
        self.save_checkpoint()
    
    def mark_engine_failed(self, engine: str, error: str):
        """Mark an engine as failed"""
        if engine not in self.checkpoint_data['failed_engines']:
            self.checkpoint_data['failed_engines'].append(engine)
            self.checkpoint_data['engine_progress'][engine]['error'] = error
            self.checkpoint_data['engine_progress'][engine]['failed_at'] = datetime.utcnow().isoformat()
        self.save_checkpoint()
    
    def update_results_stats(self, total_results: int, unique_urls: int):
        """Update overall results statistics"""
        self.checkpoint_data['results_count'] = total_results
        self.checkpoint_data['unique_urls'] = unique_urls
    
    def add_partial_results(self, results: List[Dict[str, Any]]):
        """Add partial results to checkpoint"""
        # Only keep last 1000 results in checkpoint to avoid huge files
        self.checkpoint_data['partial_results'].extend(results)
        if len(self.checkpoint_data['partial_results']) > 1000:
            self.checkpoint_data['partial_results'] = self.checkpoint_data['partial_results'][-1000:]
    
    def get_resume_info(self) -> Dict[str, Any]:
        """Get information needed to resume a search"""
        return {
            'query': self.checkpoint_data['query'],
            'engines': self.checkpoint_data['engines'],
            'completed_engines': self.checkpoint_data['completed_engines'],
            'failed_engines': self.checkpoint_data['failed_engines'],
            'engine_progress': self.checkpoint_data['engine_progress'],
            'results_count': self.checkpoint_data['results_count'],
            'unique_urls': self.checkpoint_data['unique_urls']
        }
    
    def should_resume_engine(self, engine: str) -> bool:
        """Check if an engine should be resumed"""
        return (engine not in self.checkpoint_data['completed_engines'] and 
                engine not in self.checkpoint_data['failed_engines'])
    
    def get_pending_queries(self, engine: str) -> List[str]:
        """Get pending queries for an engine"""
        if engine in self.checkpoint_data['engine_progress']:
            return self.checkpoint_data['engine_progress'][engine].get('pending_queries', [])
        return []
    
    def get_progress_summary(self) -> str:
        """Get a human-readable progress summary"""
        total_engines = len(self.checkpoint_data['engines'])
        completed = len(self.checkpoint_data['completed_engines'])
        failed = len(self.checkpoint_data['failed_engines'])
        in_progress = total_engines - completed - failed
        
        summary = f"Search Progress: {completed}/{total_engines} engines completed"
        if failed > 0:
            summary += f" ({failed} failed)"
        if in_progress > 0:
            summary += f" ({in_progress} in progress)"
        
        summary += f"\nResults: {self.checkpoint_data['unique_urls']} unique URLs from {self.checkpoint_data['results_count']} total results"
        
        return summary
    
    def cleanup(self):
        """Remove checkpoint files after successful completion"""
        try:
            if os.path.exists(self.checkpoint_file):
                os.remove(self.checkpoint_file)
            if os.path.exists(f"{self.checkpoint_file}.pkl"):
                os.remove(f"{self.checkpoint_file}.pkl")
            logger.info(f"Checkpoint cleaned up: {self.search_id}")
        except Exception as e:
            logger.error(f"Failed to cleanup checkpoint: {e}")


class CheckpointedSearch:
    """Wrapper to add checkpoint functionality to any search"""
    
    def __init__(self, search_instance, resume_from: Optional[str] = None):
        self.search = search_instance
        self.checkpoint_manager = None
        
        # Generate or use existing search ID
        if resume_from:
            self.search_id = resume_from
            self.checkpoint_manager = CheckpointManager(self.search_id)
            self.resume_info = self.checkpoint_manager.get_resume_info()
            logger.info(f"Resuming search: {self.search_id}")
            logger.info(self.checkpoint_manager.get_progress_summary())
        else:
            self.search_id = f"search_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
            self.checkpoint_manager = CheckpointManager(self.search_id)
            self.resume_info = None
    
    def run(self):
        """Run the search with checkpoint support"""
        try:
            # If resuming, skip completed engines
            if self.resume_info:
                # Filter engines to only those not completed
                original_engines = self.search.engines
                self.search.engines = [e for e in original_engines 
                                     if self.checkpoint_manager.should_resume_engine(e)]
                
                logger.info(f"Resuming with engines: {self.search.engines}")
            
            # Update checkpoint with query info
            self.checkpoint_manager.update_query_info(
                self.search.keyword, 
                self.search.engines
            )
            
            # Run the search
            self.search.search()
            
            # Mark as complete and cleanup
            logger.info("Search completed successfully")
            self.checkpoint_manager.cleanup()
            
        except KeyboardInterrupt:
            logger.warning("Search interrupted by user")
            self.checkpoint_manager.save_checkpoint()
            logger.info(f"Progress saved. Resume with: --resume {self.search_id}")
            raise
        except Exception as e:
            logger.error(f"Search failed: {e}")
            self.checkpoint_manager.save_checkpoint()
            logger.info(f"Progress saved. Resume with: --resume {self.search_id}")
            raise