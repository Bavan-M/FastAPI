import asyncio
import time
from typing import List

async def call_llm(model:str,prompt:str,delay:float)->dict:
    """Simulate calling an LLM API"""
    await asyncio.sleep(delay)
    return {
        "model":model,
        "response":f"Model {model} response to {prompt[:30]}",
        "tokens":len(prompt.split())*10
    }

async def demo_gather():
    print("\n📦 asyncio.gather patterns:")

    # Pattern 1 — basic gather
    start=time.perf_counter()
    results=await asyncio.gather(
        call_llm("gpt-4o","Explain RAG pipelines",1.0),
        call_llm("gpt-turbo-3.5","Explain RAG pipelines",1.5),
        call_llm("claude-3","Explain RAG pipelines",0.5),
    )
    print(f"3 LLMs called in {time.perf_counter()-start:.2f}s")
    for r in results:
        print(f"  {r['model']}: {r['tokens']} tokens")

    # Pattern 2 — gather with mixed results and errors
    results=await asyncio.gather(
        call_llm("gpt-4","Hello",0.5),
        asyncio.sleep(0.5),
        call_llm("claude-3","Hello",0.3),
        return_exceptions=True
    )
    print(f"\nMixed gather results: {len(results)} items")

    # Pattern 3 — dynamic list of coroutines
    models=["gpt-3.5","gpt-4o","claude-3","llama-3"]
    prompt="what is vector db"
    coroutines=[
        call_llm(model,prompt,0.5) for model in models
    ]
    results=await asyncio.gather(*coroutines)
    print(f"\nCalled {len(models)} models simultaneously")
    for r in results:
        print(f"  {r['model']}: {r['response'][:40]}")

async def demo_task_group():
    print("\n🎯 TaskGroup (Python 3.11+):")
    results=[]
     # TaskGroup is safer than gather
    # If ANY task fails → all other tasks are cancelled immediately
    # gather with return_exceptions=True continues even on failure
    async with asyncio.TaskGroup() as tg:
        task1=tg.create_task(call_llm("gpt-4o","Hello",0.5))
        task2=tg.create_task(call_llm("claude-3","Hello",0.3))
        task3=tg.create_task(call_llm("gemini","Hello",0.7))
    # All tasks guaranteed done after the block
    print(f"GPT-4: {task1.result()['response']}")
    print(f"Claude: {task2.result()['response']}")
    print(f"Gemini: {task3.result()['response']}")


async def call_with_timeout(model:str,prompt:str,timeout:float)->dict:
    try:
        return await asyncio.wait_for(
            call_llm(model,prompt,delay=1.0),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        return {"model": model, "error": "timeout", "response": None}

async def fastest_llm_response(prompt:str)->dict:
    """Call multiple LLM return whichever repsonds first.
    Great for reducing latency in production"""

    print(f"\n🏁 Race — fastest LLM wins:")
    tasks=[
        asyncio.create_task(call_llm("gpt-4o",prompt,1.0)),
        asyncio.create_task(call_llm("claude-3",prompt,0.7)),
        asyncio.create_task(call_llm("gemini",prompt,1.2))
    ]

    # wait for FIRST completed task
    done,pending=await asyncio.wait(
        tasks,
        return_when=asyncio.FIRST_COMPLETED
    )
    # Cancel remaining tasks
    for task in pending:
        task.cancel()

    winner=done.pop().result()
    print(f"Winner: {winner['model']} responded first!")
    return winner

async def parallel_with_fallback(prompt:str)->List[dict]:
    """Call all LLMS with individual timeouts.
    Retuen results from whoever responds in time.
    Used for ensemble responses,comparison ,A/B testing"""
    print(f"\n🔄 Parallel with fallback:")

    results=await asyncio.gather(
        call_with_timeout("gpt-4o",prompt,0.8),
        call_with_timeout("claude-3",prompt,0.4),
        call_with_timeout("gemini",prompt,1.3),
        return_exceptions=True   
    )
    successful=[r for r in results if isinstance(r,dict) and not r.get("error")]
    failed=[r for r in results if isinstance(r,dict) and r.get("error")]

    print(f"Successful: {len(successful)}, Failed/Timeout: {len(failed)}")
    return successful


async def demo_wait():
    print("\n⏳ asyncio.wait patterns:")

    tasks = [
        asyncio.create_task(call_llm(f"model_{i}", "test", delay=i*5))
        for i in range(1, 5)
    ]

    # ALL_COMPLETED — wait for all (like gather)
    done, pending = await asyncio.wait(tasks, return_when=asyncio.ALL_COMPLETED)
    print(f"All completed: {len(done)} tasks done")

    # Process results as they complete
    tasks2 = [
        asyncio.create_task(call_llm(f"model_{i}", "test", delay=(4-i)*0.3))
        for i in range(1, 5)
    ]

    print("\nProcessing as they complete:")
    while tasks2:
        done, tasks2 = await asyncio.wait(
            tasks2,
            return_when=asyncio.FIRST_COMPLETED
        )
        for task in done:
            result = task.result()
            print(f"  Completed: {result['model']}")


async def main():
    print("=" * 50)
    print("gather + TaskGroup Deep Dive")
    print("=" * 50)

    await demo_gather()
    await demo_task_group()
    await fastest_llm_response("Hello")
    await parallel_with_fallback("hi")
    await demo_wait()
if __name__=="__main__":
    asyncio.run(main())

