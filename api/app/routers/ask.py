from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from app.auth import get_caller          # use whatever dependency your other routers use
from app.ai.analyst import ask

router = APIRouter(prefix="/v1", tags=["analyst"])


class AskBody(BaseModel):
    model_config = ConfigDict(extra="forbid")      # an org_id in the body gives a 422
    question: str = Field(min_length=3, max_length=500)


@router.post("/ask")
def ask_endpoint(body: AskBody, request: Request, caller=Depends(get_caller)):
    rid = getattr(request.state, "request_id", "n/a")
    result = ask(caller, body.question, rid)
    return {"answer": result["answer"], "status": result["status"],
            "tools_used": result["tools_used"], "request_id": rid}