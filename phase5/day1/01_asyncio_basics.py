import asyncio
import time
import concurrent.futures

async def fetch_data(source:str,delay:float)->str:
    print(f"-> Starting fetch from {source}")
    await asyncio.sleep(delay)
    print(f"-> Done fetching from {source}")
    return f"Data from {source}"

async def sequential():
    """Run task one after another - slow"""
    print("\n⏳ Sequential (slow):")
    start=time.perf_counter()

    r1=await fetch_data("OpenAI",1.0)
    r2=await fetch_data("PineCone",0.3)
    r3=await fetch_data("PostgreSQL",0.5)

    duration=time.perf_counter()-start
    print(f"Results: {[r1, r2, r3]}")
    print(f"Time: {duration:.2f}s")

async def concurrent():
    """Runs tasks concurrently -fast"""
    print("\n⚡ Concurrent (fast):")
    start=time.perf_counter()

    r1,r2,r3=await asyncio.gather(
        fetch_data("OpenAI",1.0),
        fetch_data("Pinecone",0.3),
        fetch_data("PostgreSQL",0.5)
    )
    duration=time.perf_counter()-start
    print(f"Results: {[r1, r2, r3]}")
    print(f"Time: {duration:.2f}s")


async def demo_task():
    print("\n📋 Tasks demo:")

    task1=asyncio.create_task(fetch_data("OpenAI",2.0),name="openai")
    task2=asyncio.create_task(fetch_data("PineCone",10.5),name="pinecone")

    print("Tasks created — doing other work while they run...")
    await asyncio.sleep(0.8)
    print("Other work done — now waiting for tasks...")

    r1=await task1
    r2=await task2
    print(f"Task results: {r1}, {r2}")

    task3=asyncio.create_task(fetch_data("SlowSource",10.0))
    await asyncio.sleep(0.1)
    task3.cancel()

    try:
        await task3
    except asyncio.CancelledError:
        print("Task3 cancelled successfully")


async def might_fail(source:str,should_fail:bool)->str:
    await asyncio.sleep(0.3)
    if should_fail:
        raise ValueError(f"{source} failes!")
    return f"Success from {source}"

async def demo_error_handling():
    print("\n🔥 Error handling:")
    results=await asyncio.gather(
        might_fail("source",False),
        might_fail("source2",True),
        might_fail("source3",False),
        return_exceptions=True
    )
    for i,result in enumerate(results):
        if isinstance(result,Exception):
            print(f"  Source {i+1} failed: {result}")
        else:
            print(f"  Source {i+1} succeeded: {result}")


async def slow_operations(delay:float)->str:
    await asyncio.sleep(delay)
    return "finally done"

async def demo_timeouts():
    print("\n⏰ Timeouts:")
    # asyncio.wait_for — cancel if takes too long
    try:
        result=await asyncio.wait_for(slow_operations(5.0),timeout=1.0)
        print(f"Result: {result}")
    except asyncio.TimeoutError:
        print("Operation timed out after 1s — cancelled")

    # asyncio.shield — protect from cancellation
    # useful when you want to cancel outer task but finish inner
    try:
        result=await asyncio.wait_for(asyncio.shield(slow_operations(2.0)),timeout=0.1)
    except asyncio.TimeoutError:
        print("Outer timeout hit but shielded task continues running")


async def demo_event_lopp():
    print("\n🔄 Event loop:")
    loop=asyncio.get_running_loop()

    def blocking_io():
        time.sleep(0.5)
        return "blocking result"
    
    # run_in_executor moves blocking code to thread pool
    # event loop is free during execution
    result=await loop.run_in_executor(None,blocking_io)
    print(f"Blocking result (non-blocking): {result}")

async def main():
    print("=" * 50)
    print("asyncio Deep Dive")
    print("=" * 50)

    await sequential()
    await concurrent()
    await demo_task()
    await demo_error_handling()
    await demo_timeouts()
    await demo_event_lopp()
if __name__=="__main__":
    asyncio.run(main())
