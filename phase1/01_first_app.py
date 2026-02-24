from fastapi import FastAPI

app=FastAPI(
    title="My First FastAPI App",
    description="Learning FastAPI.",
    version="1.0.0"
)

@app.get("/")
def read_root():
    return {"message":"Hello World!"}

@app.get("/health")
def health_check():
    return {"status":"OK","version":"1.0.0"}

@app.get("/about")
def about():
    return {"framework":"FastAPI","author":"Bavan"}

