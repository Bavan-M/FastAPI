import os,sys
from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import JSONResponse
sys.path.insert(0,os.path.dirname(__file__))

app=FastAPI()

@app.get("/user./{userid}")
def get_user(user_id:int):
    fake_user={1:'Alice',2:'Bob'}
    if user_id not in fake_user:
        raise HTTPException(status_code=404,detail=f"User with user id {user_id} not found")
    return {"user_id":user_id,"username":fake_user[user_id]}


@app.get("/protected")
def protected(token:str):
    if token!='valid-token':
        raise HTTPException(status_code=401,detail="Invalid or expire token",headers={"WWW-Authenticate":"Bearer"})
    return {"message":"Access granted"}

@app.get("/documents")
def create_documents(title:str,content:str):
    if not title.strip():
        raise HTTPException(status_code=422,detail="Title cannot be empty")
    if len(content)>1000:
        raise HTTPException(status_code=413,detail="Content too large .Max 1000 characters")
    return {"message":"document created","title":title}

@app.delete("/documents/{doc_id}")
def delete_documents(doc_id:int,role:str="user"):
    if role!="admin":
        raise HTTPException(status_code=403,detail="Only admin can delete it")
    fake_id=[1,2,3]
    if doc_id not in fake_id:
        raise HTTPException(status_code=404,detail=f"Invalid doc id {doc_id}")
    return {"message":f"doc id {doc_id} deleted"}