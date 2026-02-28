import time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware

app=FastAPI()

# --- CORS Middleware ---
# Essential when your frontend (React, Next.js) calls your FastAPI backend
# Without this, browsers will block cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000","http://localhost:5173","https://yourapp.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# --- Trusted Host Middleware ---
# Protects against HTTP Host header attacks
# Only allow requests from these hosts
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["localhost","127.0.0.1","yourapp.com","*.yourapp.com"],
)

# --- GZip Middleware ---
# Automatically compresses large responses
# Great for RAG responses with large document chunks
app.add_middleware(
    GZipMiddleware,
    minimum_size=1000
)

@app.get("/")
def read_root():
    return {"message":"middleware is active"}

@app.get("/large-response")
def large_response():
    return {"data":["Item"]*1000}

@app.get("/cors-test")
def cors_test():
    return {"cors":"the endpoint is accesible from allowed origins"}