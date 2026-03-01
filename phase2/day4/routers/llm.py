from fastapi import APIRouter,Depends,HTTPException
from phase2.day4.models.schemas import LLMResponse,LMMRequest
from phase2.day4.dependencies.auth import get_current_user
from phase2.day4.core.config import settings

router=APIRouter(
    prefix="/llm",
    tags=['llm']
)

@router.post("/generate",response_model=LLMResponse)
async def generate(request:LMMRequest,current_user:dict=Depends(get_current_user)):
    fake_response=f"Response to {request.prompt[:50]}"
    fake_tokens=len(request.prompt.split())*10
    return {
        "prompt":request.prompt,
        "response":fake_response,
        "model":request.model,
        "tokens_used":fake_tokens
    }

@router.get("/models")
def list_models(current_user:dict=Depends(get_current_user)):
    return {
        "models":["gpt-4","claude-3","gmini-pro"],
        "default":settings.default_model
    }
