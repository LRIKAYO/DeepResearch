from functools import partial
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import END, START, StateGraph

from .state import AgentInputState, AgentOutputState, AgentState


def normalize_research_query(
    content: object,
) -> str:
    """
    Normalize HumanMessage.content into text-only research_query.

    Supported:
    - str
    - list of text content blocks

    Unsupported:
    - other types
    - empty text   
    """
    
    if isinstance(content, str):
        query = content.strip()

        if not query:
            raise ValueError(
                "research query cannot be empty"
            )
        
        return query

    if isinstance(content, list):
        text_parts = []

        for block in content:
            if not isinstance(block, dict):
                continue
            
            if block.get("type") != "text":
                continue
            
            text = block.get("text")

            if not isinstance(text, str):
                continue

            text = text.strip()

            if text:
                text_parts.append(text) 
            
        if not text_parts:
            raise ValueError(
                "research query contains no valid text blocks"
            )
            
        return "\n\n".join(text_parts)
    raise ValueError(
        "HumanMessage.content must be a string or a list of text blocks"
    )

def researcher(
    state: AgentState,
    researcher_model: Any,
    tool: Any,
) -> dict:
    """
    Researcher node.

    Responsibilities:
    1. Read the latest HumanMessage as research_query.
    2. Bind the available tool schema to the researcher model.
    3. Invoke the researcher model once.
    4. Append the model response to messages.
    """
    
    #取最近一次用户输入作为research_query
    research_query = None

    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            research_query = normalize_research_query(
                message.content
            )

            break
    if research_query is None:
        raise ValueError(
            "researcher requires at least one HumanMessage"
        )
    
    # 此处不会真正执行 Tool。
    model_with_tools = researcher_model.bind_tools(
        [tool],
        parallel_tool_calls=False,
    )

    response = model_with_tools.invoke(
        state["messages"]
    )
    # messages 应由 AgentState 中的 reducer 负责追加，
    # 因此这里只返回本节点产生的新消息。
    return {
        "research_query": research_query,
        "evidence": [],
        "messages": [response],
    }

def route_after_researcher(
    state: AgentState,
) -> Literal["execute_tool", "writer"]:
    """
    Decide where to go after the researcher.

    - tool_calls exists -> execute Tool calls
    - no tool_calls     -> go directly to writer
    """

    last_message = state["messages"][-1]

    if getattr(last_message, "tool_calls", None):
        return "execute_tool"

    return "writer"


def execute_tool(
    state: AgentState,
    tool: Any,
) -> dict:
    """
    Execute one or more calls to the single Tool bound to this graph.

    Tool result is treated as structured Evidence.
    ToolMessage is only execution trace metadata.
    """

    last_message = state["messages"][-1]

    # 1. 最后一条必须是Researcher 产生的AIMessage
    if not isinstance(last_message, AIMessage):
        raise ValueError(
            "execute_tool requires the last message to be an AIMessage"
        )

    tool_calls = last_message.tool_calls

    # 2. 模型至少要生成一次调用。
    if len(tool_calls) == 0:
        raise ValueError(
             "execute_tool requires at least one tool call, but none were found"
        )

    # 3. 先校验所有名称，避免未知 Tool 导致部分外部搜索已发生。
    for tool_call in tool_calls:
        if tool_call["name"] != tool.name:
            raise ValueError(f"Unknown tool: {tool_call['name']}")

    evidence_results = []
    tool_messages = []
    allowed_evidence_fields = {"source", "content", "relevance_note"}
    for tool_call in tool_calls:
        tool_result = tool.invoke(tool_call["args"])

        if not isinstance(tool_result, list):
            raise ValueError("tool must return an Evidence-compatible list")

        for index, evidence in enumerate(tool_result):
            if not isinstance(evidence, dict):
                raise ValueError(
                    f"tool Evidence at index {index} must be a dictionary"
                )

            unexpected_fields = set(evidence) - allowed_evidence_fields
            if unexpected_fields:
                raise ValueError(
                    "tool returned unsupported Evidence fields: "
                    + ", ".join(sorted(map(str, unexpected_fields)))
                )

            for required_field in ("source", "content"):
                if not isinstance(evidence.get(required_field), str):
                    raise ValueError(
                        f"tool Evidence field '{required_field}' must be a string"
                    )

            if (
                "relevance_note" in evidence
                and not isinstance(evidence["relevance_note"], str)
            ):
                raise ValueError(
                    "tool Evidence field 'relevance_note' must be a string when provided"
                )

        evidence_results.extend(tool_result)
        tool_messages.append(
            ToolMessage(
                content="Research evidence collected successfully.",
                tool_call_id=tool_call["id"],
                name=tool_call["name"],
            )
        )

    # 4. Evidence 是业务数据；ToolMessage 只是执行轨迹。
    return {
        "evidence": evidence_results,
        "messages": tool_messages,
    }
   


def writer(
    state: AgentState,
    writer_impl: Any,
) -> dict:
    """
    Generate the final answer from research state.

    
    Writer input boundary:
    - research_query
    - evidence

    ToolMessage content is execution trace only and must not be used
    as research material.
    """

    research_query = state.get("research_query")
    evidence = state.get("evidence", [])

    if research_query is None:
        raise ValueError(
            "writer requires 'research_query' in state"
        )

    #no-tool path is valid:
    #evidence is treated as an empty list.
    if evidence is None:
        evidence = []
    
    report = writer_impl.invoke(
        {
            "research_query": research_query,
            "evidence": evidence,
        }
    )

    if not isinstance(report, str):
        raise ValueError(
            "writer_impl must return a string report"
        )

    return {
        "report": report,
        "messages": [AIMessage(content=report)],
    }



def build_graph(
    researcher_model: Any,
    tool: Any,
    writer_impl: Any,
):
    """
    Build the P1-002 research workflow.

    Flow:

        START
          |
          v
      researcher
        /    \
       /      \
 tool_calls   no tool_calls
     |             |
     v             |
 execute_tool      |
     |             |
     +------> writer
                 |
                 v
                END
    """

    builder = StateGraph(
        AgentState,
        input_schema=AgentInputState,
        output_schema=AgentOutputState,
    )

    # ---------------------------------------------------------
    # Nodes
    # ---------------------------------------------------------

    builder.add_node(
        "researcher",
        partial(
            researcher,
            researcher_model=researcher_model,
            tool=tool,
        ),
    )

    builder.add_node(
        "execute_tool",
        partial(
            execute_tool,
            tool=tool,
        ),
    )

    builder.add_node(
        "writer",
        partial(
            writer,
            writer_impl=writer_impl,
        ),
    )

    # ---------------------------------------------------------
    # Edges
    # ---------------------------------------------------------

    builder.add_edge(
        START,
        "researcher",
    )

    builder.add_conditional_edges(
        "researcher",
        route_after_researcher,
        {
            "execute_tool": "execute_tool",
            "writer": "writer",
        },
    )

    builder.add_edge(
        "execute_tool",
        "writer",
    )

    builder.add_edge(
        "writer",
        END,
    )

    return builder.compile()
