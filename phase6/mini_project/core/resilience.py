import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import asyncio
from typing import Any,Callable
from fastapi import HTTPException
import random
async def with_timeout(coro,timeout:float,operation:str="operation")->Any:
    try:
        return await asyncio.wait_for(coro,timeout=timeout)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"{operation} time out after {timeout}"
        )
    

async def retry(coro_factory:Callable,max_attempt:int=3,base_delay:float=0.5,operation:str="operation")->Any:
    last_exc=None
    for attempt in range(1,max_attempt+1):
        try:
            return await coro_factory()
        except HTTPException as e:
            if 400<=e.status_code<500 and e.status_code!=429:
                raise
            last_exc=e
        except Exception as e:
            last_exc=e
        if attempt<max_attempt:
            delay=min(base_delay*(2**(attempt-1)),60.0)
            delay+=random.uniform(0,delay*0.1)
            await asyncio.sleep(delay)
    raise last_exc or HTTPException(status_code=503,detail=f"{operation} failed after {max_attempt}")


