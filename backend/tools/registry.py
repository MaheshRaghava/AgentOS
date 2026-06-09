"""
Tool registry — updated in Phase 4 to include all tools.
"""
from typing import Any, Callable
import asyncio


class ToolRegistry:

    def __init__(self):
        self._tools: dict[str, Callable] = {}

    def register(self, name: str, fn: Callable) -> None:
        self._tools[name] = fn
        print(f"[Registry] Tool registered: {name}")

    async def call(self, name: str, **kwargs: Any) -> Any:
        fn = self._tools.get(name)
        if not fn:
            raise KeyError(f"Tool '{name}' not found. Available: {list(self._tools.keys())}")
        if asyncio.iscoroutinefunction(fn):
            return await fn(**kwargs)
        else:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, lambda: fn(**kwargs))

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def has(self, name: str) -> bool:
        return name in self._tools


registry = ToolRegistry()

# Import and register tools (move imports inside to avoid circular issues)
try:
    from tools.web_search import web_search
    registry.register("web_search", web_search)
    print("[Registry] web_search registered")
except Exception as e:
    print(f"[Registry] Failed to register web_search: {e}")

try:
    from tools.http_fetch import http_fetch
    registry.register("http_fetch", http_fetch)
    print("[Registry] http_fetch registered")
except Exception as e:
    print(f"[Registry] Failed to register http_fetch: {e}")

try:
    from tools.code_exec import execute_code
    registry.register("execute_code", execute_code)
    print("[Registry] execute_code registered")
except Exception as e:
    print(f"[Registry] Failed to register execute_code: {e}")

try:
    from tools.file_rw import write_file, read_file
    registry.register("write_file", write_file)
    registry.register("read_file", read_file)
    print("[Registry] file_rw registered")
except Exception as e:
    print(f"[Registry] Failed to register file_rw: {e}")

print(f"[Registry] All tools registered: {registry.list_tools()}")