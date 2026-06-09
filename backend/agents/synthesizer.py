"""
synthesizer.py — Final synthesis agent with source attribution.

Flow:
  - Extracts source URLs from researcher outputs
  - Passes them to the synthesis prompt explicitly
  - Final output includes a consolidated Sources section
  - Still uses BaseAgent model fallback chain
"""
from graph.models import Task
from db.mongo import mongo_db
from agents.base import BaseAgent
import re

SYNTHESIZER_PROMPT = """You are a result aggregator. Your job is to combine outputs from multiple research agents into one structured final answer.

ORIGINAL GOAL: {goal}

AGENT OUTPUTS:
{outputs}

SOURCES COLLECTED:
{sources}

RULES:
- Only use information from the agent outputs provided above
- Do NOT add new ideas, advice, or explanations not present in the inputs
- Do NOT fill gaps with general knowledge — if data is missing, say so
- Preserve factual content, numbers, code, and examples exactly as provided
- Combine and deduplicate overlapping information across agents
- Structure the answer clearly with headings and bullet points where appropriate
- End with a consolidated **Sources** section containing ALL the URLs provided

Format in clean markdown.
"""

SIMPLE_SYNTHESIZER_PROMPT = """You are a result aggregator. Structure the following research output into a clean, readable answer.

GOAL: {goal}

RESEARCH OUTPUT:
{outputs}

RULES:
- Only use information from the research output above
- Do NOT add new ideas or fill gaps with general knowledge
- Preserve all facts, numbers, and sources exactly
- Format clearly in markdown
- Include any sources mentioned in the research
"""


class SynthesizerAgent(BaseAgent):

    async def run(self, task: Task, run_id: str = "", goal: str = "") -> str:
        print(f"[Synthesizer] Starting synthesis...")

        # Extract sources from all agent outputs
        sources = self._extract_sources(task.description)
        print(f"[Synthesizer] Found {len(sources)} sources")

        actual_goal = goal or task.description[:200]

        if sources:
            sources_text = "\n".join(f"- {s}" for s in sources)
            prompt = SYNTHESIZER_PROMPT\
                .replace("{goal}", actual_goal)\
                .replace("{outputs}", task.description)\
                .replace("{sources}", sources_text)
        else:
            prompt = SIMPLE_SYNTHESIZER_PROMPT\
                .replace("{goal}", actual_goal)\
                .replace("{outputs}", task.description)

        output = await self.generate_with_fallback(prompt)

        # If sources exist but model didn't include them, append manually
        if sources and "sources" not in output.lower():
            source_block = "\n\n---\n## Sources\n" + "\n".join(f"- {s}" for s in sources)
            output += source_block
            print(f"[Synthesizer] Appended {len(sources)} sources manually")

        print(f"[Synthesizer] Done — {len(output)} chars, {len(sources)} sources")

        # Save to MongoDB
        if run_id:
            try:
                await mongo_db.save_run_output(run_id, goal, output)
            except Exception as e:
                print(f"[Synthesizer] MongoDB save skipped: {e}")

        return output

    def _extract_sources(self, text: str) -> list[str]:
        """
        Extract URLs from agent outputs.
        Looks for:
        - Markdown links: [Title](URL)
        - Bare URLs: https://...
        - Sources section with plain URLs
        """
        sources = []

        # Strategy 1: markdown links [Title](URL)
        md_links = re.findall(r'\[([^\]]+)\]\((https?://[^\)]+)\)', text)
        for title, url in md_links:
            sources.append(f"[{title}]({url})")

        # Strategy 2: Sources section with plain URLs
        sources_section = re.search(
            r'(?:Sources|References|Links):\s*(.+?)(?=\n\n|\n$|$)',
            text,
            re.DOTALL | re.IGNORECASE
        )
        if sources_section:
            section_text = sources_section.group(1)
            urls_in_section = re.findall(r'https?://[^\s\'"<>\)\]]+', section_text)
            for url in urls_in_section:
                if url not in sources:
                    sources.append(url)

        # Strategy 3: bare URLs anywhere in text
        bare_urls = re.findall(r'https?://[^\s\'"<>\)\]]+', text)
        for url in bare_urls:
            if not re.search(r'\[' + re.escape(url) + r'\]', text):
                if url not in sources:
                    sources.append(url)

        # Strategy 4: titled URLs (e.g. "Title - https://...")
        titled_urls = re.findall(r'([A-Za-z0-9\s]+)[\s-]+(https?://[^\s\'"<>\)\]]+)', text)
        for title, url in titled_urls:
            if len(title.strip()) > 3:
                sources.append(f"[{title.strip()}]({url})")

        # Deduplicate preserving order
        seen = set()
        unique_sources = []
        for s in sources:
            url_match = re.search(r'(https?://[^\]]+)', s)
            key = url_match.group(1) if url_match else s
            if key not in seen:
                seen.add(key)
                unique_sources.append(s)

        return unique_sources[:15]


synthesizer_agent = SynthesizerAgent()

async def run_synthesizer(task: Task) -> str:
    return await synthesizer_agent.run(task)