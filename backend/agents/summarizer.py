"""
Summarizer agent — condenses long text or multiple research outputs.
Also handles direct answers for simple factual questions (no web search).
Uses map-reduce for large inputs that exceed context limits.
Called by dispatcher when task.worker == WorkerType.SUMMARIZER
"""
import asyncio
from config import settings
from graph.models import Task
from agents.base import BaseAgent

SUMMARIZER_PROMPT = """You are a summarization expert. Condense the following content into a clear, structured summary.

TASK: {description}

CONTENT TO SUMMARIZE:
{content}

Write a well-structured summary with:
- Key findings or main points (bullet points)
- Important details worth noting
- A 1-2 sentence conclusion

Be concise but complete. Preserve all important facts and numbers.
"""

REDUCE_PROMPT = """You have multiple summaries that need to be merged into one final summary.

TASK: {description}

SUMMARIES:
{summaries}

Merge these into a single coherent summary. Remove duplicates, keep all unique insights.
Structure it clearly with bullet points and a conclusion.
"""

DIRECT_ANSWER_PROMPT = """Answer the question directly using your knowledge.

Requirements:
- Be accurate and factual.
- Mention uncertainty if information may have changed recently.
- Keep answers concise but informative.
- Do not invent facts.

QUESTION: {question}

ANSWER:"""

# Max chars before switching to map-reduce (roughly 6k tokens)
CHUNK_LIMIT = 24000


class SummarizerAgent(BaseAgent):

    def __init__(self):
        super().__init__()  # BaseAgent handles model chain

    async def run(self, task: Task) -> str:
        print(f"[Summarizer] Starting: {task.name}")

        # Direct answer for simple factual questions (no web search)
        if task.name == "direct_answer":
            print(f"[Summarizer] Direct answer mode — using knowledge only (no web search)")
            prompt = DIRECT_ANSWER_PROMPT.replace("{question}", task.description)
            output = await self.generate_with_fallback(prompt)
            print(f"[Summarizer] Done: {task.name} ({len(output)} chars) [direct answer]")
            return output

        # Regular summarization flow
        content = task.description

        if len(content) <= CHUNK_LIMIT:
            output = await self._summarize(task.description, content)
        else:
            # Map-reduce for large content
            output = await self._map_reduce(task.description, content)

        print(f"[Summarizer] Done: {task.name} ({len(output)} chars)")
        return output

    async def _summarize(self, description: str, content: str) -> str:
        prompt = SUMMARIZER_PROMPT\
            .replace("{description}", description)\
            .replace("{content}", content[:CHUNK_LIMIT])

        return await self.generate_with_fallback(prompt)

    async def _map_reduce(self, description: str, content: str) -> str:
        """Split into chunks, summarize each, then merge."""
        print(f"[Summarizer] Content too large ({len(content)} chars) — using map-reduce")

        # Split into chunks
        chunks = [content[i:i+CHUNK_LIMIT] for i in range(0, len(content), CHUNK_LIMIT)]
        print(f"[Summarizer] Processing {len(chunks)} chunks in parallel")

        # Map — summarize each chunk concurrently using fallback
        chunk_summaries = await asyncio.gather(*[
            self._summarize(description, chunk) for chunk in chunks
        ])

        # Reduce — merge all summaries
        merged = "\n\n---\n\n".join(chunk_summaries)
        prompt = REDUCE_PROMPT\
            .replace("{description}", description)\
            .replace("{summaries}", merged)

        return await self.generate_with_fallback(prompt)


summarizer_agent = SummarizerAgent()

async def run_summarizer(task: Task) -> str:
    return await summarizer_agent.run(task)