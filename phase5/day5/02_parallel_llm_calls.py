import os,sys
sys.path.insert(0,os.path.dirname(__file__))
from fastapi import FastAPI
from dotenv import load_dotenv
from openai import AsyncOpenAI
from groq import AsyncGroq
import asyncio
from pydantic import BaseModel
import time
from pathlib import Path
load_dotenv()
# Try to load from parent directory if not found
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

# Debug: Print current working directory and check for .env file
print(f"Current working directory: {os.getcwd()}")
print(f".env file exists: {os.path.exists('.env')}")
print(f".env file exists in parent: {env_path.exists()}")

# Get API keys with better error messages
api_key = os.getenv("OPENAI_API_KEY")
groq_key = os.getenv("GROQ_API_KEY")

print(f"OpenAI API Key loaded: {'Yes' if api_key else 'No'}")
print(f"Groq API Key loaded: {'Yes' if groq_key else 'No'}")

# Debug: Print first few characters if key exists (don't print full key)
if api_key:
    print(f"OpenAI API Key starts with: {api_key[:10]}...")
if groq_key:
    print(f"Groq API Key starts with: {groq_key[:10]}...")



app=FastAPI(title="Parallel LLM Calls")

openai_client=AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
groq_client=AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))

async def call_openai(prompt:str,model:str="gpt-3.5-turbo")->dict:
    start_time=asyncio.get_event_loop().time()
    try:
        response=await openai_client.chat.completions.create(
            model=model,
            max_tokens=800,
            messages=[{"role":"user","content":prompt}]
        )
        return{
            "provider":"openai",
            "model":model,
            "response":response.choices[0].message.content,
            "tokens":response.usage.total_tokens,
            "latency_ms":asyncio.get_event_loop().time()-start_time
        }
    except Exception as e:
        return {"error": str(e), "response": f"Failed: {e}"}
    
async def call_groq(prompt:str,model:str="llama-3.1-8b-instant")->dict:
    start_time=asyncio.get_event_loop().time()
    try:
        response=await groq_client.chat.completions.create(
            model=model,
            max_tokens=800,
            messages=[{"role":"user","content":prompt}]
        )
        return{
            "provider":"groq",
            "model":model,
            "response":response.choices[0].message.content,
            "tokens":response.usage.total_tokens,
            "latency_ms":asyncio.get_event_loop().time()-start_time
        }
    except Exception as e:
        return {"error":str(e),"response":f"Failed: {e}"}
    
async def call_embedding_model(text:str,model:str="text-embedding-3-small")->dict:
    start_time=asyncio.get_event_loop().time()
    try:
        response=await openai_client.embeddings.create(
            model=model,
            input=text
        )
        return {
            "provider":"openai",
            "model":model,
            "embeddings":response.data[0].embedding,
            "dimensions":len(response.data[0].embeddings),
            "latency_ms":(asyncio.get_event_loop().time()-start_time)*1000
        }
    except Exception as e:
        return {"error":str(e),"response":f"Failed: {e}"}

# ============================================================
# SCHEMAS
# ============================================================
class ParallelRequest(BaseModel):
    prompt:str
    models:list[str]=["gpt-3.5-turbo","llama-3.1-8b-instant","text-embedding-3-small"]
    timeout:float=10.0

class RAGRequest(BaseModel):
    query: str
    top_k: int = 5


# ============================================================
# PATTERN 1 — Call all LLMs simultaneously
# ============================================================
@app.post("/llm/parallel")
async def parallel_llm_call(req:ParallelRequest):
    """
    Call multiple LLMs simultaneously — return all responses.
    Use case: comparison, ensemble, A/B testing.
    """
    start=time.perf_counter()
    results=await asyncio.gather(
        call_openai(prompt=req.prompt) if "gpt-3.5-turbo" in req.models else asyncio.sleep(0),
        call_groq(prompt=req.prompt) if "llama-3.1-8b-instant" in req.models else asyncio.sleep(0),
        return_exceptions=True
    )
    duration=time.perf_counter()-start
    print(results)
    # Filter out None results from skipped models and exceptions
    responses=[]
    for r in results:
        if isinstance(r,dict) and "provider" in r:
            responses.append(r)
        elif isinstance(r,Exception):
            responses.append({"error":"failed"})
    return {
        "prompt":req.prompt,
        "responses":responses,
        "total_time_ms":round(duration*1000),
        "models_calles":len(responses)
    }

