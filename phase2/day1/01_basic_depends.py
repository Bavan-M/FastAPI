from fastapi import FastAPI,Depends,HTTPException

app=FastAPI()

def get_api_version():
    return "v1.0"

@app.get("/info")
def get_info(version:str=Depends(get_api_version)):
    return {"api_version":version}

def pagination(skip:int=0,limit:int=0):
    return {"skip":skip,"limit":limit}

@app.get("/items")
def get_items(params:dict=Depends(pagination)):
    fake_items=[f"item_{i}" for i in range(100)]
    return {"pagination":params,"items":fake_items[params["skip"]:params["skip"]+params["limit"]]}

@app.get("/documents")
def get_documents(params:dict=Depends(pagination)):
    fake_documents=[f"document_{i}" for i in range(100)]
    return {"pagination":params,"documents":fake_documents[params["skip"]:params["skip"]+params["limit"]]}

def valid_api_key(api_key:str):
    api_keys=["secret-123","secret-456"]
    if api_key not in api_keys:
        raise HTTPException(status_code=401,detail="Invalid API Key")
    return api_key

@app.get("/protected")
def protected_route(api_key:str=Depends(valid_api_key)):
    return {"message":"You have access to this protected route","api_key":api_key}



