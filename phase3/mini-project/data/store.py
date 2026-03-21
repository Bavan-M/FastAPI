import sys,os
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))

from core.security import hash_password
from datetime import datetime
from typing import Optional,List

users_db:dict={}
api_keys_db:dict={}
hashed_key_index:dict={}
refresh_tokens_store:dict={}
blacklisted_jtis:set=set()
failed_attempts:dict={}
locked_accounts:dict={}
locked_ips:dict={}

user_counter=3

def _init_users():
    users_db["alice"]={
        "id":1,
        "username":"alice",
        "email":"alice@gmail.com",
        "hashed_password":hash_password("pass123"),
        "role":"admin",
        "disabled":False,
        "auth_provider":"local",
        "created_at":datetime.now()
    }
    users_db["bob"]={
        "id":2,
        "username":"bob",
        "email":"bob@gmail.com",
        "hashed_password":hash_password("pass456"),
        "role":"user",
        "disabled":False,
        "auth_provider":"local",
        "created_at":datetime.now()
    }
_init_users()

def get_user_by_name(username:str)->Optional[dict]:
    return users_db.get(username)

def get_user_by_email(email:str)->Optional[dict]:
    return next((user for user in users_db.values() if user["email"]==email),None)

def get_user_by_id(id:int)->Optional[dict]:
    return next((user for user in users_db.values() if user["id"]==id),None)

def create_user(username:str,email:str,password:str,role:str="user")->dict:
    global user_counter
    user={
        "username":username,
        "id":user_counter,
        "email":email,
        "hashed_password":hash_password(password),
        "role":role,
        "disabled":False,
        "auth_provider":"local",
        "created_at":datetime.now()
    }
    users_db[username]=user
    user_counter+=1
    return user

def create_oauth_user(email:str,name:str,google_id:str)->dict:
    global user_counter
    username=email.split("@")[0]+str(user_counter)
    user={
        "username":username,
        "id":user_counter,
        "email":email,
        "hashed_password":None,
        "role":"user",
        "disabled":False,
        "auth_provider":"google",
        "google_id":google_id,
        "created_at":datetime.now()
    }
    users_db[username]=user
    user_counter+=1
    return user

def store_api_keys(key_id:str,key_data:dict,hashed:str):
    api_keys_db[key_id]=key_data
    hashed_key_index[hashed]=key_id


def get_api_key_by_hash(hashed:str)->Optional[dict]:
    key_id=hashed_key_index.get(hashed)
    if not key_id:
        return None
    return api_keys_db.get(key_id)


def get_api_keys_by_owner(owner:int)->List[dict]:
    return [key for key in api_keys_db.values() if key["owner"]==owner]