# ============================================================
# PATTERN 2 — Race: return fastest response
# ============================================================
#You get ONE response – the fastest one. 
# All other slower requests are cancelled immediately. 
# It's like calling multiple taxis and taking the first one that arrives.
@app.post("/llm/fastest")
async def fastest_llm(req:ParallelRequest):
    """
    Call all LLMs — return whichever responds first.
    Use case: minimize latency, use cheapest/fastest available.
    """
    start=time.perf_counter()
    tasks=[
        asyncio.create_task(call_openai(req.prompt),name="gpt=3.5-turbo"),
        asyncio.create_task(call_groq(req.prompt),name="llama")
    ]
    done,pending=await asyncio.wait(tasks,timeout=req.timeout,return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    if not done:
        return {"error","ALL LLM timeout"}
    winner=done.pop().result()
    duration=time.perf_counter()-start
    return {
        "winner":winner,
        "total_time_ms":round(duration*1000),
        "cancelled_models":len(pending)
    }

# ============================================================
# PATTERN 3 — Parallel with timeout per model
# ============================================================
# You get ALL responses that complete within their individual time limits. 
# Each request has its own timeout, and they all run independently. 
# Slow or failing requests don't affect the others.
async def call_with_timeout(coro,model_name:str,timeout:float)->dict:
    try:
        return await asyncio.wait_for(coro,timeout=timeout)
    except asyncio.TimeoutError:
        return {"provider":model_name,"error":"timeout","response":None}
    except Exception as e:
        return {"provider":model_name,"error":str(e),"response":None}

@app.post("/llm/parallel-with-timeout")
async def parallel_with_individual_timeouts(req:ParallelRequest):
    """
    Call all LLMs with individual timeouts per model.
    Failed/slow models don't block successful ones.
    """
    start=time.perf_counter()
    results=await asyncio.gather(
        call_with_timeout(call_openai(req.prompt),model_name="gpt-3.5-turbo",timeout=req.timeout),
        call_with_timeout(call_groq(req.prompt),model_name="llama",timeout=req.timeout)
    )
    duration=time.perf_counter()-start
    print(results)
    success=[r for r in results if not r.get("error")]
    failed=[r for r in results if r.get("error")]
    return{
        "reaults":results,
        "success":len(success),
        "failed":len(failed),
        "total_time_ms":round(duration*1000)
    }


# ============================================================
# PATTERN 4 — Full parallel RAG pipeline
# The most important Gen AI pattern
# ============================================================
async def retrieve_from_vector_db(query: str) -> list:
    """Simulate vector DB retrieval"""
    await asyncio.sleep(0.3)
    return [
        {"text": f"Relevant chunk 1 about {query}", "score": 0.95},
        {"text": f"Relevant chunk 2 about {query}", "score": 0.87},
        {"text": f"Relevant chunk 3 about {query}", "score": 0.82},
    ]


async def retrieve_from_keyword_search(query: str) -> list:
    """Simulate keyword/BM25 search"""
    await asyncio.sleep(0.2)
    return [
        {"text": f"Keyword match 1 for {query}", "score": 0.78},
        {"text": f"Keyword match 2 for {query}", "score": 0.71},
    ]


async def get_user_context(user_id: str) -> dict:
    """Simulate fetching user preferences/history"""
    await asyncio.sleep(0.1)
    return {
        "user_id": user_id,
        "preferences": ["concise", "technical"],
        "recent_topics": ["FastAPI", "RAG", "embeddings"]
    }


async def embed_query(query: str) -> list:
    """Simulate query embedding"""
    result = await call_embedding_model(query)
    return result["embedding"]

@app.post("/rag/query")
async def parallel_rag_pipeline(req: RAGRequest, user_id: str = "user_1"):
    """
    Full parallel RAG pipeline:
    - Embed query
    - Retrieve from vector DB
    - Retrieve from keyword search
    - Fetch user context
    All simultaneously, then synthesize with LLM
    """
    start = time.perf_counter()

    # Step 1 — Run all retrieval operations SIMULTANEOUSLY
    embedding, vector_results, keyword_results, user_context = await asyncio.gather(
        embed_query(req.query),
        retrieve_from_vector_db(req.query),
        retrieve_from_keyword_search(req.query),
        get_user_context(user_id)
    )

    retrieval_time = time.perf_counter() - start

    # Step 2 — Combine and rank results
    all_chunks = vector_results + keyword_results
    all_chunks.sort(key=lambda x: x["score"], reverse=True)
    top_chunks = all_chunks[:req.top_k]

    # Step 3 — Build prompt with context
    context = "\n".join([c["text"] for c in top_chunks])
    augmented_prompt = f"""
    User preferences: {user_context['preferences']}
    Context: {context}
    Question: {req.query}
    """

    # Step 4 — Call LLM with augmented prompt
    llm_response = await call_openai(augmented_prompt, delay=0.5)

    total_time = time.perf_counter() - start

    return {
        "query": req.query,
        "response": llm_response["response"],
        "sources": top_chunks,
        "timing": {
            "retrieval_ms": round(retrieval_time * 1000),
            "total_ms": round(total_time * 1000),
            "llm_ms": round((total_time - retrieval_time) * 1000)
        },
        "stats": {
            "chunks_retrieved": len(all_chunks),
            "chunks_used": len(top_chunks),
            "embedding_dims": len(embedding)
        }
    }

# ============================================================
# PATTERN 5 — Parallel document ingestion
# ============================================================

async def chunk_document(doc_id: str, content: str) -> list:
    await asyncio.sleep(0.2)
    words = content.split()
    return [
        {"chunk_id": f"{doc_id}_chunk_{i}", "text": " ".join(words[i:i+50])}
        for i in range(0, len(words), 50)
    ]


async def embed_chunk(chunk: dict) -> dict:
    await asyncio.sleep(0.1)
    return {**chunk, "embedding": [0.1, 0.2, 0.3]}


async def store_chunk(chunk: dict) -> bool:
    await asyncio.sleep(0.05)
    return True


@app.post("/ingest/parallel")
async def parallel_ingestion(document_content: str, doc_id: str = "doc_1"):
    """
    Ingest document with maximum parallelism:
    - Chunk document
    - Embed ALL chunks simultaneously
    - Store ALL chunks simultaneously
    """
    start = time.perf_counter()

    # Step 1 — Chunk (sequential — depends on full content)
    chunks = await chunk_document(doc_id, document_content)
    print(f"[INGEST] Created {len(chunks)} chunks")

    # Step 2 — Embed ALL chunks in parallel
    embedded_chunks = await asyncio.gather(*[
        embed_chunk(chunk) for chunk in chunks
    ])
    print(f"[INGEST] Embedded {len(embedded_chunks)} chunks")

    # Step 3 — Store ALL chunks in parallel
    store_results = await asyncio.gather(*[
        store_chunk(chunk) for chunk in embedded_chunks
    ])

    duration = time.perf_counter() - start

    return {
        "doc_id": doc_id,
        "chunks_created": len(chunks),
        "chunks_embedded": len(embedded_chunks),
        "chunks_stored": sum(store_results),
        "total_time_ms": round(duration * 1000)
    }


