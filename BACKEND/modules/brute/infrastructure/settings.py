#!/usr/bin/env python3
"""
Centralized settings for targeted_searches modules
Loads configuration from environment variables with sensible defaults
"""

import os
from dataclasses import dataclass
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


@dataclass
class Settings:
    """Configuration settings for search modules"""
    
    # Resource limits
    MAX_CONCURRENT_REQUESTS: int = 5
    MAX_RESULTS_PER_ENGINE: int = 1000
    REQUEST_TIMEOUT: int = 30
    GLOBAL_TIMEOUT: int = 300
    
    # Memory limits
    MAX_BUFFER_SIZE: int = 10000
    MAX_QUEUE_SIZE: int = 5000
    
    # Rate limiting
    REQUESTS_PER_SECOND: int = 10
    
    # HTTP settings
    MAX_CONNECTIONS: int = 100
    MAX_CONNECTIONS_PER_HOST: int = 30
    
    # File I/O
    OUTPUT_BUFFER_SIZE: int = 100
    MAX_FILE_SIZE_MB: int = 100
    
    # Search settings
    DEFAULT_SEARCH_DEPTH: int = 10
    DEDUPLICATION_ENABLED: bool = True
    
    # Retry settings
    MAX_RETRIES: int = 3
    RETRY_DELAY: float = 1.0
    RETRY_BACKOFF: float = 2.0
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: Optional[str] = None
    DEBUG_MODE: bool = False
    
    # Output settings
    DEFAULT_OUTPUT_DIR: str = "./results"
    DEFAULT_OUTPUT_FORMAT: str = "json"
    
    @classmethod
    def from_env(cls) -> 'Settings':
        """Load settings from environment variables"""
        return cls(
            # Resource limits
            MAX_CONCURRENT_REQUESTS=int(os.getenv('MAX_CONCURRENT_REQUESTS', '5')),
            MAX_RESULTS_PER_ENGINE=int(os.getenv('MAX_RESULTS_PER_ENGINE', '1000')),
            REQUEST_TIMEOUT=int(os.getenv('REQUEST_TIMEOUT', '30')),
            GLOBAL_TIMEOUT=int(os.getenv('GLOBAL_TIMEOUT', '300')),
            
            # Memory limits
            MAX_BUFFER_SIZE=int(os.getenv('MAX_BUFFER_SIZE', '10000')),
            MAX_QUEUE_SIZE=int(os.getenv('MAX_QUEUE_SIZE', '5000')),
            
            # Rate limiting
            REQUESTS_PER_SECOND=int(os.getenv('REQUESTS_PER_SECOND', '10')),
            
            # HTTP settings
            MAX_CONNECTIONS=int(os.getenv('MAX_CONNECTIONS', '100')),
            MAX_CONNECTIONS_PER_HOST=int(os.getenv('MAX_CONNECTIONS_PER_HOST', '30')),
            
            # File I/O
            OUTPUT_BUFFER_SIZE=int(os.getenv('OUTPUT_BUFFER_SIZE', '100')),
            MAX_FILE_SIZE_MB=int(os.getenv('MAX_FILE_SIZE_MB', '100')),
            
            # Search settings
            DEFAULT_SEARCH_DEPTH=int(os.getenv('DEFAULT_SEARCH_DEPTH', '10')),
            DEDUPLICATION_ENABLED=os.getenv('DEDUPLICATION_ENABLED', 'true').lower() == 'true',
            
            # Retry settings
            MAX_RETRIES=int(os.getenv('MAX_RETRIES', '3')),
            RETRY_DELAY=float(os.getenv('RETRY_DELAY', '1.0')),
            RETRY_BACKOFF=float(os.getenv('RETRY_BACKOFF', '2.0')),
            
            # Logging
            LOG_LEVEL=os.getenv('LOG_LEVEL', 'INFO').upper(),
            LOG_FILE=os.getenv('LOG_FILE'),
            DEBUG_MODE=os.getenv('DEBUG_MODE', 'false').lower() == 'true',
            
            # Output settings
            DEFAULT_OUTPUT_DIR=os.getenv('DEFAULT_OUTPUT_DIR', './results'),
            DEFAULT_OUTPUT_FORMAT=os.getenv('DEFAULT_OUTPUT_FORMAT', 'json')
        )
    
    def validate(self) -> bool:
        """Validate settings and return True if valid"""
        errors = []
        
        # Check numeric limits
        if self.MAX_CONCURRENT_REQUESTS < 1:
            errors.append("MAX_CONCURRENT_REQUESTS must be at least 1")
        
        if self.MAX_RESULTS_PER_ENGINE < 1:
            errors.append("MAX_RESULTS_PER_ENGINE must be at least 1")
        
        if self.REQUEST_TIMEOUT < 1:
            errors.append("REQUEST_TIMEOUT must be at least 1 second")
        
        if self.REQUESTS_PER_SECOND < 1:
            errors.append("REQUESTS_PER_SECOND must be at least 1")
        
        # Check paths
        output_dir = Path(self.DEFAULT_OUTPUT_DIR)
        if not output_dir.exists():
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                errors.append(f"Cannot create output directory: {e}")
        
        # Check log level
        valid_log_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if self.LOG_LEVEL not in valid_log_levels:
            errors.append(f"Invalid LOG_LEVEL: {self.LOG_LEVEL}")
        
        if errors:
            for error in errors:
                print(f"Settings validation error: {error}")
            return False
        
        return True
    
    def to_dict(self) -> dict:
        """Convert settings to dictionary"""
        return {
            'resource_limits': {
                'max_concurrent_requests': self.MAX_CONCURRENT_REQUESTS,
                'max_results_per_engine': self.MAX_RESULTS_PER_ENGINE,
                'request_timeout': self.REQUEST_TIMEOUT,
                'global_timeout': self.GLOBAL_TIMEOUT,
            },
            'memory_limits': {
                'max_buffer_size': self.MAX_BUFFER_SIZE,
                'max_queue_size': self.MAX_QUEUE_SIZE,
            },
            'rate_limiting': {
                'requests_per_second': self.REQUESTS_PER_SECOND,
            },
            'http_settings': {
                'max_connections': self.MAX_CONNECTIONS,
                'max_connections_per_host': self.MAX_CONNECTIONS_PER_HOST,
            },
            'file_io': {
                'output_buffer_size': self.OUTPUT_BUFFER_SIZE,
                'max_file_size_mb': self.MAX_FILE_SIZE_MB,
            },
            'search_settings': {
                'default_search_depth': self.DEFAULT_SEARCH_DEPTH,
                'deduplication_enabled': self.DEDUPLICATION_ENABLED,
            },
            'retry_settings': {
                'max_retries': self.MAX_RETRIES,
                'retry_delay': self.RETRY_DELAY,
                'retry_backoff': self.RETRY_BACKOFF,
            },
            'logging': {
                'log_level': self.LOG_LEVEL,
                'log_file': self.LOG_FILE,
                'debug_mode': self.DEBUG_MODE,
            },
            'output_settings': {
                'default_output_dir': self.DEFAULT_OUTPUT_DIR,
                'default_output_format': self.DEFAULT_OUTPUT_FORMAT,
            }
        }
    
    def print_summary(self):
        """Print a summary of current settings"""
        print("\nSearch_Engineer Settings Summary")
        print("=" * 40)
        print(f"Resource Limits:")
        print(f"  Max concurrent requests: {self.MAX_CONCURRENT_REQUESTS}")
        print(f"  Max results per engine: {self.MAX_RESULTS_PER_ENGINE}")
        print(f"  Request timeout: {self.REQUEST_TIMEOUT}s")
        print(f"  Global timeout: {self.GLOBAL_TIMEOUT}s")
        print(f"\nMemory Limits:")
        print(f"  Max buffer size: {self.MAX_BUFFER_SIZE}")
        print(f"  Max queue size: {self.MAX_QUEUE_SIZE}")
        print(f"\nRate Limiting:")
        print(f"  Requests per second: {self.REQUESTS_PER_SECOND}")
        print(f"\nHTTP Settings:")
        print(f"  Max connections: {self.MAX_CONNECTIONS}")
        print(f"  Max per host: {self.MAX_CONNECTIONS_PER_HOST}")
        print(f"\nOutput Settings:")
        print(f"  Output directory: {self.DEFAULT_OUTPUT_DIR}")
        print(f"  Output format: {self.DEFAULT_OUTPUT_FORMAT}")
        print(f"\nLogging:")
        print(f"  Log level: {self.LOG_LEVEL}")
        print(f"  Debug mode: {self.DEBUG_MODE}")
        print("=" * 40)


# Global settings instance
settings = Settings.from_env()

# Validate on import
if not settings.validate():
    print("Warning: Some settings are invalid, using defaults")


# Convenience functions
def get_settings() -> Settings:
    """Get the global settings instance"""
    return settings


def reload_settings():
    """Reload settings from environment"""
    global settings
    settings = Settings.from_env()
    if not settings.validate():
        print("Warning: Some settings are invalid after reload")
    return settings


if __name__ == '__main__':
    # Print settings when run directly
    settings.print_summary()
