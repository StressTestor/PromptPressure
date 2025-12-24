import asyncio
import time
from typing import Dict

class TokenBucket:
    def __init__(self, rate: float, capacity: float):
        """
        rate: tokens per second
        capacity: max tokens in the bucket
        """
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0):
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.last_update = now
            
            # Refill tokens
            new_tokens = elapsed * self.rate
            self.tokens = min(self.capacity, self.tokens + new_tokens)
            
            if self.tokens < tokens:
                wait_time = (tokens - self.tokens) / self.rate
                await asyncio.sleep(wait_time)
                self.tokens = 0
            else:
                self.tokens -= tokens

class AsyncRateLimiter:
    _limiters: Dict[str, TokenBucket] = {}
    
    @classmethod
    def configure_limiter(cls, key: str, rate: float, burst: float):
        """Pre-configure a limiter for a specific key."""
        cls._limiters[key] = TokenBucket(rate, burst)

    @classmethod
    def get_limiter(cls, key: str, default_rate: float = 5.0, default_burst: float = 10.0) -> TokenBucket:
        if key not in cls._limiters:
            cls._limiters[key] = TokenBucket(default_rate, default_burst)
        return cls._limiters[key]

    @classmethod
    async def wait(cls, key: str, rate: float = 5.0, burst: float = 10.0):
        # Allow run-time override if not configured, but prioritize existing config
        limiter = cls.get_limiter(key, rate, burst)
        await limiter.acquire()
