import time
import asyncio
from fastapi import FastAPI,BackgroundTasks
from pydantic import BaseModel
from typing import Optional

app=FastAPI()

def log_request(endpoints:str,user:str,duration:float):
    time.sleep(0.5)
    print(f"[LOG] {user} called {endpoints} and duration is {duration}")

def send_email(email:str,subject:str,body:str):
    time.sleep(1.0)
    print(f"[EMAIL] sent to {email} Subject:{subject}")

def process_document(doc_id:int,content:str):
    time.sleep(1)
    print(f"[DOC PROCESSING] doc_{doc_id} chunked and embedded ")

@app.get("/items/{item_id}")
def get_item(item_id:int,background_tasks:BackgroundTasks):
    start=time.perf_counter()
    result={"item_id":item_id,"name":f"item_{item_id}"}
    duration=time.perf_counter()-start
    background_tasks.add_task(log_request,"/items","alice",duration)
    return result

class UserRegister(BaseModel):
    username:str
    email:str

@app.get("/user-register")
def register_user(user:UserRegister,background_tasks:BackgroundTasks):
    background_tasks.add_task(send_email,user.email,"Welcome",f"Hey {user.username} we welcome you")
    return {"message":f"Registration successfully done,to {user.username}"}

class DocumentUpload(BaseModel):
    title:str
    content:str

@app.post("/documents")
async def document_upload(doc:DocumentUpload,background_tasks:BackgroundTasks):
    doc_id=42
    background_tasks.add_task(process_document,doc_id,doc.content)
    return {
        "message":"Document uploaded processing in background",
        "document_id":doc_id
    }

@app.post("/ai/generate")
async def generate(prompt:str,background_tasks:BackgroundTasks):
    response=f"Response form {prompt}"
    background_tasks.add_task(log_request,"/ai/generate","alice",0.3)
    background_tasks.add_task(send_email,"alice@gmail.com","New generation",response)
    return {"prompt":prompt,"response":response}



