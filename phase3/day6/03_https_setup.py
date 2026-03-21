import os,sys
sys.path.insert(0,os.path.dirname(__file__))

from fastapi import FastAPI,Request
from pathlib import Path
import subprocess
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import RedirectResponse

app=FastAPI(title="HTTPS setup demo")

def generate_self_signed_certificate(cert_dir:str="certs"):
    """Generate a self signed SSL certificate for local development
    In production, use Lets Encrypt or your local cloud provider cert."""

    Path(cert_dir).mkdir(exist_ok=True)
    cert_file=f"{cert_dir}/cert.pem"
    key_file=f"{cert_dir}/key.pem"

    if Path(cert_file).exists() and Path(key_file).exists():
        print(f"[SSL] certificate already exists in {cert_dir}")
        return cert_file,key_file
    
    try:
        # This is a terminal command that creates a fake SSL certificate for development. Let me break it down piece by piece
        # openssl req -x509 -newkey rsa:4096 -keyout certs/key.pem -out certs/cert.pem -days 365 -nodes -subj "/CN=localhost"
        # executing the above command in python code
        subprocess.run([
            "openssl","req","-x509",
            "-newkey","rsa:4096",  # Fixed: colon, not hyphen
            "-keyout",key_file,
            "-out",cert_file,
            "-days","365",          # Fixed: added missing hyphen
            "-nodes",
            "-subj","/CN=localhost"
        ],check=True,capture_output=True)
        print(f"[SSL] Self Signed Certificate generated in {cert_dir}/")
        return cert_file,key_file
    except (subprocess.CalledProcessError,FileNotFoundError):
        print(f"[SSL] OpenSSL not found - install it or use a certificate provider")
        return None,None
generate_self_signed_certificate()
class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request:Request, call_next):
        if request.url.scheme=="http":
            https_url=str(request.url).replace("http://","https://",1)
            return RedirectResponse(url=https_url,status_code=301)
        return await call_next(request)
    
IS_PRODUCTION=os.getenv("ENV","development")=="production"
if IS_PRODUCTION:
    app.add_middleware(HTTPSRedirectMiddleware)

@app.get("/")
def root(request:Request):
    return {
        "scheme":request.url.scheme,
        "is_https":request.url.scheme=="https",
        "host":request.url.hostname,
        "message":"Check scheme field - should be https in production"
    }
        
    


