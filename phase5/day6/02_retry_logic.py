import os,sys
sys.path.insert(0,os.path.dirname(__file__))

from fastapi import FastAPI
import random

app=FastAPI(title="Retry Logic")

# ============================================================
# RETRY STRATEGIES
# ============================================================
class RetryStratergy:
    """
    Defines HOW to retry — delay calculation strategy.
    """
    @staticmethod
    def fixed(delay:float)->float:
        """Same delay every time: 1s, 1s, 1s"""
        return delay
    
    @staticmethod
    def exponential(attempt:int,base:float=0.5,max_delay:float=60.0)->float:
        """Doubles each time: 0.5s, 1s, 2s, 4s, 8s...
        Most common strategy for external APIs.
        """
        return min(base*(2**(attempt-1)),max_delay)
    
    @staticmethod
    def exponential_jitter(attempt:int,base:float=0.5,max_delay:float=60.0)->float:
        """
        Exponential + random jitter.
        Prevents thundering herd — clients don't all retry at same time.
        Best practice for high-traffic systems.
        """
        exp_delay=min(base*(2**(attempt-1)),max_delay)
        jitter=random.uniform(0,exp_delay*0.1)
        return exp_delay+jitter
    
# ============================================================
# RETRY EXCEPTIONS — what to retry vs what not to
# ============================================================
# Errors worth retrying (transient failures)
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# Errors NOT worth retrying (permanent failures)
NON_RETRYABLE_STATUS_CODES = {400, 401, 403, 404, 422}


