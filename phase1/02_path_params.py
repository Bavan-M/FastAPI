from fastapi import FastAPI

app=FastAPI()

@app.get("/users/me")
def get_current_user():
    return {"user":"the current logged in user"}

@app.get("/users/{user_id}")
def get_user(user_id:int):
    return {"user_id":user_id}

@app.get("/models/{model_name}")
def get_model(model_name:str):
    supported_models=["Claude","OpenAI","Gemini"]
    return {"model_name":model_name,"supported":model_name in supported_models}

@app.get("/orgs/{org_id}/users/{user_id}")
def get_org_user(org_id:int,user_id:int):
    return {"org_id":org_id,"user_id":user_id}



@app.get("/users/{user_id}/profile")
def get_user_profile(user_id:int):
    return {"user_id":user_id,"profile":"avatar"}

