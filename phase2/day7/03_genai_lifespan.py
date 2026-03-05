import asyncio
import time
from fastapi import HTTPException,FastAPI,Request
from contextlib import asynccontextmanager
import httpx
from pydantic import BaseModel
from typing import Optional

class OpenAIClient():
    def __init__(self,api_key:str,model:str):
        self.api_key=api_key
        self.model=model
        self.ready=False
        self.total_tokens=0

    async def initialize(self):
        await asyncio.sleep(2)
        self.ready=True
        print(f"Open AI client ready {self.model}")

    async def close(self):
        await asyncio.sleep(2)
        self.ready=False
        print(f"Open AI Client closed .Total tokens used is {self.total_tokens}")

    async def generate(self,prompt:str,max_tokens:int=512):
        if not self.ready:
            raise RuntimeError("Open ai client not initialized")
        
        tokens=len(prompt)*10
        self.total_tokens+=tokens
        return {
            "response":f"[{self.model}] Response to : {prompt}",
            "tokens_used":tokens
        }
    
class VectorDBClient:
    def __init__(self,host:str,collection:str):
        self.host=host
        self.collection=collection
        self.ready=False
        self._store={}

    async def connect(self):
        await asyncio.sleep(2)
        self.ready=True
        print(f"Vector DB connected . Collection :{self.collection}")

    async def disconnect(self):
        self.ready=False
        print(f"Vector DB disconnected. {len(self._store)} vectors stored")

    async def upsert(self,id:int,vector:list,metadata:dict):
        self._store[id]={'vector':vector,"metadata":metadata}
        return {"id":id,"status":"Upserted"}
    

    async def search(self,query_vector:list,top_k:int=5):
        results=list(self._store.values())[:top_k]
        return {"result":results,"total":len(results)}
    

class EmbeddingModel:
    def __init__(self,model_name:str):
        self.model_name=model_name
        self.loaded=False

    def load(self):
        time.sleep(2)
        self.loaded=True
        print(f"Embedding model loaded {self.model_name}")
    
    def unload(self):
        self.loaded=False
        print(f"Embedding model unloaded")

    def embed(self,text:str)-> list:
        if not self.loaded:
            raise RuntimeError("Embedding model not loaded")
        
        return [hash(c)%100/100 for c in text[:5]]
    
class Settings:
    openai_api_key:str="sk-fake-key"
    openai_model:str="gpt-4"
    vector_db_host:str="localhost:3000"
    vector_collections:str='documents'
    emebdding_model:str="texr-embedding-ada-002"

settings=Settings()

@asynccontextmanager
async def lifespan(app:FastAPI):
    print("Initializing the GEN api")

    llm_client=OpenAIClient(
        api_key=settings.openai_api_key,
        model=settings.openai_model
    )

    vector_db=VectorDBClient(
        host=settings.vector_db_host,
        collection=settings.vector_collections
    )

    embedding_model=EmbeddingModel(
        model_name=settings.emebdding_model
    )

    http_client=httpx.AsyncClient(timeout=2)

    await asyncio.gather(llm_client.initialize(),vector_db.connect())
    embedding_model.load()

    app.state.llm_client=llm_client
    app.state.vector_db=vector_db
    app.state.embedding_model=embedding_model
    app.state.http_client=http_client

    print("Gen AI api ready")

    yield

    print("Shutting down GEN ai api")
    await asyncio.gather(llm_client.close(),vector_db.disconnect(),http_client.aclose())
    embedding_model.unload()

    print("Gen AI api shutdown complete")

app=FastAPI(title="Gen AI app",lifespan=lifespan)

@app.get("/health")
async def healthy(request:Request):
    return {
        "status":"ok",
        "resources":
        {
            "llm":request.app.state.llm_client.ready,
            "vector_db":request.app.state.vector_db.ready,
            "embedder":request.app.state.embedding_model.loaded
        }
    }

class IngestRequest(BaseModel):
    doc_id:int
    text:str
    meta_data:Optional[dict]={}

class SearchRequest(BaseModel):
    query:str
    top_k:int

@app.post("/ingest")
async def ingest_document(request:Request,ingest:IngestRequest):
    embed=request.app.state.embedding_model
    vector_db=request.app.state.vector_db

    vector=embed.embed(ingest.text)
    print(vector)
    result=await vector_db.upsert(id=ingest.doc_id,vector=vector,metadata=ingest.meta_data)

    return {"id":ingest.doc_id,"vectors":len(vector),"status":result['status'],"result":result}


@app.get("/search")
async def search(request:Request,search:SearchRequest):
    embed=request.app.state.embedding_model
    vector_db=request.app.state.vector_db

    query_vector=embed.embed(search.query)
    result=await vector_db.search(query_vector=query_vector,top_k=search.top_k)
    return {"query":query_vector,**result}
















    