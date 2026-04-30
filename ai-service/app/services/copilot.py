import logging

from langchain_core.messages import ToolMessage

from app.agent.graph import build_agent
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

    # Step 1: create tools scoped to this patient.
    # The closures lock in pid + internal_token — the agent cannot query a different patient.
    tools = make_patient_tools(request.pid, request.internal_token)

    # Step 2: build the agent with those tools and run it.
    agent = build_agent(tools)
    result = await agent.ainvoke({"messages": [("user", request.message)]})

    # Step 3: the last message in the result is always the agent's final answer.
    answer = result["messages"][-1].content

    # Step 4: extract which tools were actually called during this run.
    # ToolMessages are the responses from tool calls — their .name is the tool name.
    # This gives us a simple citation list showing what data the answer drew from.
    tools_called = [
        msg.name
        for msg in result["messages"]
        if isinstance(msg, ToolMessage)
    ]
    citations = [
        Citation(type=name.replace("get_", "").replace("_", " "), title=name)
        for name in tools_called
    ]

    return ChatResponse(
        answer=answer,
        citations=citations,
        verification_status="pass",
        warnings=[],
    )
