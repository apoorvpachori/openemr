"""
CopilotService — business logic layer.

Routes are thin HTTP handlers. This module owns what actually happens with a
request. Right now that's a tool-probe stub. In Step 5 this becomes a LangGraph
agent invocation.

Keeping logic here (not in the route) means:
- Routes stay readable (just HTTP in/out)
- This service can be tested directly without spinning up HTTP
- Swapping the stub for the real agent requires changing only this file
"""

import logging

from app.models.chat import ChatRequest, ChatResponse
from app.tools.patient_tools import make_patient_tools

logger = logging.getLogger("copilot.service")


async def handle_chat(request: ChatRequest) -> ChatResponse:
    """
    Process a chat request and return a response.

    Step 4 (now): calls all six patient data tools to verify the HMAC proxy
    pipeline works end-to-end. Returns a summary of each tool's status so you
    can confirm real data is flowing before wiring up the LangGraph agent.

    Step 5: replaced with `await agent.run(request)` — a full LangGraph graph
    that routes the question, calls the relevant tools, synthesizes with Claude,
    verifies claims, and returns a cited response.
    """
    logger.info(
        "Processing chat  pid=%s  user=%s  msg_len=%d",
        request.pid,
        request.auth_user,
        len(request.message),
    )

    # Build tools scoped to this request's pid and auth token.
    # The closures ensure the LLM (in Step 5) cannot change which patient
    # is queried — pid and token are baked in at this point.
    tools = make_patient_tools(request.pid, request.internal_token)

    # Call every tool to verify the HMAC proxy works for all data types.
    # In Step 5 only the relevant tools run (selected by the router node).
    tool_statuses: dict[str, str] = {}
    for tool_fn in tools:
        result = await tool_fn.ainvoke({})
        tool_statuses[tool_fn.name] = result.get("status", "unknown")

    status_line = ", ".join(f"{k}={v}" for k, v in tool_statuses.items())
    all_ok = all(s in ("ok", "no_data") for s in tool_statuses.values())

    return ChatResponse(
        answer=(
            f"[Step 4 stub] pid={request.pid} | {status_line}\n\n"
            f"Message received: '{request.message}'\n"
            f"{'All tools reachable — ready for Step 5.' if all_ok else 'Some tools failed — check Python logs.'}"
        ),
        verification_status="pass" if all_ok else "fail",
        warnings=["Step 4 stub — LangGraph agent not yet connected"],
    )
