import asyncio
import time
import random
from typing import List


async def demo_queue():
    """Queue = buffer producers and consumers.
    Perfect for :
    - Rate limiting LLM calls (max N concurrent).
    - Processing uploaded documents in order.
    - Handling webhook events
    """
    print("\n📬 Queue — producer/consumer:")
    queue=asyncio.Queue(maxsize=5)

    # Producer — puts work items into queue
    async def producer(name:str,items:List[str]):
        for item in items:
            await queue.put(item)
            print(f"  [Producer {name}] queued: {item}")
            await asyncio.sleep(0.1)
        print(f"  [Producer {name}] done")

    # Consumer — takes work items from queue
    async def consumer(name:str):
        while True:
            try:
                item = await asyncio.wait_for(
                    queue.get(),
                    timeout=1.0
                )
                print(f"  [Consumer {name}] processing: {item}")
                await asyncio.sleep(0.3)
                queue.task_done()
            except asyncio.TimeoutError:
                print(f"  [Consumer {name}] no more items, stopping")
                break

    await asyncio.gather(
        producer("A",["doc1","doc2","doc3"]),
        producer("B",["doc4","doc5"]),
        consumer("X"),
        consumer("Y"),
    )
    print("Queue processing complete")

class LLMRateLimiter:
    """Limits concurrent LLM calls using a semaphore-like queue.
    OpenAI has rate limits - this prevents exceeding them.
    """
    def __init__(self,max_concurrent:int=3):
        self.semaphore=asyncio.Semaphore(max_concurrent)
        self.total_calls=0
        self.active_calls=0
        
    async def call_llm(self,prompt:str,model:str="gpt-4")->dict:
        async with self.semaphore:
            self.active_calls+=1
            self.total_calls+=1
            print(f"  [LLM] Active: {self.active_calls} | Total: {self.total_calls}")

            await asyncio.sleep(random.uniform(0.3,0.8))
            result={"model":model,"response":f"Response tp {prompt[:30]}"}
            self.active_calls-=1
            return result
            
async def demo_rate_limiter():
    print("\n🚦 LLM Rate Limiter (max 3 concurrent):")
    limiter=LLMRateLimiter(max_concurrent=3)

    start=time.perf_counter()
    result=await asyncio.gather(
       *[limiter.call_llm(prompt=f"Prompt {i}",model="gpt-4") for i in range(10)]
    )
    duration=time.perf_counter()-start
    print(f"\n10 LLM calls with max 3 concurrent: {duration:.2f}s")
    print(f"Total calls made: {limiter.total_calls}")


async def demo_lock():
    """Lock Prevents multiple coroutines from
    modifying sgared state simultaneously.
    """
    counter_unsafe=0

    async def increment_unsafe():
        nonlocal counter_unsafe
        value=counter_unsafe
        await asyncio.sleep(0.1)
        counter_unsafe=value+1
    await asyncio.gather(*[increment_unsafe() for _ in range(100)])
    print(f"Unsafe counter (expected 100): {counter_unsafe}")  # likely < 100

    counter_safe=0
    lock=asyncio.Lock()
    async def increment_safe():
        nonlocal counter_safe
        async with lock:
            value=counter_safe
            await asyncio.sleep(0.1)
            counter_safe=value+1
    await asyncio.gather(*[increment_safe() for _ in range(100)])
    print(f"Safe counter (expected 100): {counter_safe}")  # always 100


class TokenUsageCounter:
    """Thread safe token usage tracking.
    Multiple async routes update this simultaneously.
    """
    def __init__(self):
        self.lock=asyncio.Lock()
        self.usage={}

    async def add_usage(self,user_id:str,tokens:int):
        async with self.lock:
            self.usage[user_id]=self.usage.get(user_id,0)+tokens
        
    async def get_usage(self,user_id:str)->int:
        async with self.lock:
            return self.usage.get(user_id,0)
        
    async def get_all_usages(self)->dict:
        return dict(self.usage)
    
async def demo_token_tracker():
    print("\n📊 Token usage tracker (concurrent updates):")
    tracker=TokenUsageCounter()

    async def simluate_llm_calls(user_id:str):
        tokens=random.randint(100,500)
        await asyncio.sleep(random.uniform(0.1,0.3))
        await tracker.add_usage(user_id,tokens)

    await asyncio.gather(*[simluate_llm_calls(user_id=f"user_{i % 3}") for i in range(20)])

    usage=await tracker.get_all_usages()
    print("Token usage per user:")
    for user,tokens in usage.items():
        print(f"  {user}: {tokens} tokens")
    
async def demo_event():
    """Event=signal that one coroutine sends to others.
    Used for model loaded signal ,data  ready signal
    """
    print("\n📡 Event — coroutine signaling:")
    model_ready=asyncio.Event()

    async def load_model():
        print("  Loading ML model...")
        await asyncio.sleep(1.0)
        model_ready.set() # signal that model is ready
        print("  Model loaded!")
        
    async def handle_request(request_id:int):
        print(f"  Request {request_id} waiting for model...")
        await model_ready.wait() # blocks until event is set
        print(f"  Request {request_id} being processed!")

    await asyncio.gather(
        load_model(),
        handle_request(1),
        handle_request(2),
        handle_request(3)
    )



async def main():
    print("=" * 50)
    print("Queue + Lock + Event Deep Dive")
    print("=" * 50)
    #await demo_queue()
    #await demo_rate_limiter()
    #await demo_lock()
    #await demo_token_tracker()
    await demo_event()
    print("\n✅ All asyncio primitives covered!")



if __name__=="__main__":
    asyncio.run(main())

