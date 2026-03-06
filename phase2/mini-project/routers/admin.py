import os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
from typing import List
from fastapi import APIRouter,Depends
from dependencies.auth import require_admin
from data.store import user_db,get_user_by_userid,tasks_db
from models.schemas import UserResponse,TaskResponse
from core.exceptions import NotFoundException

router=APIRouter(prefix='/admin',tags=['Admin'],dependencies=[Depends(require_admin)])

@router.get("/users",response_model=List[UserResponse])
def get_all_users():
    return list(user_db.values())

@router.get("/{user_id}",response_model=UserResponse)
def get_user(user_id:int):
    user=get_user_by_userid(user_id)
    if not user:
        raise NotFoundException("User",user_id)
    
    return user

@router.get("/tasks",response_model=TaskResponse)
def get_tasks(status:str=None):
    tasks=tasks_db.values()
    if status:
        tasks=[task for task in tasks if task['status']==status]
    return tasks






