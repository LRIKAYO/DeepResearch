import os

from langgraph_sdk import get_sync_client


API_URL = os.getenv("RESEARCHFLOW_API_URL", "http://127.0.0.1:2024")
ASSISTANT_ID = "researchflow"
USER_ID = os.getenv("RESEARCHFLOW_USER_ID")
PROJECT_ID = os.getenv("RESEARCHFLOW_PROJECT_ID")


def run_context() -> dict:
    """Agent runs are scoped by immutable context, not by model arguments."""

    if not USER_ID or not PROJECT_ID:
        raise SystemExit(
            "Set RESEARCHFLOW_USER_ID and RESEARCHFLOW_PROJECT_ID "
            "(an existing Project) before running the smoke test."
        )
    return {
        "knowledge_scope": {
            "user_id": USER_ID,
            "project_id": PROJECT_ID,
        }
    }


def node_updates(events, node_name):
    for event in events:
        if event.event != "updates" or not isinstance(event.data, dict):
            continue
        update = event.data.get(node_name)
        if isinstance(update, dict):
            yield update


def update_node_names(events):
    return [
        sorted(event.data)
        for event in events
        if event.event == "updates" and isinstance(event.data, dict)
    ]


def state_after_run(client, thread_id):
    state = client.threads.get_state(thread_id)["values"]
    report = state.get("report")
    if not isinstance(report, str) or not report.strip():
        raise AssertionError("checkpoint state has no final report")
    if final_message_content(state) != report:
        raise AssertionError("final AIMessage does not contain the report")
    return state


def streamed_output(events):
    values = [
        event.data
        for event in events
        if event.event == "values" and isinstance(event.data, dict)
    ]
    if not values:
        raise AssertionError("stream did not include a values event")
    output = values[-1]
    report = output.get("report")
    if not isinstance(report, str) or not report.strip():
        raise AssertionError("streamed output has no final report")
    if final_message_content(output) != report:
        raise AssertionError("streamed final AIMessage does not contain the report")


def final_message_content(state):
    messages = state.get("messages")
    if not isinstance(messages, list) or not messages:
        return None
    last_message = messages[-1]
    if not isinstance(last_message, dict):
        return None
    return last_message.get("content")


def main():
    client = get_sync_client(url=API_URL, api_key=None)
    if not client.assistants.search(graph_id=ASSISTANT_ID):
        raise AssertionError(f"assistant is not registered: {ASSISTANT_ID}")

    thread_id = client.threads.create()["thread_id"]
    research_events = list(
        client.runs.stream(
            thread_id,
            ASSISTANT_ID,
            input={
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Use web_search to find the official LangGraph documentation "
                            "about State, then give a two-sentence Chinese summary."
                        ),
                    }
                ]
            },
            context=run_context(),
            stream_mode=["updates", "values"],
        )
    )
    evidence_updates = list(node_updates(research_events, "execute_tool"))
    if not evidence_updates:
        raise AssertionError(
            "research run never reached execute_tool; "
            f"streamed update nodes: {update_node_names(research_events)}"
        )
    streamed_output(research_events)
    research_state = state_after_run(client, thread_id)
    if not research_state.get("evidence"):
        raise AssertionError(
            "execute_tool ran but checkpoint state has no valid Evidence"
        )
    if not research_state.get("sub_questions"):
        raise AssertionError("planner did not write sub_questions into Graph State")
    if "verification" not in research_state:
        raise AssertionError("verifier did not record any citation verdicts")

    no_tool_events = list(
        client.runs.stream(
            thread_id,
            ASSISTANT_ID,
            input={
                "messages": [
                    {
                        "role": "user",
                        "content": "Do not call any tool. Reply only: NO_TOOL_CONFIRMATION",
                    }
                ]
            },
            context=run_context(),
            stream_mode=["updates", "values"],
        )
    )
    if list(node_updates(no_tool_events, "execute_tool")):
        raise AssertionError("no-tool run unexpectedly executed web_search")

    streamed_output(no_tool_events)
    final_state = state_after_run(client, thread_id)
    if final_state.get("evidence") != []:
        raise AssertionError("old Evidence leaked into the no-tool run")
    if "thread_id" in final_state:
        raise AssertionError("thread_id must not enter Graph State")

    print(
        {
            "api_url": API_URL,
            "assistant_id": ASSISTANT_ID,
            "thread_id": thread_id,
            "report": final_state["report"],
        }
    )


if __name__ == "__main__":
    main()
