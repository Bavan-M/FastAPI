import sys,os
sys.path.insert(0,os.path.dirname(__file__))

from fastapi import FastAPI,Request
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.middleware.cors import CORSMiddleware
import time
from fastapi.responses import JSONResponse

app=FastAPI(title="Security Headers Demo")

class SecurityHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request:Request, call_next):
        response=await call_next(request)
        
        # --- Prevent clickjacking ---
        # Stops your app being embedded in iframes on other sites
        # Attackers create invisible iframes to trick users into clicking
        response.headers["X-Frame-Options"]="DENY"

        # --- Prevent MIME type sniffing ---
        # Browser won't guess content type — uses what server declares
        # Prevents attackers from uploading HTML disguised as images
        response.headers["X-Content-Type-Options"]="nosniff"

        # --- XSS Protection (legacy browsers) ---
        response.headers["X-XSS-Protection"]="1; mode=block"

        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "          # only load from same origin
            "script-src 'self'; "           # scripts only from your domain
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; " # images from self, data URIs, HTTPS
            "frame-ancestors 'none'; "      # no iframes anywhere
            "base-uri 'self';"
        )

        # --- HTTPS enforcement ---
        # Tells browser to ONLY use HTTPS for this domain for 1 year
        # Even if user types http://, browser auto-upgrades to https://
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains; preload"
        )

        # --- Referrer Policy ---
        # Controls how much URL info is shared when navigating away
        # "strict-origin-when-cross-origin" = safe default
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # --- Permissions Policy ---
        # Disable browser features your app doesn't need
        # Prevents malicious scripts from accessing camera/mic etc.
        response.headers["Permissions-Policy"] = (
            "camera=(), "           # no camera access
            "microphone=(), "       # no microphone access
            "geolocation=(), "      # no location access
            "payment=(), "          # no payment API
            "usb=()"                # no USB access
        )

        # --- Remove server info ---
        # Don't tell attackers what server you're running
        # Default FastAPI/uvicorn adds "uvicorn" header
        if "server" in response.headers:
            del response.headers["server"]

        return response
    

DEV_ORIGINS=[
    "http://localhost:3000", # React apps traditionally run on port 3000
    "http://localhost:5173", # Vite (used with Vue/React/Svelte) defaults to port 5173
    "http://127.0.0.1:3000" # 127.0.0.1 is just the numerical version of localhost 
]

PROD_ORIGINS=[
    "https://yourapp.com",
    "https://www.yourapp.com",
    "https://app.yourapp.com"
]

IS_PRODUCTION=os.getenv("ENV","development")=="production"
ALLOWED_ORIGINS=PROD_ORIGINS if IS_PRODUCTION else DEV_ORIGINS+PROD_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET","PUT","POST","PATCH","DELETE"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-API-Key",
        "X-Request-ID"
    ],
    expose_headers=[
        "X-Request-ID",
        "X-Process-Time"
    ],
    max_age=600 # preflight cache for 10 minutes
)


app.add_middleware(SecurityHeaderMiddleware)

class RateLimitHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, request_per_minute:int=60):
        super().__init__(app)
        self.limit=request_per_minute
        self.requests={}

    async def dispatch(self, request:Request, call_next):
        client_ip=request.client.host
        now=time.time()
        window_start=now-60

        self.requests[client_ip]=[t for t in self.requests.get(client_ip,[]) if t > window_start]
        self.requests[client_ip].append(now)

        current=len(self.requests[client_ip])
        remaining=max(0,self.limit-current)

        if current>self.limit:
            return JSONResponse(
                status_code=429,
                content={"detail":"Rate limit exceeded"},
                headers={
                    "X-RateLimit-Limit":str(self.limit),
                    "X-RateLimit-Remaining":"0",
                    "X-RateLimit-Reset":str(int(window_start+60)),
                    "Retry-After":60
                }
            )
        response=await call_next(request)
        response.headers["X-RateLimit-Limit"]=str(self.limit)
        response.headers["X-RateLimit-Remaining"]=str(remaining)
        response.headers["X-RateLimit-Reset"]=str(int(window_start+60))
        return response
    
app.add_middleware(RateLimitHeadersMiddleware,request_per_minute=60)

@app.get("/")
def root():
    return {
        "message":"Check response headers in browser tools or Swagger"
    }

@app.get("/headers-demo")
def headers_demo(request: Request):
    return {
        "message": "All security headers applied",
        "check_response_headers": [
            "X-Frame-Options",
            "X-Content-Type-Options",
            "Content-Security-Policy",
            "Strict-Transport-Security",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining"
        ]
    }

  



