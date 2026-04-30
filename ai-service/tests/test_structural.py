"""
Structural tests — fully mocked, no real LLM or network calls.

What these test:
  - ChatResponse and VerificationResult always have the correct shape/types
  - The graph routes correctly for each verification status
  - The sanitize node appends a warning (not replaces the answer)
  - The fallback node replaces the answer entirely
  - The verify node is skipped when no tools were called
  - tool_results dict is keyed by tool name

All LLM and tool calls are mocked. These tests run in milliseconds and never
require OPENAI_API_KEY or a running service.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from app.agent.graph import build_graph
from app.agent.verify import VerificationResult
from app.models.chat import ChatResponse, Citation


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_inner_mock(answer: str, tool_name: str = None, tool_data: dict = None) -> AsyncMock:
    """
    Build a mock inner_agent whose ainvoke() returns controlled messages.

    If tool_name is provided, the message list will include a ToolMessage before
    the final AIMessage — this simulates a run where the agent called a tool.
    """
    msgs = []
    if tool_name and tool_data is not None:
        msgs.append(
            ToolMessage(
                content=json.dumps(tool_data),
                name=tool_name,
                tool_call_id="mock-call-1",
            )
        )
    msgs.append(AIMessage(content=answer))

    mock_inner = AsyncMock()
    mock_inner.ainvoke.return_value = {"messages": msgs}
    return mock_inner


async def _run_graph(mock_inner: AsyncMock, verify_result: VerificationResult) -> dict:
    """
    Patch both the inner agent and the verify call, build the graph, run it.
    Returns the final state dict.
    """
    mock_verify = AsyncMock(return_value=verify_result)
    with (
        patch("app.agent.graph.create_react_agent", return_value=mock_inner),
        patch("app.agent.graph.verify_response", mock_verify),
    ):
        graph = build_graph(tools=[])
        return await graph.ainvoke({"messages": [("user", "test question")]})


# ── ChatResponse shape ────────────────────────────────────────────────────────

@pytest.mark.unit
class TestChatResponseShape:
    def test_required_fields_present(self):
        r = ChatResponse(
            answer="Patient takes Norvasc.",
            citations=[],
            verification_status="pass",
            warnings=[],
        )
        assert r.answer == "Patient takes Norvasc."
        assert r.citations == []
        assert r.verification_status == "pass"
        assert r.warnings == []

    def test_all_valid_verification_statuses_accepted(self):
        for status in ("pass", "partial", "fail"):
            r = ChatResponse(answer="x", verification_status=status)
            assert r.verification_status == status

    def test_citations_default_to_empty_list(self):
        r = ChatResponse(answer="x", verification_status="pass")
        assert r.citations == []

    def test_warnings_default_to_empty_list(self):
        r = ChatResponse(answer="x", verification_status="pass")
        assert r.warnings == []

    def test_citation_model(self):
        c = Citation(type="medication", title="Norvasc", index=0)
        assert c.type == "medication"
        assert c.title == "Norvasc"
        assert c.index == 0

    def test_citation_index_optional(self):
        c = Citation(type="problem", title="HTN")
        assert c.index is None


# ── VerificationResult model ──────────────────────────────────────────────────

@pytest.mark.unit
class TestVerificationResult:
    def test_pass_status(self):
        vr = VerificationResult(status="pass")
        assert vr.status == "pass"
        assert vr.unsupported_claims == []

    def test_partial_with_claims(self):
        vr = VerificationResult(status="partial", unsupported_claims=["wrong dosage"])
        assert vr.status == "partial"
        assert "wrong dosage" in vr.unsupported_claims

    def test_fail_status(self):
        vr = VerificationResult(status="fail", unsupported_claims=["claim A", "claim B"])
        assert len(vr.unsupported_claims) == 2

    def test_reasoning_defaults_to_empty_string(self):
        vr = VerificationResult(status="pass")
        assert vr.reasoning == ""


# ── Graph routing ─────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestGraphRouting:
    """
    Test that state flows to the correct node for each verification outcome.
    All LLM calls are mocked — only the routing logic is exercised.
    """

    async def test_pass_returns_answer_unchanged(self):
        mock_inner = _make_inner_mock(
            "The patient takes Norvasc.",
            tool_name="get_medications",
            tool_data={"status": "ok", "data": [{"title": "Norvasc"}]},
        )
        result = await _run_graph(mock_inner, VerificationResult(status="pass"))

        assert result["answer"] == "The patient takes Norvasc."
        assert result["verification_status"] == "pass"
        assert result["warnings"] == []
        assert "⚠️" not in result["answer"]

    async def test_partial_appends_warning_to_answer(self):
        original_answer = "The patient takes Norvasc and aspirin."
        mock_inner = _make_inner_mock(
            original_answer,
            tool_name="get_medications",
            tool_data={"status": "ok", "data": [{"title": "Norvasc"}]},
        )
        result = await _run_graph(
            mock_inner,
            VerificationResult(status="partial", unsupported_claims=["aspirin"]),
        )

        assert result["verification_status"] == "partial"
        # Original answer is preserved (not replaced)
        assert original_answer in result["answer"]
        # Warning text is appended
        assert "⚠️" in result["answer"]
        assert "aspirin" in result["answer"]

    async def test_fail_replaces_answer_entirely(self):
        mock_inner = _make_inner_mock(
            "The patient takes a completely fabricated drug called XYZ-9000.",
            tool_name="get_medications",
            tool_data={"status": "ok", "data": []},
        )
        result = await _run_graph(
            mock_inner,
            VerificationResult(status="fail", unsupported_claims=["XYZ-9000"]),
        )

        assert result["verification_status"] == "fail"
        # Original hallucinated answer is gone
        assert "XYZ-9000" not in result["answer"]
        # Safe fallback message is present
        assert "review" in result["answer"].lower() or "unable" in result["answer"].lower()

    async def test_partial_warnings_list_contains_message(self):
        mock_inner = _make_inner_mock(
            "The patient takes Norvasc and fake_drug.",
            tool_name="get_medications",
            tool_data={"status": "ok", "data": [{"title": "Norvasc"}]},
        )
        result = await _run_graph(
            mock_inner,
            VerificationResult(status="partial", unsupported_claims=["fake_drug"]),
        )

        assert len(result["warnings"]) == 1
        assert "fake_drug" in result["warnings"][0]

    async def test_pass_warnings_list_is_empty(self):
        mock_inner = _make_inner_mock(
            "The patient takes Norvasc.",
            tool_name="get_medications",
            tool_data={"status": "ok", "data": [{"title": "Norvasc"}]},
        )
        result = await _run_graph(mock_inner, VerificationResult(status="pass"))
        assert result["warnings"] == []


# ── Verify bypass ─────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestVerifyBypass:
    """
    When the agent answers without calling any tools (e.g. a greeting),
    the verify node should skip the LLM call and pass through immediately.
    """

    async def test_no_tools_called_skips_verify_llm(self):
        # No tool_name → no ToolMessage → tool_results will be empty
        mock_inner = _make_inner_mock("Hello! How can I help you today?")
        mock_verify = AsyncMock()

        with (
            patch("app.agent.graph.create_react_agent", return_value=mock_inner),
            patch("app.agent.graph.verify_response", mock_verify),
        ):
            graph = build_graph(tools=[])
            result = await graph.ainvoke({"messages": [("user", "hello")]})

        # verify_response should never have been called
        mock_verify.assert_not_called()
        assert result["verification_status"] == "pass"
        assert result["answer"] == "Hello! How can I help you today?"

    async def test_no_tools_called_warnings_empty(self):
        mock_inner = _make_inner_mock("Hello!")
        with (
            patch("app.agent.graph.create_react_agent", return_value=mock_inner),
            patch("app.agent.graph.verify_response", AsyncMock()),
        ):
            graph = build_graph(tools=[])
            result = await graph.ainvoke({"messages": [("user", "hi")]})

        assert result["warnings"] == []


# ── tool_results extraction ───────────────────────────────────────────────────

@pytest.mark.unit
class TestToolResultsExtraction:
    """The agent node must key tool_results by tool function name."""

    async def test_tool_results_keyed_by_tool_name(self):
        tool_data = {"status": "ok", "data": [{"title": "Norvasc"}]}
        mock_inner = _make_inner_mock(
            "Patient takes Norvasc.",
            tool_name="get_medications",
            tool_data=tool_data,
        )
        mock_verify = AsyncMock(return_value=VerificationResult(status="pass"))

        with (
            patch("app.agent.graph.create_react_agent", return_value=mock_inner),
            patch("app.agent.graph.verify_response", mock_verify),
        ):
            graph = build_graph(tools=[])
            result = await graph.ainvoke({"messages": [("user", "meds?")]})

        assert "get_medications" in result["tool_results"]
        assert result["tool_results"]["get_medications"] == tool_data

    async def test_multiple_tool_calls_all_captured(self):
        """If agent calls two tools, both appear in tool_results."""
        meds_data = {"status": "ok", "data": [{"title": "Norvasc"}]}
        labs_data = {"status": "no_data", "message": "No labs on file"}

        msgs = [
            ToolMessage(content=json.dumps(meds_data), name="get_medications", tool_call_id="1"),
            ToolMessage(content=json.dumps(labs_data), name="get_recent_labs", tool_call_id="2"),
            AIMessage(content="Patient takes Norvasc. No labs on file."),
        ]
        mock_inner = AsyncMock()
        mock_inner.ainvoke.return_value = {"messages": msgs}
        mock_verify = AsyncMock(return_value=VerificationResult(status="pass"))

        with (
            patch("app.agent.graph.create_react_agent", return_value=mock_inner),
            patch("app.agent.graph.verify_response", mock_verify),
        ):
            graph = build_graph(tools=[])
            result = await graph.ainvoke({"messages": [("user", "meds and labs?")]})

        assert "get_medications" in result["tool_results"]
        assert "get_recent_labs" in result["tool_results"]
