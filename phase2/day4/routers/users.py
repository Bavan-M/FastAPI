from fastapi import APIRouter,Depends
from phase2.day4.models.schemas import UserResponse
from phase2.day4.dependencies.auth import get_current_user,require_admin

router=APIRouter(
    prefix="/users",
    tags=["Users"]
)

@router.get("/me",response_model=UserResponse)
def get_my_profile(current_user:dict=Depends(get_current_user)):
    return {
        "id":current_user['id'],
        "username":current_user["username"],
        "email":f"{current_user['username']}@myapp.com"
    }

@router.get("/{userid}")
def get_user(user_id:int,current_user:dict=Depends(get_current_user)):
    return {
        "userid":user_id,
        "requested_by":current_user['username']
    }

@router.get("/",dependencies=[Depends(require_admin)])
def list_all_users():
    return {"users":["alice",'bob']}

