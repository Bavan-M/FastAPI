from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from phase2.day4.core.config import settings
from phase2.day4.routers import users,document,llm

app=FastAPI(
    title=settings.app_name,
    version=settings.version,
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

app.include_router(users.router,prefix=settings.api_prefix)
app.include_router(document.router,prefix=settings.api_prefix)
app.include_router(llm.router,prefix=settings.api_prefix)

@app.get("/",tags=["Health"])
def root():
    return {"app":settings.app_name,"version":settings.version}

@app.get("/health",tags=["Health"])
def health():
    return {"status":"Ok"}

