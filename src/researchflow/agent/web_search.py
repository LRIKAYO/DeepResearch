from typing import Any

from langchain_core.tools import tool
from tavily import TavilyClient

from .state import Evidence


def build_web_search_tool(
    api_key: str | None = None,
    client: Any | None = None,
):
    """
    Build Tavily backed web search tool.

    api_key is injected by runtime factory.
    """

    if client is None:
        if api_key is None:
            raise ValueError("web search tool requires a Tavily API key")

        client = TavilyClient(api_key=api_key)


    @tool("web_search")
    def web_search(
        query: str,
    ) -> list[Evidence]:
        """
        Search web and return Evidence list.

        Args:
            query:
                Search query.

        Returns:
            list of Evidence dictionaries.
        """

        if not isinstance(query, str):
            raise ValueError(
                "query must be a string"
            )


        query = query.strip()

        if not query:
            raise ValueError(
                "query cannot be empty"
            )


        response = client.search(
            query=query,
            max_results=3,
            search_depth="basic",
        )

        evidence: list[Evidence] = []

        for result in response.get(
            "results",
            []
        ):
            url = result.get("url")
            content = result.get("content")


            if not isinstance(url, str):
                continue

            if not isinstance(content, str):
                continue


            evidence.append(
                {
                    "source": url,
                    "content": content,
                }
            )


        return evidence


    return web_search
