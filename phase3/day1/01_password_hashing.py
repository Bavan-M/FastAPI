from passlib.context import CryptContext
import hashlib
pwd_context=CryptContext(schemes=['argon2'],deprecated='auto')

def hash_password(plain_password:str)->str:
    pre_hashed=hashlib.sha256(plain_password.encode()).hexdigest()
    return pwd_context.hash(pre_hashed)

def verify_password(plain_password:str,hashed_password:str)->bool:
    pre_hashed=hashlib.sha256(plain_password.encode()).hexdigest()
    return pwd_context.verify(pre_hashed,hashed_password)

password='mysecretpassword'
hashed=hash_password(password)

print(f"Original password: {password}") #  Original password: mysecretpassword
print(f"Hashed password {hashed}") # Hashed password $argon2id$v=19$m=65536,t=3,p=4$m7P2vhdCKAVgrLX2/v+fcw$221+FJ20a+Moasz41lluPygNQ9fUc1FsVoSxVvPLzRE
print(f"Verify correct :{verify_password(password,hashed)}") # Verify correct :True
print(f"Verify wrong : {verify_password('wrongpasasword',hashed)}") # Verify wrong : False
 
hash1=hash_password(password)
hash2=hash_password(password)

print(f"Hash1 : {hash1}")
print(f"Hash2 : {hash2}")
print(f"Same ? {hash1==hash2}")
print(f"Both verify {verify_password(password,hash1)} and {verify_password(password,hash2)}")

# Key insight — every hash is different even for the same password because bcrypt adds a random **salt**. 
# But `verify_password` still works because the salt is embedded inside the hash itself.