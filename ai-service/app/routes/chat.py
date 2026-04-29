"""
Chat routes — HTTP layer only.

These functions receive a request, hand it to the service, and return the
response. No business logic lives here. If you find yourself doing data
transformation or conditionals here, it belongs in services/copilot.py instead.
"""

from fastapi import APIRouter
from app.models.chat import ChatRequest, ChatResponse
from app.services.copilot import handle_chat

router = APIRouter()


@router.get("/health")
async def health():
    """
    Liveness check. Called by the Docker healthcheck and can be polled by the
    PHP bridge before sending a real request to confirm the service is up.
    """
    return {"status": "ok", "service": "clinical-copilot"}


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Main endpoint. Receives a validated, pre-authorised request from the PHP
    bridge and returns a structured response.

    FastAPI validates ChatRequest automatically via Pydantic before this
    function is called — a malformed payload never reaches handle_chat().
    """
    return await handle_chat(request)
