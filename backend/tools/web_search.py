"""
web_search.py — Tavily API wrapper.

Updated to return URLs alongside content so researcher.py
can fetch full page content and synthesizer.py can cite sources.
"""
from typing import Any

from config import settings


async def web_search(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """
    Search the web using Tavily.
    Returns list of {title, url, content} dicts.
    Falls back to mock results if no API key set.
    """
    if not settings.tavily_api_key:
        print("[WebSearch] No Tavily key — returning mock results")
        return [
            {
                "title":   f"Mock result for: {query}",
                "url":     "https://example.com",
                "content": f"Mock result because TAVILY_API_KEY is not set. Query: {query}",
            }
        ]

    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=settings.tavily_api_key)

        response = client.search(
            query=query,
            max_results=max_results,
            search_depth="basic",
            include_answer=False,
            include_raw_content=False,
        )

        results = []
        for r in response.get("results", []):
            results.append({
                "title":   r.get("title", ""),
                "url":     r.get("url", ""),
                "content": r.get("content", ""),
                # score helps researcher decide which URLs are worth fetching
                "score":   r.get("score", 0.0),
            })

        # Sort by relevance score descending
        results.sort(key=lambda x: x.get("score", 0), reverse=True)

        print(f"[WebSearch] '{query[:50]}' → {len(results)} results")
        return results

    except Exception as e:
        print(f"[WebSearch] Error: {e}")
        return [{"title": "Search failed", "url": "", "content": str(e), "score": 0}]


def format_results_for_llm(results: list[dict]) -> str:
    """
    Basic formatter — still used by other parts of the codebase.
    Researcher now uses its own _format_enriched_results instead.
    """
    if not results:
        return "No search results found."

    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}")
        lines.append(f"   URL: {r['url']}")
        lines.append(f"   {r.get('content', '')[:300]}")
        lines.append("")
    return "\n".join(lines)
