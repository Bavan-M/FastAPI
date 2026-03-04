import os,sys
sys.path.insert(0,os.path.dirname(__file__))
from fastapi import FastAPI,Request
from contextlib import asynccontextmanager
import asyncio
import time
import httpx

class DatabasePool:
    def __init__(self):
        self.connected=False
        self.pool=[]

    async def connect(self):
        await asyncio.sleep(3)
        self.connected=True
        self.pool=[f"Connection_{con}" for con in range(5)]
        print(f"DB pool ready with {len(self.pool)} conections")

    async def disconnect(self):
        await asyncio.sleep(1.0)
        self.connected=False
        self.pool=[]
        print("DB pool closed successfully")

    async def query(self,sql:str):
        if not self.connected:
            raise RuntimeError("DB not connected")
        return {"sql":sql,"rows":[],"connections":self.pool[0]}
    
class RediesClient:
    def __init__(self):
        self.connected=False
        self._store={}
        
    async def connect(self):
        await asyncio.sleep(3)
        self.connected=True
        print("Redies client connected")
    
    async def close(self):
        self.connected=False
        print("Redis closed successfully")

    async def get(self,key:str):
        return self._store.get(key)
    
    async def set(self,key:str,value:str):
        self._store[key]=value

class MLModel:
    def __init__(self,name:str):
        self.loaded=False
        self.name=name

    def load(self):
        time.sleep(1)
        self.loaded=True
        print(f"Model {self.name} loaded sucessfully into memory")
    
    def unload(self):
        self.loaded=False
        print(f"Model {self.name} unloaded from memory")

    def predict(self,text:str):
        if not self.loaded:
            raise RuntimeError("Model not loaded")
        return {"input":text,"emebedding":[0.1,0.2,0.3]}
    
@asynccontextmanager
async def lifespan(app:FastAPI):
    db=DatabasePool()
    redis=RediesClient()
    model=MLModel(name="text-emebedding-ada-002")
    http_client=httpx.AsyncClient(timeout=0.3)# If an external service takes more than 0.3 seconds to respond, the request fails Prevents your API from hanging when downstream services are slow
    
    await asyncio.gather(db.connect(),redis.connect())
    model.load()

    app.state.db=db
    app.state.redis=redis
    app.state.model=model
    app.state.httpx_client=http_client

    print("All resources ready")

    yield

    print("Shutting down - cleaning up resources")

    await asyncio.gather(db.disconnect(),redis.close(),http_client.aclose())
    model.unload()

    print("Cleanup complete")

app=FastAPI(lifespan=lifespan)

@app.get("/")
def read_root():
    return {"message":"App running with managed resources"}


@app.get("/db/query")
async def query_db(request:Request,sql:str="select * from users"):
    result=await request.app.state.db.query(sql)
    return {"result":result}

@app.get("/cache/{key}")
async def get_cache(request:Request,key:str):
    value=await request.app.state.redis.get(key)
    return {"key":key,"value":value or "Not found"}

@app.post("/cache/{key}")
async def set_cache(key:str,value:str,request:Request):
    await request.app.state.redis.set(key,value)
    return {"key":key,"value":value}

@app.get("/embed")
async def emebd_text(text:str,request:Request):
    result= request.app.state.model.predict(text)
    return result

@app.get("/resource-status")
async def resource_status(request:Request):
    return {
        "database":request.app.state.db.connected,
        "redis":request.app.state.redis.connected,
        "model":request.app.state.model.loaded,
        "model_name":request.app.state.model.name
    }








    