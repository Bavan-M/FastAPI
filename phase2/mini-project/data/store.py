from datetime import datetime
from typing import Dict,List,Optional

user_db:Dict[int,dict]={
    1:
    {
        "id":1,
        "username":"alice",
        "email":"alice@gmail.com",
        "password":"password@123",
        "role":"admin",
        "created_at":datetime.now()
    },
    2:
    {
         "id":2,
        "username":"bob",
        "email":"bob@gmail.com",
        "password":"password@456",
        "role":"user",
        "created_at":datetime.now()
    }
}

tasks_db:Dict[int,dict]={
    1:
    {
        "id":1,
        "title":"Learn FastAPI",
        "description":"Complete phase 2",
        "status":"in_progress",
        "priority":"high",
        "owner_id":1,
        "created_at":datetime.now()
    },
    2:
    {
        "id":2,
        "title":"Build Rag Pipeline",
        "description":"Implement vector search",
        "status":"to_do",
        "priority":"medium",
        "owner_id":2,
        "created_at":datetime.now()
    }
}

user_id_counter=3
task_id_counter=3

def get_user_by_username(username:str)->Optional[dict]:
    return next((user for user in user_db.values() if user['username']==username),None)

def get_user_by_userid(user_id:int)->Optional[dict]:
    return user_db.get(user_id)

def create_user(username:str,email:str,password:str)->dict:
    global user_id_counter
    user={
        "id":user_id_counter,
        "username":username,
        "email":email,
        "password":password,
        "role":"user",
        "created_at":datetime.now()
    }
    user_db[user_id_counter]=user
    user_id_counter+=1
    return user

def get_task_by_owner_id(owner_id:int)->Optional[dict]:
    return next((task for task in tasks_db.values() if task['owner_id']==owner_id),None)

def get_task_by_id(id:int)->Optional[dict]:
    return tasks_db.get(id)

def create_task(title:str,description:str,priority:str,owner_id:int)->dict:
    global task_id_counter
    task={
        "title":title,
        "description":description,
        "status":"todo",
        "priority":priority,
        "owner_id":owner_id,
        "created_at":datetime.now(),
        "id":task_id_counter
    }
    tasks_db[task_id_counter]=task
    task_id_counter+=1
    return task

def update_task(task_id:int,updates:dict)->Optional[dict]:
    if task_id not in tasks_db:
        return None
    tasks_db[task_id].update(updates)
    return tasks_db[task_id]

def delete_task(task_id:int)->bool:
    if task_id not in task_id:
        return False
    del tasks_db[task_id]
    return True


