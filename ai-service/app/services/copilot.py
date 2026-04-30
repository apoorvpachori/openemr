import logging

from app.agent.graph import build_graph
from app.models.chat import ChatRequest, ChatResponse, Citation
from app.tools.patient_tools import make_patient_tools

logger = logging.getLogger("copilot.service")


async def handle_chat(request: ChatRequest) -> ChatResponse:
    logger.info(
        "Processing chat  pid=%s  user=%s  msg_len=%d",
        request.pid,
        request.auth_user,
        len(request.message),
    )

    # Tools are scoped to this patient — pid and token baked into closures.
    tools = make_patient_tools(request.pid, request.internal_token)

    # Build the outer graph (agent → verify → sanitize/fallback).
    graph = build_graph(tools)

    result = await graph.ainvoke(
        {"messages": [("user", request.message)]},
        config={
            "run_name": "clinical-copilot-query",
            "metadata": {"auth_user": request.auth_user, "pid": request.pid},
            "tags": ["patient-query", "clinical-copilot"],
        },
    )

    # Citations: one entry per tool that was actually called during this run.
    citations = [
        Citation(type=name.replace("get_", "").replace("_", " "), title=name)
        for name in result.get("tool_results", {}).keys()
    ]

    return ChatResponse(
        answer=result["answer"],
        citations=citations,
        verification_status=result.get("verification_status", "pass"),
        warnings=result.get("warnings", []),
    )
