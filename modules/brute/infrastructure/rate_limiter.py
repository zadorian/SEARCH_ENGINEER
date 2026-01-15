import time
import threading
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

class AdaptiveRateLimiter:
    """INTELLIGENT rate limiter that learns optimal rates in real-time"""
    
    def __init__(self):
        self.last_request_time = defaultdict(float)
        self.request_counts = defaultdict(int)
        self._lock = threading.Lock()
        
        # Engine-specific rate limits - ADAPTIVE AND INTELLIGENT
        self.rate_limits = {
            'GO': 10,    # Google: 10 req/sec (avoid captcha)
            'BR': 50,    # Brave: 50 req/sec (FAST ENGINE!)
            'EX': 100,   # EXA: 100 req/sec (VERY FAST when subscription active!) 
            'AR': 10,    # Archive.org: 10 req/sec (be nice)
            'YE': 20,    # Yep: 20 req/sec
            'QW': 2,     # Qwant: 2 req/sec (be respectful)
            'SS': 30,    # SocialSearcher: 30 req/sec
            'BO': 20,    # BoardReader: 20 req/sec
            'W': 10,     # WikiLeaks: 10 req/sec
            'OA': 100,   # OpenAlex: 100 req/sec (very generous API)
            'GU': 20,    # Gutenberg: 20 req/sec (be polite)
            'CR': 100,   # Crossref: 100 req/sec (no hard limit)
            'OL': 50,    # OpenLibrary: 50 req/sec (be respectful)
            'PM': 3,     # PubMed: 3 req/sec (NCBI limit)
            'AX': 0.33,  # arXiv: 1 req/3 sec (their requirement)
            'SE': 100,   # Semantic Scholar: 100 req/sec with key
            'WP': 200,   # Wikipedia: 200 req/sec allowed
            'NT': 0.5,   # Nature: 0.5 req/sec (scraping, be respectful)
            'JS': 1,     # JSTOR: 1 req/sec (authenticated can be faster)
            'MU': 1,     # Project MUSE: 1 req/sec (authenticated can be faster)
            'SG': 1,     # SAGE Journals: 1 req/sec (authenticated can be faster)
            'BK': 1000,  # Books: No rate limit (local search)
            'AA': 1,     # Anna's Archive: 1 req/sec (searches both books and journals)
            'LG': 1,     # LibGen: 1 req/sec (be respectful)
            'BA': 2,     # Baidu: 2 req/sec (be respectful to Chinese search engine)
            'DEFAULT': 50  # Default: 50 req/sec
        }
        
        # Minimum delays - SMALL BUT SAFE TO AVOID BLOCKS
        self.min_delays = {
            'GO': 0.1,   # Google: 100ms (avoid detection)
            'BR': 0.02,  # Brave: 20ms (VERY FAST!)
            'EX': 0.01,  # EXA: 10ms (BLAZING FAST when active!)
            'AR': 0.1,   # Archive.org: 100ms (respectful)
            'YE': 0.05,  # Yep: 50ms
            'QW': 0.5,   # Qwant: 500ms (respectful delay)
            'SS': 0.03,  # SocialSearcher: 30ms
            'BO': 0.05,  # BoardReader: 50ms
            'W': 0.1,    # WikiLeaks: 100ms
            'OA': 0.01,  # OpenAlex: 10ms (fast API)
            'GU': 0.05,  # Gutenberg: 50ms (be polite)
            'CR': 0.01,  # Crossref: 10ms (fast API)
            'OL': 0.02,  # OpenLibrary: 20ms (respectful)
            'PM': 0.33,  # PubMed: 330ms (NCBI strict limit)
            'AX': 3.0,   # arXiv: 3 seconds (their requirement)
            'SE': 0.01,  # Semantic Scholar: 10ms with key
            'WP': 0.005, # Wikipedia: 5ms (very fast)
            'NT': 2.0,   # Nature: 2 seconds (scraping, be respectful)
            'JS': 1.0,   # JSTOR: 1 second (faster if authenticated)
            'MU': 1.0,   # Project MUSE: 1 second (faster if authenticated)
            'SG': 1.0,   # SAGE Journals: 1 second (faster if authenticated)
            'BK': 0.001,  # Books: 1ms (local search, no rate limit needed)
            'AA': 1.0,   # Anna's Archive: 1 second (searches both books and journals)
            'LG': 1.0,   # LibGen: 1 second (respectful scraping)
            'BA': 0.5,   # Baidu: 500ms (respectful delay)
            'DEFAULT': 0.01  # Default: 10ms (2x faster!)
        }
        
        # Real-time performance metrics
        self.success_count = defaultdict(int)
        self.error_count = defaultdict(int)
        self.last_429_time = defaultdict(float)
        # Standardize on pluralized structure for moving average
        self.avg_response_times = defaultdict(float)
        self.backoff_multiplier = defaultdict(lambda: 1.0)
        # Initialize burst tokens to allow gradual ramp-up
        self.burst_tokens = defaultdict(float)
        for k in list(self.rate_limits.keys()) + ['DEFAULT']:
            self.burst_tokens[k] = 3.0
    
    def wait_if_needed(self, engine_code: str):
        """ADAPTIVE rate limiting that learns from API responses"""
        with self._lock:
            current_time = time.time()
            
            # Check if we got 429 recently - EXPONENTIAL BACKOFF
            time_since_429 = current_time - self.last_429_time[engine_code]
            if time_since_429 < 60:  # Within last minute
                backoff_delay = min(30, 2 ** (5 - time_since_429 / 10))
                time.sleep(backoff_delay)
                self.last_request_time[engine_code] = time.time()
                return
            
            # Calculate adaptive delay based on success rate
            total_requests = self.success_count[engine_code] + self.error_count[engine_code]
            if total_requests > 0:
                success_rate = self.success_count[engine_code] / total_requests
                
                # Adjust multiplier based on success
                if success_rate > 0.95:
                    self.backoff_multiplier[engine_code] *= 0.9  # Speed up
                elif success_rate < 0.8:
                    self.backoff_multiplier[engine_code] *= 1.5  # Slow down
            
            # Apply the adaptive delay
            base_delay = self.min_delays.get(engine_code, self.min_delays['DEFAULT'])
            actual_delay = base_delay * self.backoff_multiplier[engine_code]
            
            time_since_last = current_time - self.last_request_time[engine_code]
            if time_since_last < actual_delay:
                sleep_time = actual_delay - time_since_last
                time.sleep(sleep_time)
            
            self.last_request_time[engine_code] = time.time()
            self.request_counts[engine_code] += 1
    
    def report_error(self, engine_code: str, is_429: bool = False):
        """Report error - INTELLIGENT backoff"""
        with self._lock:
            self.error_count[engine_code] += 1
            
            if is_429:
                # Got rate limited - REMEMBER IT
                self.last_429_time[engine_code] = time.time()
                self.backoff_multiplier[engine_code] = min(10.0, self.backoff_multiplier[engine_code] * 3)
                logger.warning(f"⚠️ {engine_code} rate limited! Backing off x{self.backoff_multiplier[engine_code]:.1f}")
            else:
                # Regular error - moderate backoff
                self.backoff_multiplier[engine_code] = min(5.0, self.backoff_multiplier[engine_code] * 1.5)
    
    def report_success(self, engine_code: str, response_time: float = None):
        """Report success - gradually reduce delays and improve burst capacity"""
        with self._lock:
            # Track success metrics
            if engine_code not in self.success_count:
                self.success_count[engine_code] = 0
            self.success_count[engine_code] += 1
            
            # Update average response time if provided
            if response_time is not None:
                # Exponential moving average
                alpha = 0.3
                self.avg_response_times[engine_code] = (
                    alpha * response_time + 
                    (1 - alpha) * self.avg_response_times.get(engine_code, response_time)
                )
            
            # Gradually reduce backoff on consistent success
            if self.success_count[engine_code] % 5 == 0:  # Every 5 successes
                self.backoff_multiplier[engine_code] = max(1.0, self.backoff_multiplier[engine_code] * 0.8)
            
            # Increase burst capacity gradually
            if self.burst_tokens[engine_code] < 10:
                self.burst_tokens[engine_code] = min(10, self.burst_tokens[engine_code] + 0.5)
            
            # Reduce minimum delay gradually (but not below safe limit)
            default_delay = {
                'GO': 0.1,   # Google minimum
                'BR': 0.02,  # Brave is VERY FAST!
                'EX': 0.01,  # Exa is BLAZING FAST!
                'AR': 0.5,   # Archive.org needs to be slow
                'YE': 0.33,  # Yep moderate
                'SS': 0.05,  # SocialSearcher fast
                'BO': 0.33,  # BoardReader moderate
                'YA': 0.05,  # Yandex can be fast
                'BI': 0.05,  # Bing can be fast
                'DD': 0.05,  # DuckDuckGo fast
                'DEFAULT': 0.05
            }.get(engine_code, 0.05)
            
            current_delay = self.min_delays.get(engine_code, default_delay * 2)
            self.min_delays[engine_code] = max(current_delay * 0.95, default_delay)
