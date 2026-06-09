"""
researcher.py — Deep research agent with smart content extraction.

Flow:
  1. DETECT: If simple knowledge question → answer directly (skip all research)
  2. Extract short focused search query from task description
  3. Tavily search → top results with URLs sorted by score
  4. Boost official documentation URLs based on query keywords
  5. If official docs missing, run targeted fallback searches
  6. RE-SORT so official docs are at the TOP before fetching
  7. Fetch full page content from top URLs
  8. Strip nav/ads/footer with BeautifulSoup — keep article body only
  9. Gemini summarizes rich context with source citation instructions
  10. Append sources directly from fetched URLs (guaranteed, no Gemini needed)

Falls back gracefully at every step — no crash if fetch or parse fails.
"""
from graph.models import Task
from tools.registry import registry
from tools.http_fetch import http_fetch
from agents.base import BaseAgent

PAGE_CONTENT_LIMIT = 5000   # chars per page after cleaning

# Simple knowledge questions — answer directly, no research
SIMPLE_KNOWLEDGE_STARTERS = [
    "what is", "who is", "explain", "define", 
    "how does", "what are", "why does", "why is",
    "what does", "how to", "when to", "which is"
]

SIMPLE_KNOWLEDGE_PROMPT = """Answer this question directly and accurately. 
Be concise but informative. Use your knowledge — no need to search the web.

QUESTION: {question}

ANSWER:"""

# Official documentation domains for boosting and fallback
OFFICIAL_DOMAINS = {
    # Python
    "python": {
        "domains": ["docs.python.org"],
        "fallback_query": "Python official documentation"
    },
    # Frontend Frameworks
    "react": {
        "domains": ["react.dev"],
        "fallback_query": "React official documentation react.dev"
    },
    "vue": {
        "domains": ["vuejs.org"],
        "fallback_query": "Vue.js official documentation vuejs.org"
    },
    "angular": {
        "domains": ["angular.dev"],
        "fallback_query": "Angular official documentation angular.dev"
    },
    "nextjs": {
        "domains": ["nextjs.org/docs"],
        "fallback_query": "Next.js official documentation"
    },
    "typescript": {
        "domains": ["typescriptlang.org/docs"],
        "fallback_query": "TypeScript official documentation"
    },
    "javascript": {
        "domains": ["developer.mozilla.org"],
        "fallback_query": "JavaScript MDN Web Docs"
    },
    # AI/ML Frameworks
    "langchain": {
        "domains": ["python.langchain.com"],
        "fallback_query": "LangChain official documentation"
    },
    "openai": {
        "domains": ["platform.openai.com/docs"],
        "fallback_query": "OpenAI official API documentation"
    },
    "huggingface": {
        "domains": ["huggingface.co/docs"],
        "fallback_query": "Hugging Face official documentation"
    },
    # Vector Databases
    "pinecone": {
        "domains": ["docs.pinecone.io"],
        "fallback_query": "Pinecone official documentation docs.pinecone.io"
    },
    "qdrant": {
        "domains": ["qdrant.tech"],
        "fallback_query": "Qdrant official documentation qdrant.tech"
    },
    "milvus": {
        "domains": ["milvus.io"],
        "fallback_query": "Milvus official documentation milvus.io"
    },
    "weaviate": {
        "domains": ["weaviate.io"],
        "fallback_query": "Weaviate official documentation weaviate.io"
    },
    "chroma": {
        "domains": ["docs.trychroma.com"],
        "fallback_query": "Chroma official documentation docs.trychroma.com"
    },
    # Cloud/DevOps
    "aws": {
        "domains": ["aws.amazon.com/pricing", "calculator.aws"],
        "fallback_query": "AWS official pricing page aws.amazon.com"
    },
    "azure": {
        "domains": ["azure.microsoft.com/en-us/pricing"],
        "fallback_query": "Azure official pricing page"
    },
    "gcp": {
        "domains": ["cloud.google.com/pricing"],
        "fallback_query": "Google Cloud official pricing page"
    },
    "kubernetes": {
        "domains": ["kubernetes.io/docs"],
        "fallback_query": "Kubernetes official documentation"
    },
    "terraform": {
        "domains": ["developer.hashicorp.com/terraform"],
        "fallback_query": "Terraform official documentation"
    },
    "redis": {
        "domains": ["redis.io/docs"],
        "fallback_query": "Redis official documentation"
    },
    "docker": {
        "domains": ["docs.docker.com"],
        "fallback_query": "Docker official documentation"
    },
    # Tools & Databases
    "fastapi": {
        "domains": ["fastapi.tiangolo.com"],
        "fallback_query": "FastAPI official documentation"
    },
    "mongodb": {
        "domains": ["docs.mongodb.com"],
        "fallback_query": "MongoDB official documentation"
    },
    "postgresql": {
        "domains": ["postgresql.org"],
        "fallback_query": "PostgreSQL official documentation"
    },
}

