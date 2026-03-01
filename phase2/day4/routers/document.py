import sys
import os
from fastapi import APIRouter,Depends,HTTPException
from phase2.day4.models.schemas import DocumentCreate,DocumentResponse
from phase2.day4.dependencies.auth import get_current_user

router=APIRouter(
    prefix="/documents",
    tags=["Documents"]
)

fake_db:list=[]

@router.get("/")
def list_documents(current_user:dict=Depends(get_current_user)):
    return {
        "documents":fake_db,
        "total":len(fake_db)
    }

@router.post("/",response_model=DocumentResponse,status_code=201)
def create_document(doc:DocumentCreate,current_user:dict=Depends(get_current_user)):
    new_doc={
        "id":len(fake_db)+1,
        "title":doc.title,
        "content":doc.content,
        "category":doc.category,
        "created_by":current_user['username']
    }
    fake_db.append(new_doc)
    return new_doc

@router.get("/{doc_id}")
def get_document(doc_id:int,current_user:dict=Depends(get_current_user)):
    doc =next((d for d in fake_db if d['id']==doc_id),None)
    if not doc:
        raise HTTPException(status_code=404,detail="document not found")
    return doc

@router.delete("/{doc_id}",status_code=204)
def delete_document(doc_id:int,current_user:dict=Depends(get_current_user)):
    global fake_db
    fake_db=[d for d in fake_db if d['id']!=doc_id]