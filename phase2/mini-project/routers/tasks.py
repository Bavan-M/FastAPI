import os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
from typing import List
from fastapi import APIRouter,Depends,BackgroundTasks
from dependencies.auth import get_current_user
from models.schemas import TaskResponse,TaskCreate,TaskUpdate,MessageResponse
from data.store import get_task_by_id,get_task_by_owner_id,delete_task,update_task,create_task
from core.exceptions import NotFoundException,ForbiddenException

router=APIRouter(prefix="/tasks",tags=["Tags"])

def log_task_action(action:str,task_id:int,username:str):
    print(f"[TASK LOG] {action} | task_id: {task_id} | user:{username} ")


@router.get("/",response_model=List[TaskResponse])
def list_my_tasks(status:str=None,priority:str=None,current_user:dict=Depends(get_current_user)):
    tasks=get_task_by_owner_id(current_user['id'])
    if status:
        tasks=[t for t in tasks if t['status']==status]

    if priority:
        tasks=[t for t in tasks if t['priority']==priority]

    return tasks

@router.post("/",response_model=TaskResponse,status_code=201)
def create_new_task(request:TaskCreate,background_task:BackgroundTasks,current_user:dict=Depends(get_current_user)):
    new_task=create_task(
        title=request.title,
        description=request.description,
        priority=request.priority,
        owner_id=current_user['id']
    )
    background_task.add_task(log_task_action("[CREATED]",new_task['id'],username=current_user['id']))
    return new_task

@router.get("/{task_id}")
def get_task_id(task_id:int,current_user:dict=Depends(get_current_user)):
    task=get_task_by_id(task_id)
    if not task:
        raise NotFoundException("task",task_id)
    
    if task['owner_id']!=current_user['id'] and current_user['role']!='admin':
        raise ForbiddenException("You can only view your own tasks")
    
    return task

@router.patch("/{task_id}",response_model=TaskResponse)
def update_existing_task(task_id:int,updates:TaskUpdate,background_task:BackgroundTasks,current_user:dict=Depends(get_current_user)):
    task =get_task_by_id(task_id)
    if not task:
        raise NotFoundException('Task',task_id)
    
    if task['owner_id']!=current_user['id']:
        raise ForbiddenException("you can only update your tasks")
    
    update_data=updates.model_dump(exclude_none=True)
    updated=update_task(task_id,update_data)

    background_task.add_task(log_task_action,'[UPDATED]',task_id,current_user['id'])
    return updated

@router.delete("/{task_id}",response_model=MessageResponse)
def delete_existing_task(task_id:int,background_task:BackgroundTasks,current_user:dict=get_current_user):
    task=get_task_by_id(task_id)
    if not task:
        raise NotFoundException("task",task_id)
    
    if task['owner_id']!=current_user['id'] and current_user['role']!='admin':
        raise ForbiddenException("you can delete only your tasks")
    
    delete_task(task_id)

    background_task.add_task(log_task_action,'[DELETED]',task_id,current_user['id'])
    return  {"message":f"task of task_id {task_id} deletd successfully!"}




