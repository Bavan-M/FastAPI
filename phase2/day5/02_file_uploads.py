import os
from fastapi import FastAPI,UploadFile,File,HTTPException,BackgroundTasks
import asyncio
from typing import List

app=FastAPI()

UPLOAD_DIR="uploads"
os.makedirs(UPLOAD_DIR,exist_ok=True)

ALLOWED_TYPES = {
    "application/pdf",
    "text/plain",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
}

MAX_FILE_SIZE=10*1024*1024

@app.post("/upload")
def upload_file(file:UploadFile=File(...)):
    return {
        "filename":file.filename,
        "content_type":file.content_type,
        "size":"unknown until read"
    }


async def process_for_rag(filename:str,content:str):
    await asyncio.sleep(2)
    print(f"[RAG] {filename} processed -- {len(content)} byts chunked and emebedded")

@app.post("/upload/document")
async def upload_document(file:UploadFile=File(...),background_task:BackgroundTasks=None):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400,detail=f"File type {file.content_type} is not allowed .Use .pdf,.text,.docx")

    content=await file.read()
    print(content)
    if len(content)>MAX_FILE_SIZE:
        raise HTTPException(status_code=400,detail="File too large max size allowed is 10MB")
    
    file_path=os.path.join(UPLOAD_DIR,file.filename)
    with open(file_path,"wb") as f:
        f.write(content)

    background_task.add_task(process_for_rag,file.filename,content)

    return {
        "message":"File uploaded successfully",
        "filename":file.filename,
        "size_bytes":len(content),
        "status":"processing"
    }

@app.post("/upload/multiple")
async def upload_multiple_file(files:List[UploadFile]=File(...)):
    result=[]
    for file in files :
        content=await file.read()
        result.append({
            "filename":file.filename,
            "content_type":file.content_type,
            "size_bytes":len(content)
        }
        )
    return {
        "uploaded":len(result),
        "files":result
    }
@app.post("/upload/text")
async def upload_text(file:UploadFile=File(...)):
    if file.content_type !="text/plain":
        raise HTTPException(status_code=400,detail="Only txt file is allowed")
    content=await file.read()
    text=content.decode("utf-8")
    return {
        "filename":file.filename,
        "size_bytes":len(content),
        "words":text.split(),
        "preview":text[:200]
    }

    
    


