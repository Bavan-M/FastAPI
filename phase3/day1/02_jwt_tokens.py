from datetime import datetime,timezone,timedelta
from typing import Optional
from jose import JWTError,jwt

SECRET_KEY="your-super-secret-key-change-in-production"
ALGORITHM='HS256'
ACCESS_TOKEN_EXPIRE_MINUTES=60

def create_access_token(data:dict,expires_delta:Optional[timedelta]=None)->str:
    to_encode=data.copy()
    expires=datetime.now(timezone.utc)+(expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp":expires})
    return jwt.encode(to_encode,key=SECRET_KEY,algorithm=ALGORITHM)

def decode_access_token(token:str)->dict:
    try:
        payload=jwt.decode(token=token,key=SECRET_KEY,algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
    

token=create_access_token(
    data={
        "sub":"alice",
        "user_id":1,
        "role":"admin"
    }
)

print(f"Token : {token}")
payload=decode_access_token(token)
print(f"Decode payload : {payload}")

fake_toke=token[:-5]
result=decode_access_token(token=fake_toke)
print(f"Tampered token result {result}")

expired_token=create_access_token(
    data={
        "sub":"alice"
    },
    expires_delta=timedelta(seconds=-1)
)

expired_token_result=decode_access_token(expired_token)
print(f"Expired token {expired_token_result}")