RESEARCHER_PROMPT = """You are a research assistant. Based on the search results and page content below, write a clear and factual summary.

TASK: {description}

SEARCH RESULTS AND PAGE CONTENT:
{search_results}

Instructions:
- Write a focused 3-4 paragraph summary covering key facts, features, pros, and cons relevant to the task.
- Be specific — include actual data points, version numbers, benchmarks, or examples from the sources.
- Prefer information from official documentation over blogs.
- Do NOT add a Sources section — it will be added automatically after your summary.

FORMAT:
[Your 3-4 paragraph summary only — no Sources section needed]
"""

QUERY_EXTRACT_PROMPT = """Extract a short, focused 5-7 word web search query from this task description.
Return ONLY the search query, nothing else.

Task: {description}

Query:"""


class ResearcherAgent(BaseAgent):

    async def run(self, task: Task) -> str:
        print(f"[Researcher] Starting: {task.name}")

        # Step 0 — Check if this is a simple knowledge question
        if self._is_simple_knowledge_question(task.description):
            print(f"[Researcher] Simple knowledge question — answering directly (no web search)")
            prompt = SIMPLE_KNOWLEDGE_PROMPT.replace("{question}", task.description)
            output = await self.generate_with_fallback(prompt)
            print(f"[Researcher] Done: {task.name} ({len(output)} chars) [direct answer]")
            return output

        # Step 1 — extract a clean search query
        query = await self._extract_query(task.description)
        print(f"[Researcher] Search query: '{query}'")

        # Step 2 — web search
        results = await registry.call(
            "web_search",
            query=query,
            max_results=5,
        )

        if not results:
            results = []

        # Step 3 — boost official documentation URLs
        results = self._boost_official_docs(query, results)

        # Step 4 — targeted fallback searches for missing official docs
        results = await self._add_missing_official_docs(query, results)

        # Step 5 — RE-SORT: Move official docs to the TOP before fetching
        results = self._prioritize_official_docs_for_fetching(results)

        # Step 6 — fetch and clean full page content from top URLs
        enriched = await self._enrich_with_page_content(results)

        # Step 7 — format for LLM
        formatted = self._format_enriched_results(enriched)

        # Step 8 — summarize with model fallback chain
        prompt = RESEARCHER_PROMPT\
            .replace("{description}", task.description)\
            .replace("{search_results}", formatted)

        output = await self.generate_with_fallback(prompt)

        # Step 9 — Append sources directly from fetched URLs (guaranteed, no Gemini needed)
        sources_block = self._build_sources_block(enriched)
        if sources_block:
            output += sources_block
            source_count = len(sources_block.split('\n')) - 1  # Subtract the header line
            print(f"[Researcher] Added sources block with {source_count} sources")

        print(f"[Researcher] Done: {task.name} ({len(output)} chars)")
        return output

    # ------------------------------------------------------------------
    # Helper: Build sources block from fetched URLs
    # ------------------------------------------------------------------

    def _build_sources_block(self, results: list[dict]) -> str:
        """
        Build a Sources section directly from fetched result URLs.
        Guaranteed to have real URLs — doesn't depend on Gemini formatting.
        """
        lines = []
        seen_urls = set()
        
        for r in results:
            url = r.get("url", "")
            title = r.get("title", "")
            
            if not url or not url.startswith("http"):
                continue
                
            if url in seen_urls:
                continue
            
            # Skip GitHub repo root pages — not useful as sources
            if "github.com" in url and "/blob/" not in url and "/wiki/" not in url:
                continue
            seen_urls.add(url)
            
            if title and len(title) > 3:
                lines.append(f"- [{title}]({url})")
            else:
                lines.append(f"- {url}")

        if not lines:
            return ""

        return "\n\n**Sources:**\n" + "\n".join(lines)

    # ------------------------------------------------------------------
    # Step 0 — Detect simple knowledge questions
    # ------------------------------------------------------------------

    def _is_simple_knowledge_question(self, text: str) -> bool:
        """
        Detect if this is a simple knowledge question that doesn't need web search.
        Examples: "What is Python decorator?", "Who is Elon Musk?", "Explain inheritance"
        """
        text_lower = text.lower().strip()
        
        # Remove trailing punctuation
        text_lower = text_lower.rstrip('?.')

        # Check if it starts with a simple question starter
        starts_with_question = any(
            text_lower.startswith(starter) for starter in SIMPLE_KNOWLEDGE_STARTERS
        )

        if not starts_with_question:
            return False

        # Check if it's short (less than 15 words)
        word_count = len(text.split())
        if word_count > 15:
            return False

        # Check for keywords that indicate need for current/research info
        research_keywords = [
            "latest", "current", "2025", "2026", "trend", "compare", 
            "vs", "versus", "pricing", "cost", "benchmark", "top",
            "best", "newest", "recent", "news", "update"
        ]
        
        for keyword in research_keywords:
            if keyword in text_lower:
                return False

        return True

    # ------------------------------------------------------------------
    # Step 1 — extract short search query
    # ------------------------------------------------------------------

    async def _extract_query(self, description: str) -> str:
        """
        Use Gemini to extract a focused 5-7 word search query.
        Falls back to first 60 chars of description if it fails.
        """
        if len(description.split()) <= 8:
            return description

        try:
            prompt = QUERY_EXTRACT_PROMPT.replace("{description}", description[:300])
            query = await self.generate_with_fallback(prompt)
            query = query.strip().strip('"').strip("'").split('\n')[0].strip()
            if len(query) > 5:
                return query
        except Exception as e:
            print(f"[Researcher] Query extraction failed: {e}")

        return description[:60].strip()

    # ------------------------------------------------------------------
    # Step 2 — boost official documentation URLs
    # ------------------------------------------------------------------

    def _get_relevant_docs(self, query: str) -> list[tuple[str, str, str]]:
        """
        Returns list of (keyword, domain, fallback_query) for matching docs.
        """
        query_lower = query.lower()
        relevant = []
        for keyword, info in OFFICIAL_DOMAINS.items():
            if keyword in query_lower:
                for domain in info["domains"]:
                    relevant.append((keyword, domain, info["fallback_query"]))
        return relevant

    def _boost_official_docs(self, query: str, results: list[dict]) -> list[dict]:
        """
        Boost URLs from official documentation to the top of results.
        """
        relevant_docs = self._get_relevant_docs(query)
        if not relevant_docs:
            return results

        preferred_domains = [d for _, d, _ in relevant_docs]

        def score_result(result: dict) -> int:
            url = result.get("url", "").lower()
            for domain in preferred_domains:
                if domain in url:
                    return 100
            return 0

        results.sort(key=score_result, reverse=True)

        for i, r in enumerate(results[:2]):
            if score_result(r) == 100:
                print(f"[Researcher] Boosted official doc: {r.get('url', '')[:60]}")

        return results

    # ------------------------------------------------------------------
    # Step 3 — targeted fallback searches for missing official docs
    # ------------------------------------------------------------------

    async def _add_missing_official_docs(self, query: str, results: list[dict]) -> list[dict]:
        """
        If official docs are missing from search results, run targeted searches.
        """
        relevant_docs = self._get_relevant_docs(query)
        if not relevant_docs:
            return results

        existing_urls = set(r.get("url", "").lower() for r in results)
        missing_docs = []

        for keyword, domain, fallback_query in relevant_docs:
            found = any(domain in url for url in existing_urls)
            if not found:
                missing_docs.append((keyword, domain, fallback_query))

        if not missing_docs:
            return results

        for keyword, domain, fallback_query in missing_docs:
            print(f"[Researcher] Running targeted search for {keyword} docs: '{fallback_query}'")
            try:
                targeted_results = await registry.call(
                    "web_search",
                    query=fallback_query,
                    max_results=2,
                )
                if targeted_results:
                    for tr in targeted_results:
                        tr_url = tr.get("url", "").lower()
                        if domain in tr_url and tr_url not in existing_urls:
                            results.append(tr)
                            existing_urls.add(tr_url)
                            print(f"[Researcher] Added official doc: {tr.get('url', '')[:60]}")
            except Exception as e:
                print(f"[Researcher] Targeted search failed for {keyword}: {e}")

        return results

    # ------------------------------------------------------------------
    # Step 4 — RE-SORT: Prioritize official docs for fetching
    # ------------------------------------------------------------------

    def _prioritize_official_docs_for_fetching(self, results: list[dict]) -> list[dict]:
        """
        Re-sort results so official documentation URLs are at the TOP
        before fetching page content.
        """
        if not results:
            return results

        official = []
        others = []

        all_official_domains = set()
        for info in OFFICIAL_DOMAINS.values():
            for domain in info["domains"]:
                all_official_domains.add(domain)

        for r in results:
            url = r.get("url", "").lower()
            is_official = any(domain in url for domain in all_official_domains)
            if is_official:
                official.append(r)
            else:
                others.append(r)

        sorted_results = official + others

        if official:
            print(f"[Researcher] Prioritized {len(official)} official docs for fetching")

        return sorted_results

    # ------------------------------------------------------------------
    # Step 5 — fetch full page content
    # ------------------------------------------------------------------

    async def _enrich_with_page_content(self, results: list[dict]) -> list[dict]:
        """
        Fetch full page for top 3 results, extract clean article body.
        """
        import asyncio
        enriched = list(results)

        async def fetch_one(idx: int, result: dict):
            url = result.get("url", "")
            if not url:
                return
            try:
                raw_html = await http_fetch(url, timeout=10)
                if raw_html and len(raw_html) > 200:
                    clean = self._extract_article_text(raw_html, url)
                    if clean:
                        enriched[idx]["page_content"] = clean
                        print(f"[Researcher] Extracted {len(clean)} chars from {url[:60]}")
            except Exception as e:
                print(f"[Researcher] Page fetch failed for {url[:60]}: {e}")

        await asyncio.gather(*[fetch_one(i, r) for i, r in enumerate(results[:3])])
        return enriched

    # ------------------------------------------------------------------
    # Step 6 — BeautifulSoup article extraction
    # ------------------------------------------------------------------

    def _extract_article_text(self, html: str, url: str = "") -> str:
        """
        Extract clean article body using BeautifulSoup.
        """
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")

            for tag in soup(["script", "style", "nav", "header", "footer",
                             "aside", "iframe", "noscript"]):
                tag.decompose()

            for element in soup.select(
                "[class*='nav'], [class*='menu'], [class*='footer'], "
                "[class*='sidebar'], [class*='cookie'], [class*='banner'], "
                "[class*='ad'], [class*='advertisement']"
            ):
                element.decompose()

            content = None
            for selector in ["article", "main", "[role='main']",
                             ".content", ".post-content", ".article-body",
                             "#content", "#main"]:
                found = soup.select_one(selector)
                if found and len(found.get_text(strip=True)) > 200:
                    content = found
                    break

            if not content:
                content = soup.find("body") or soup

            text = content.get_text(separator=" ", strip=True)

            import re
            text = re.sub(r'\s+', ' ', text).strip()
            return text[:PAGE_CONTENT_LIMIT]

        except ImportError:
            print("[Researcher] BeautifulSoup not installed — using raw text")
            import re
            text = re.sub(r'<[^>]+>', ' ', html)
            text = re.sub(r'\s+', ' ', text).strip()
            return text[:PAGE_CONTENT_LIMIT]

        except Exception as e:
            print(f"[Researcher] HTML extraction error: {e}")
            return ""

    # ------------------------------------------------------------------
    # Step 7 — format for LLM prompt
    # ------------------------------------------------------------------

    def _format_enriched_results(self, results: list[dict]) -> str:
        lines = []
        for i, r in enumerate(results, 1):
            title   = r.get("title", "Untitled")
            url     = r.get("url", "")
            snippet = r.get("content", "")
            page    = r.get("page_content", "")

            lines.append(f"{i}. **{title}**")
            lines.append(f"   URL: {url}")

            if page:
                lines.append(f"   Content: {page[:3500]}")
            else:
                lines.append(f"   Snippet: {snippet[:400]}")

            lines.append("")

        return "\n".join(lines) if lines else "No results available."


researcher_agent = ResearcherAgent()

async def run_researcher(task: Task) -> str:
    return await researcher_agent.run(task)