from typing import TypedDict


class CopilotState(TypedDict):
    """
    Shared state that flows through every node in the outer graph.

    messages     — the initial user message, passed into the inner ReAct agent
    answer       — the agent's final answer text, set by the agent node
    tool_results — raw data returned by each tool, keyed by tool name;
                   used by the verify node to check every claim in the answer
    verification_status — "pass" | "partial" | "fail", set by the verify node
    unsupported_claims  — specific claims the verifier flagged, set by verify
    warnings     — human-readable warnings forwarded to the chat panel
    """

    messages: list
    answer: str
    tool_results: dict
    verification_status: str
    unsupported_claims: list[str]
    warnings: list[str]
