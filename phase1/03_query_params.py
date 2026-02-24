from fastapi import FastAPI
from typing import Optional

app=FastAPI()

@app.get("/items")
def get_items(skip:int=0,limit:int=10):
    faked_item=[f"item_{i}" for i in range(100)]
    return {
        "skip":skip,
        "limit":limit,
        "items":faked_item[skip:limit+skip]    
    }

@app.get("/search")
def search(query:str):
    return {"query":query,"result":[]}

@app.get("/llm/query")
def llm_query(prompt:str,model:str="gpt-3.5",temperature:float=0.7,max_tokens:int=100,stream:bool=False):
    return{
        "prompt":prompt,
        "model":model,
        "temperature":temperature,
        "max_tokens":max_tokens,
        "stream":stream}

@app.get("/documents")
def get_documents(category:Optional[str]=None,published:Optional[bool]=None):
    filters={}
    if category:
        filters["category"]=category
    if published is not None:
        filters["published"]=published
    return {"filters":filters,"documents":[]}





