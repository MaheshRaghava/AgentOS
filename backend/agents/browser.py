"""
Browser agent — fetches and extracts content from a specific URL.
Falls back to http_fetch if Playwright is not installed.
Called by dispatcher when task.worker == WorkerType.BROWSER
"""
from config import settings
from graph.models import Task
from tools.http_fetch import http_fetch
from agents.base import BaseAgent

BROWSER_PROMPT = """You are a web content analyst. Extract the most relevant information from the page content below.

TASK: {description}
PAGE URL: {url}

PAGE CONTENT:
{content}

Extract and summarize:
- The main topic or purpose of the page
- Key facts, data, or information relevant to the task
- Any important links or references mentioned

Be concise and factual.
"""


class BrowserAgent(BaseAgent):

    def __init__(self):
        super().__init__()  # BaseAgent handles model chain
        self._playwright_available = False
        self._check_playwright()

    def _check_playwright(self):
        try:
            import playwright
            self._playwright_available = True
            print("[Browser] Playwright available ✓")
        except ImportError:
            print("[Browser] Playwright not installed — using http_fetch fallback")

    async def run(self, task: Task) -> str:
        print(f"[Browser] Starting: {task.name}")

        # Extract URL from task description if present
        url = self._extract_url(task.description)

        if not url:
            return f"[Browser] No URL found in task description: {task.description}"

        # Fetch page content
        if self._playwright_available:
            content = await self._fetch_with_playwright(url)
        else:
            content = await http_fetch(url)

        if not content:
            return f"[Browser] Could not fetch content from {url}"

        # Summarize with Gemini (using fallback)
        prompt = BROWSER_PROMPT\
            .replace("{description}", task.description)\
            .replace("{url}", url)\
            .replace("{content}", content[:8000])

        output = await self.generate_with_fallback(prompt)
        
        print(f"[Browser] Done: {task.name}")
        return output

    def _extract_url(self, text: str) -> str:
        """Pull the first URL out of the task description."""
        import re
        match = re.search(r'https?://[^\s"\'<>]+', text)
        return match.group(0) if match else ""

    async def _fetch_with_playwright(self, url: str) -> str:
        """Use Playwright for JS-rendered pages."""
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(url, timeout=15000)
                await page.wait_for_load_state("networkidle", timeout=10000)
                content = await page.inner_text("body")
                await browser.close()
                return content[:10000]
        except Exception as e:
            print(f"[Browser] Playwright error: {e} — falling back to http_fetch")
            return await http_fetch(url)


browser_agent = BrowserAgent()

async def run_browser(task: Task) -> str:
    return await browser_agent.run(task)