from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from app.agent.prompts import SYSTEM_PROMPT


def build_agent(tools: list):
    """
    Build and return a compiled LangGraph ReAct agent scoped to this request's tools.

    Called once per request — the tools passed in already have the patient's
    pid and HMAC token baked into their closures, so the agent is automatically
    scoped to the correct patient without any extra wiring.
    """
    llm = ChatOpenAI(model="gpt-4o", temperature=0, max_tokens=1024)

    return create_react_agent(
        model=llm,
        tools=tools,
        prompt=SystemMessage(content=SYSTEM_PROMPT),
    )
