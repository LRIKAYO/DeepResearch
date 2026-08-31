import os

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from langchain_core.runnables.config import RunnableConfig
from langchain_openai import ChatOpenAI

from .graph import build_graph
from .web_search import build_web_search_tool


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def create_model() -> ChatOpenAI:
    return ChatOpenAI(
        api_key=require_env("SILICONFLOW_API_KEY"),
        base_url=require_env("SILICONFLOW_BASE_URL"),
        model=require_env("SILICONFLOW_MODEL"),
        temperature=0,
    )


def create_web_search():
    return build_web_search_tool(api_key=require_env("TAVILY_API_KEY"))


def create_writer(model: Runnable) -> Runnable:
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a research report writer. "
                "Write a concise and accurate report based on the evidence.",
            ),
            (
                "human",
                """
Research Query:
{research_query}

Evidence:
{evidence}

Generate the final research report.
""",
            ),
        ]
    )
    return prompt | model | StrOutputParser()


def create_runtime(config: RunnableConfig | None = None):
    """Build the graph registered by the LangGraph Server."""
    model = create_model()
    return build_graph(
        researcher_model=model,
        tool=create_web_search(),
        writer_impl=create_writer(model),
    )
