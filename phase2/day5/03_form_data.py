from fastapi import FastAPI,Form,HTTPException,UploadFile,File
from typing import Optional

app=FastAPI()

@app.post("/login")
def login(username:str=Form(...),password:str=Form(...)):
    fake_users={"alice":"password123","bob":"secret123"}
    if fake_users.get(username)!=password:
        raise HTTPException(status_code=401,detail="Invalid Creds")
    return {"message":f"Welcome {username}"  ,"token" :f"token_{username}"}


@app.post("/upload/metadata")
async def upload_with_metadata(title:str=Form(...),description:str=Form(...),category:Optional[str]=Form(...),file:UploadFile=File(...)):
    content=await file.read()
    return {
        "title":title,
        "description":description,
        "category":category,
        "file":{
            "name":file.filename,
            "type":file.content_type,
            "size_bytes":len(content)
        }
    }

@app.post("/feedback")
def submit_feedback(user_id:int=Form(...),rating:int=Form(ge=1,le=5),comment:str=Form(max_length=500),prompt_used:str=Form(None)):
    if rating<3:
        print(f"[RATING] low rating from user {user_id} :{comment}")
    
    return {
        "message":"Feedback recieved",
        "user_id":user_id,
        "rating":rating
    }
