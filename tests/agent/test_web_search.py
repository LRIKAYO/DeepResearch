from researchflow.agent.web_search import build_web_search_tool


class FakeTavilyClient:

    def __init__(self):
        self.calls = []


    def search(
        self,
        query,
        max_results,
        search_depth,
    ):
        self.calls.append(
            {
                "query": query,
                "max_results": max_results,
                "search_depth": search_depth,
            }
        )

        return {
            "results": [
                {
                    "url": "https://a.com",
                    "content": "first result",
                },
                {
                    "url": "https://b.com",
                    "content": "second result",
                },
            ]
        }


def test_web_search_tool_returns_evidence_from_fake_tavily():

    fake_client = FakeTavilyClient()


    tool = build_web_search_tool(
        client=fake_client,
    )


    result = tool.invoke(
        {
            "query": "  LangGraph State  ",
        }
    )


    # 1. Tool 名称
    assert tool.name == "web_search"


    # 2. 输出只包含 Evidence 字段
    assert result == [
        {
            "source": "https://a.com",
            "content": "first result",
        },
        {
            "source": "https://b.com",
            "content": "second result",
        },
    ]


    # 3. Provider 参数
    assert fake_client.calls == [
        {
            "query": "LangGraph State",
            "max_results": 3,
            "search_depth": "basic",
        }
    ]
