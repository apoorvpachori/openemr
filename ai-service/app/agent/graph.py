"""
Outer LangGraph graph — wraps the inner ReAct agent and adds verification.

Structure:
    START → agent → verify ──(pass)──────────────→ END
                         │
                         ├──(partial)──→ sanitize → END
                         │
                         └──(fail)─────→ fallback → END

The inner ReAct loop (create_react_agent) lives inside the agent node.
It handles all tool calling and synthesis. Once it produces a final answer,
control passes to the verify node which checks every claim against the raw
tool data before anything reaches the physician.
"""

import json
import logging

from langchain_core.messages import SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import create_react_agent

from app.agent.prompts import SYSTEM_PROMPT
from app.agent.state import CopilotState
from app.agent.verify import VerificationResult, verify_response

logger = logging.getLogger("copilot.agent")


def build_graph(tools: list):
    """
    Build and compile the full clinical co-pilot graph scoped to this request's tools.
    Called once per request — tools already have pid and token baked into their closures.
    """

    llm = ChatOpenAI(model="gpt-4o", temperature=0, max_tokens=1024)

    # ── Inner agent: the full ReAct loop ─────────────────────────────────────
    # create_react_agent handles: model decides tools → tools run → model sees
    # results → model answers (or calls more tools) → loop until final answer.
    inner_agent = create_react_agent(
        model=llm,
        tools=tools,
        prompt=SystemMessage(content=SYSTEM_PROMPT),
    )

    # ── Node 1: agent ────────────────────────────────────────────────────────
    # Runs the full ReAct loop then extracts the answer and raw tool results
    # from the message history so the verify node can work with them.
    async def agent_node(state: CopilotState):
        result = await inner_agent.ainvoke({"messages": state["messages"]})
        msgs = result["messages"]

        # The last message is always the model's final answer.
        answer = msgs[-1].content

        # ToolMessages are the raw responses from each tool call.
        # We key them by tool name so the verifier can look up "medications"
        # and find exactly what the DB returned.
        tool_results: dict = {}
        for msg in msgs:
            if isinstance(msg, ToolMessage):
                try:
                    data = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
                except (json.JSONDecodeError, TypeError):
                    data = {"raw": str(msg.content)}
                tool_results[msg.name] = data

        return {"answer": answer, "tool_results": tool_results}

    # ── Node 2: verify ───────────────────────────────────────────────────────
    # Makes a structured LLM call: "given this raw data, which claims in the
    # answer are not supported?" Returns pass / partial / fail.
    async def verify_node(state: CopilotState):
        # If the agent called no tools (e.g. a greeting), there's nothing to
        # verify against — pass through.
        if not state.get("tool_results"):
            return {
                "verification_status": "pass",
                "unsupported_claims": [],
                "warnings": [],
            }

        result: VerificationResult = await verify_response(
            answer=state["answer"],
            tool_results=state["tool_results"],
        )

        logger.info(
            "Verification result: status=%s unsupported=%s",
            result.status,
            result.unsupported_claims,
        )

        warnings = []
        if result.unsupported_claims:
            warnings.append(
                "The following claims could not be verified against the record: "
                + ", ".join(f'"{c}"' for c in result.unsupported_claims)
            )

        return {
            "verification_status": result.status,
            "unsupported_claims": result.unsupported_claims,
            "warnings": warnings,
        }

    # ── Node 3: sanitize ─────────────────────────────────────────────────────
    # Reached when verification_status == "partial".
    # Appends a clear warning to the answer so the physician knows which
    # specific claims were unverifiable — without silently hiding them.
    async def sanitize_node(state: CopilotState):
        flagged = ", ".join(f'"{c}"' for c in state.get("unsupported_claims", []))
        warning = (
            f"\n\n⚠️ Verification warning: the following could not be confirmed "
            f"directly from the patient record: {flagged}. "
            f"Please verify before acting on this information."
        )
        return {"answer": state["answer"] + warning}

    # ── Node 4: fallback ─────────────────────────────────────────────────────
    # Reached when verification_status == "fail".
    # Replaces the entire answer with a safe message — better to say nothing
    # than to surface an answer the verifier judged fundamentally unreliable.
    async def fallback_node(state: CopilotState):
        return {
            "answer": (
                "I was unable to generate a verified response from this patient's "
                "record. Please review the chart directly."
            ),
            "verification_status": "fail",
        }

    # ── Conditional edge: route on verification result ───────────────────────
    def route_after_verify(state: CopilotState) -> str:
        status = state.get("verification_status", "pass")
        if status == "partial":
            return "sanitize"
        if status == "fail":
            return "fallback"
        return END  # pass → done

    # ── Assemble the graph ───────────────────────────────────────────────────
    graph = StateGraph(CopilotState)

    graph.add_node("agent",    agent_node)
    graph.add_node("verify",   verify_node)
    graph.add_node("sanitize", sanitize_node)
    graph.add_node("fallback", fallback_node)

    graph.add_edge(START,    "agent")
    graph.add_edge("agent",  "verify")
    graph.add_conditional_edges(
        "verify",
        route_after_verify,
        {"sanitize": "sanitize", "fallback": "fallback", END: END},
    )
    graph.add_edge("sanitize", END)
    graph.add_edge("fallback", END)

    return graph.compile()
