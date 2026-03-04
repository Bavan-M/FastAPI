import os,sys
sys.path.insert(0,os.path.dirname(__file__))

from fastapi import FastAPI
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app:FastAPI):
    # ===== STARTUP — runs before app accepts requests =====
    print("="*40)
    print("App is starting up")
    print("Connecting to database")
    print("Loading mmodels")
    print("Warming up clients")
    print("="*40)

    yield # App runs here — handles all requests    
    # ===== SHUTDOWN — runs after app stops accepting requests =====
    print("="*40)
    print("App is shuting down")
    print("Closing database connection")
    print("Releasing Resources")
    print("="*40)

app=FastAPI(lifespan=lifespan)

@app.get("/")
def read_root():
    return {"message":"App is running"}

@app.get("/health")
def health():
    return {"status":"Ok"}

