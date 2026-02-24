from fastapi import FastAPI,Depends,HTTPException

app=FastAPI()

def get_token(token:str):
    if not token:
        raise HTTPException(status_code=401,detail="token is missing")
    return token

def get_current_user(token:str=Depends(get_token)):
    fake_users={
        "token_alice":{"id":1,"name":"Alice","role":"admin"},
        "token_bob":{"id":2,"name":"Bob","role":"user"}
    }
    users=fake_users.get(token)
    if not users:
        raise HTTPException(status_code=401,detail="Invalid token")
    
    return users

def require_admin(user:dict=Depends(get_current_user)):
    if user["role"]!="admin":
        raise HTTPException(status_code=403,detail="Admins only.")
    return user

@app.get("/profile")
def get_profile(user:dict=Depends(get_current_user)):
    return {"profile":user}

@app.get("/admin/dashboard")
def admin_dashboard(user:dict=Depends(require_admin)):
    return {"message":f"Welcome to the admin dashboard, {user['name']}!"}

