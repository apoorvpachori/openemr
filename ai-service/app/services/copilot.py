"""
CopilotService — business logic layer.

Routes are thin HTTP handlers. This module owns what actually happens with a
request. Right now that's an echo stub. In Step 5 this becomes a LangGraph
agent invocation.

Keeping logic here (not in the route) means:
- Routes stay readable (just HTTP in/out)
- This service can be tested directly without spinning up HTTP
- Swapping the stub for the real agent requires changing only this file
"""

import logging

from app.models.chat import ChatRequest, ChatResponse

logger = logging.getLogger("copilot.service")


async def handle_chat(request: ChatRequest) -> ChatResponse:
    """
    Process a chat request and return a response.

    Step 2 (now): echo stub — confirms the PHP→Python pipeline works and shows
    what context fields are arriving so we can verify Step 4's PHP data fetch.

    Step 5: replaced with `await agent.run(request)` — a full LangGraph graph
    that routes the question, calls tools, synthesizes with Claude, verifies
    claims, and returns a cited response.
    """
    logger.info(
        "Processing chat  pid=%s  user=%s  msg_len=%d",
        request.pid,
        request.auth_user,
        len(request.message),
    )

    # Build a summary of which context fields arrived — useful for debugging
    # Step 4 (PatientContextService.php) to confirm PHP is sending data correctly.
    ctx = request.context
    context_summary = (
        f"encounters={len(ctx.encounters)}, "
        f"meds={len(ctx.medications)}, "
        f"problems={len(ctx.problems)}, "
        f"labs={len(ctx.labs)}, "
        f"allergies={len(ctx.allergies)}"
    )

    return ChatResponse(
        answer=(
            f"[Python echo] pid={request.pid} | "
            f"user={request.auth_user} | "
            f"msg='{request.message}' | "
            f"context: {context_summary}"
        ),
        verification_status="pass",
        # The warning tells whoever is testing that this is still the stub,
        # not a real agent response.
        warnings=["Step 2 stub — LangGraph agent not yet connected"],
    )
