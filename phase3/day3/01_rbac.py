import sys,os
sys.path.insert(0,os.path.dirname(__file__))

from fastapi import FastAPI,Depends,HTTPException,status
from enum import Enum
from typing import List
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordBearer,OAuth2PasswordRequestForm
import hashlib
from jose import jwt,JWTError
from datetime import datetime,timedelta,timezone


SUPER_SECRET_KEY="your-super-secret-key"
ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=10

pwd_context=CryptContext(schemes="argon2",deprecated="auto")
oauth2=OAuth2PasswordBearer(tokenUrl="/auth/login")

def hash_password(plain_password:str)->str:
    pre_hashed=hashlib.sha256(plain_password.encode()).hexdigest()
    return pwd_context.hash(pre_hashed)

def verify_password(passowrd:str,hash_password:str)->bool:
    pre_hashed=hashlib.sha256(passowrd.encode()).hexdigest()
    return pwd_context.verify(pre_hashed,hash_password)




app=FastAPI(title="Role Base Access Control Demo")

class Permission(str,Enum):
    READ_OWN_TASKS = "read:own_tasks"
    WRITE_OWN_TASKS ="write:own_tasks"
    DELETE_OWN_TASKS ="delete:own_tasks"
    READ_ALL_TASKS = "read:all_tasks"
    DELETE_ALL_TASKS = "delete:all_tasks"

    READ_OWN_PROFILE ="read:own_profile"
    READ_ALL_USERS ="read:all_users"
    MANAGE_USERS = "manage:users"

    VIEW_ANALYTICS = "view:analytics"

    USE_LLM = "use:llm"
    USE_EMBEDDINGS = "use:embeddings"

class Role(str,Enum):
    ADMIN="admin"
    ANALYST="analyst"
    USER="user"
    GUEST="guest"

ROLE_PERMISSION:dict[Role,List[Permission]]={
    Role.ADMIN:[
        Permission.READ_OWN_TASKS,
        Permission.WRITE_OWN_TASKS,
        Permission.DELETE_OWN_TASKS,
        Permission.READ_ALL_TASKS,
        Permission.DELETE_ALL_TASKS,
        Permission.READ_OWN_PROFILE,
        Permission.READ_ALL_USERS,
        Permission.MANAGE_USERS,
        Permission.VIEW_ANALYTICS,
        Permission.USE_LLM,
        Permission.USE_EMBEDDINGS,
    ],
    Role.ANALYST:[
        Permission.READ_OWN_TASKS,
        Permission.READ_ALL_TASKS,
        Permission.READ_OWN_PROFILE,
        Permission.READ_ALL_USERS,
        Permission.VIEW_ANALYTICS,
        Permission.USE_EMBEDDINGS,
    ],
    Role.USER:[
        Permission.READ_OWN_TASKS,
        Permission.WRITE_OWN_TASKS,
        Permission.DELETE_OWN_TASKS,
        Permission.READ_OWN_PROFILE,
        Permission.USE_LLM,
        Permission.USE_EMBEDDINGS,
    ],
    Role.GUEST:[
        Permission.READ_OWN_PROFILE,
    ]
}


def get_permission_for_role(role:Role)->List[Permission]:
    return ROLE_PERMISSION.get(role,[])

def has_permission(role:Role,permission:Permission)->bool:
    return permission in get_permission_for_role(role)


fake_users_db = {
    "alice":   {"id": 1, "username": "alice",   "hashed_password": hash_password("pass123"), "role": Role.ADMIN},
    "bob":     {"id": 2, "username": "bob",     "hashed_password": hash_password("pass123"), "role": Role.USER},
    "charlie": {"id": 3, "username": "charlie", "hashed_password": hash_password("pass123"), "role": Role.ANALYST},
    "dave":    {"id": 4, "username": "dave",    "hashed_password": hash_password("pass123"), "role": Role.GUEST},
}

def create_access_token(data:dict)->str:
    to_encode=data.copy()
    to_encode["exp"]=datetime.now(timezone.utc)+timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(to_encode,key=SUPER_SECRET_KEY,algorithm=ALGORITHM)

async def get_current_user(token:str=Depends(oauth2))->dict:
    try:
        payload=jwt.decode(token,key=SUPER_SECRET_KEY,algorithms=[ALGORITHM])
        username=payload.get("sub")
        if not username:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail="Invalid token")
        
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail="Invalid token")
    
    user=fake_users_db.get(username)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail="User not found")
    return user


def require_permission(permsision:Permission):
    def dependency(current_user:dict=Depends(get_current_user))->dict:
        role=current_user['role']
        print(role)
        print(current_user['username'])
        if not has_permission(role,permsision):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail=f"Permission denied.Required :{permsision}")
        return current_user
    return dependency

def require_any_permission(*permissions:Permission):
    def dependency(current_user:dict=Depends(get_current_user))->dict:
        role=current_user['role']
        if not any (has_permission(role,p) for p in permissions):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail=f"Permission denied.Required one of :{[p for p in permissions]}")
        return current_user
    return dependency



@app.post("/auth/login")
async def login(form_data:OAuth2PasswordRequestForm=Depends()):
    user=fake_users_db.get(form_data.username)
    if not user or not verify_password(form_data.password,user['hashed_password']):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail="Invalid credentials")
    payload={
        "sub":user['username'],
        "role":user['role']
    }
    token=create_access_token(data=payload)

    return {
        "access_token":token,"type":"bearer"
    }

@app.get("/my/permissions")
def my_permission(current_user:dict=Depends(get_current_user)):
    role=current_user['role']
    return {
        "username":current_user['username'],
        "role":role,
        "permissions":get_permission_for_role(role)
    }

@app.get("/tasks/mine")
def get_my_tasks(current_user:dict=Depends(require_permission(Permission.READ_ALL_TASKS))):
    return {
        "tasks":[],
        "username":current_user['username']
    }


@app.delete("/tasks/{task_id}")
def delete_task(task_id:int,current_user:dict=Depends(require_any_permission(Permission.DELETE_ALL_TASKS,Permission.DELETE_OWN_TASKS))):
    return {"deleted":task_id,"by":current_user['user']}

@app.post("/ai/generate")
def generate(prompt:str,current_user:dict=Depends(require_permission(Permission.USE_LLM))):
    return {
        "prompt":prompt,
        "response":"..........",
        "username":current_user['username']
    }