from fastapi import FastAPI,Depends
app=FastAPI()


class PaginationParams:
    def __init__(self,skip:int=0,limit:int=0,max_limit:int=100):
        self.skip=skip
        self.limit=min(limit,max_limit)
        

@app.get("/items")
def get_items(params:PaginationParams=Depends(PaginationParams)):
    items=[f"item_{i}" for i in range(100)]
    return {
        "skip":params.skip,
        "limit":params.limit,
        "items":items[params.skip:params.skip+params.limit]
    }


class LLMConfig:
    def __init__(self,model:str="gpt-3.5",temperature:float=0.7,max_tokens:int=100,stream:bool=False):
        self.model=model
        self.temperature=temperature
        self.max_tokens=max_tokens
        self.stream=stream

@app.get("/generate")
def generate_text(prompt:str,config:LLMConfig=Depends(LLMConfig)):
    return {
        "prompt":prompt,
        "config":{
            "model":config.model,
            "temperature":config.temperature,
            "max_tokens": config.max_tokens,
            "stream":config.stream
        }
    }

class MockLLMConfig:
    model="mock-llm"
    temperature=0.5
    max_tokens=50
    stream=False

app.dependency_overrides[LLMConfig]=lambda:MockLLMConfig()