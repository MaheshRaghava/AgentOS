"""
planner.py — Smart planner with dynamic agent allocation.

Two-step process:
  Step 1: Classify goal complexity → simple / moderate / complex
  Step 2: Generate task DAG using tier-appropriate prompt + constraints

This ensures:
  - Simple goals ("What is React?")  → DIRECT ANSWER (no web search) or 1 researcher
  - Moderate goals ("Compare X vs Y vs Z") → 1 worker per item, synthesizer merges
  - Complex goals (multi-part research + code) → full pipeline, synthesizer merges
"""
import json
import re
from enum import Enum

from config import settings
from graph.models import Task, WorkerType
from agents.base import BaseAgent


# ---------------------------------------------------------------------------
# Complexity tiers
# ---------------------------------------------------------------------------

class ComplexityTier(str, Enum):
    SIMPLE   = "simple"
    MODERATE = "moderate"
    COMPLEX  = "complex"


# ---------------------------------------------------------------------------
# Direct answer patterns — no web search needed
# ---------------------------------------------------------------------------

DIRECT_ANSWER_PATTERNS = [
    "what is", "who is", "define", "explain",
    "what are", "how does", "why is", "why does",
    "what does", "when is", "where is", "which is"
]

RESEARCH_KEYWORDS = [
    "latest", "current", "trend", "compare", "vs", "versus",
    "pricing", "cost", "benchmark", "top", "best", "worst",
    "news", "update", "2025", "2026", "2024", "recent",
    "analysis", "review", "rating", "popular", "trending",
    "write", "code", "function", "script", "program", 
    "implement", "create", "build", "generate", "make"
]


# ---------------------------------------------------------------------------
# Step 1 — Classify complexity (fast, cheap call)
# ---------------------------------------------------------------------------

CLASSIFIER_PROMPT = """Classify this goal into exactly one complexity tier.

TIERS:
- simple   : Single factual question, definition, or explanation. One topic. No comparison needed.
- moderate : Comparison, multi-angle research, or explanation needing 2-3 perspectives.
- complex  : Multi-part research + analysis + code, or requires 4+ distinct research areas.

EXAMPLES:
"What is React?" → simple
"What is JWT authentication?" → simple
"Compare React vs Vue vs Angular" → moderate
"Explain microservices architecture with pros and cons" → moderate
"Write a Python function to find prime numbers" → complex
"Write code that calculates fibonacci sequence" → complex
"Create a script to sort a list of numbers" → complex
"Research the top 5 AI frameworks, compare them, and write sample code" → complex
"Research quantum computing, explain concepts, and show Python simulation" → complex

GOAL: {goal}

Reply with ONLY one word: simple, moderate, or complex"""


# ---------------------------------------------------------------------------
# Step 2 — Generate tasks per tier
# ---------------------------------------------------------------------------

SIMPLE_PROMPT = """You are a task planning AI. This is a SIMPLE goal — it needs exactly 1 worker.

RULE: Return a JSON array with EXACTLY 1 task.
- Use "researcher" worker
- No dependencies (empty array)
- The researcher will answer directly — no summarizer or synthesizer needed

GOAL: {goal}

Output ONLY the JSON array:
[
  {{
    "name": "research_and_answer",
    "description": "Research and provide a complete answer to: {goal}",
    "worker": "researcher",
    "dependencies": []
  }}
]"""


MODERATE_PROMPT = """You are a task planning AI. This is a MODERATE goal — it needs one researcher task per item being compared.

RULES:
1. Return a JSON array with ONE researcher task per item/framework/technology.
2. Create ONE "researcher" task for EACH item being compared or researched.
3. DO NOT add a summarizer or synthesizer task — that is handled automatically.
4. Each task MUST have these exact fields: "name", "description", "worker", "dependencies"
5. All researcher tasks have empty dependencies (they run in parallel).

EXAMPLE FOR COMPARING 3 FRAMEWORKS:
[
  {
    "name": "research_react",
    "description": "Research React.js features, pros, and cons",
    "worker": "researcher",
    "dependencies": []
  },
  {
    "name": "research_vue",
    "description": "Research Vue.js features, pros, and cons",
    "worker": "researcher",
    "dependencies": []
  },
  {
    "name": "research_angular",
    "description": "Research Angular features, pros, and cons",
    "worker": "researcher",
    "dependencies": []
  }
]

GOAL: {goal}

Output ONLY the JSON array (no explanation, no markdown), nothing else:"""


COMPLEX_PROMPT = """You are a task planning AI. This is a COMPLEX goal — use the full pipeline.

RULES:
1. Return a JSON array with 3-7 tasks.
2. Each task MUST have these exact fields: "name", "description", "worker", "dependencies"
3. When the goal asks for "top N items" or "compare multiple items", create ONE researcher task for EACH item.
4. ALL researcher tasks must have EMPTY dependencies (they run in parallel).
5. DO NOT make researchers depend on each other — they run simultaneously.
6. Use coder only if code execution is explicitly requested.
7. DO NOT create separate "test" or "verify" tasks — the coder validates its own output.
8. Max 7 tasks — stay focused.

AVAILABLE WORKERS:
- researcher  : searches the web and summarizes findings
- coder       : writes and runs Python code (only for actual coding tasks)
- browser     : fetches content from a specific URL (use when goal mentions a specific URL, documentation page, or "visit this site")

EXAMPLE FOR "top 5 vector databases with code":
[
  {
    "name": "research_pinecone",
    "description": "Research Pinecone features, pricing, performance, and scalability",
    "worker": "researcher",
    "dependencies": []
  },
  {
    "name": "research_qdrant",
    "description": "Research Qdrant features, pricing, performance, and scalability",
    "worker": "researcher",
    "dependencies": []
  },
  {
    "name": "research_milvus",
    "description": "Research Milvus features, pricing, performance, and scalability",
    "worker": "researcher",
    "dependencies": []
  },
  {
    "name": "research_weaviate",
    "description": "Research Weaviate features, pricing, performance, and scalability",
    "worker": "researcher",
    "dependencies": []
  },
  {
    "name": "research_chroma",
    "description": "Research Chroma features, pricing, performance, and scalability",
    "worker": "researcher",
    "dependencies": []
  },
  {
    "name": "write_pinecone_code",
    "description": "Write Python script to connect to Pinecone and perform similarity search",
    "worker": "coder",
    "dependencies": ["research_pinecone", "research_qdrant", "research_milvus", "research_weaviate", "research_chroma"]
  }
]

EXAMPLE FOR COMPLEX GOAL (general):
[
  {
    "name": "research_frameworks",
    "description": "Research the top 3 JavaScript frameworks",
    "worker": "researcher",
    "dependencies": []
  },
  {
    "name": "research_performance",
    "description": "Research performance benchmarks for JavaScript frameworks",
    "worker": "researcher",
    "dependencies": []
  },
  {
    "name": "write_sample_code",
    "description": "Write a simple React component example",
    "worker": "coder",
    "dependencies": ["research_frameworks"]
  }
]

GOAL: {goal}

Output ONLY the JSON array (no explanation, no markdown), nothing else:"""


# ---------------------------------------------------------------------------
# Planner agent
# ---------------------------------------------------------------------------

class PlannerAgent(BaseAgent):

    def __init__(self):
        super().__init__()  # BaseAgent handles model chain

    async def plan(self, goal: str) -> list[Task]:
        """
        Dynamic agent allocation:
          1. Classify complexity
          2. Check if direct answer is possible (simple factual questions)
          3. Generate tasks with tier-appropriate constraints
        """
        # Step 1 — classify
        tier = await self._classify(goal)
        print(f"[Planner] Goal complexity: {tier.value.upper()} — '{goal[:60]}'")

        # Step 2 — Check for direct answer (no web search needed)
        if self._should_answer_directly(goal, tier):
            print(f"[Planner] Using DIRECT ANSWER (no web search)")
            return [Task(
                name="direct_answer",
                description=goal,
                worker=WorkerType.SUMMARIZER,
                dependencies=[],
            )]

        # Step 3 — generate tasks for this tier
        task_dicts = await self._generate_tasks(goal, tier)

        if not task_dicts:
            print("[Planner] WARNING: Fallback to single researcher task")
            task_dicts = [{
                "name": "research_goal",
                "description": goal,
                "worker": "researcher",
                "dependencies": []
            }]

        tasks = self._build_tasks(task_dicts)

        print(f"[Planner] Allocated {len(tasks)} worker(s) [{tier.value}]:")
        for t in tasks:
            deps = [d[:6] for d in t.dependencies]
            print(f"  [{t.worker.value}] {t.name}  deps={deps}")

        return tasks

    # ------------------------------------------------------------------
    # Helper: Check if goal can be answered directly
    # ------------------------------------------------------------------

    def _should_answer_directly(self, goal: str, tier: ComplexityTier) -> bool:
        """
        Check if this goal can be answered directly without web search.
        Examples: "What is Python?", "Who is Elon Musk?", "Explain inheritance"
        """
        # Only simple goals qualify
        if tier != ComplexityTier.SIMPLE:
            return False

        goal_lower = goal.lower().strip()
        goal_lower = goal_lower.rstrip('?.').strip()

        # Must start with a direct answer pattern
        starts_with_pattern = any(
            goal_lower.startswith(pattern) for pattern in DIRECT_ANSWER_PATTERNS
        )
        if not starts_with_pattern:
            return False

        # Must be relatively short (under 20 words)
        word_count = len(goal.split())
        if word_count > 20:
            return False

        # Must NOT contain research keywords (including code-related words)
        for keyword in RESEARCH_KEYWORDS:
            if keyword in goal_lower:
                print(f"[Planner] Direct answer rejected: contains research keyword '{keyword}'")
                return False

        return True

    # ------------------------------------------------------------------
    # Step 1 — complexity classifier
    # ------------------------------------------------------------------

    async def _classify(self, goal: str) -> ComplexityTier:
        prompt = CLASSIFIER_PROMPT.replace("{goal}", goal)
        
        try:
            raw = await self.generate_with_fallback(prompt)
            tier_str = raw.strip().lower()

            # Accept partial matches in case model adds punctuation
            if "complex" in tier_str:
                return ComplexityTier.COMPLEX
            elif "moderate" in tier_str:
                return ComplexityTier.MODERATE
            else:
                return ComplexityTier.SIMPLE

        except Exception as e:
            print(f"[Planner] Classifier error: {e} — defaulting to MODERATE")
            return ComplexityTier.MODERATE

    # ------------------------------------------------------------------
    # Step 2 — task generation per tier
    # ------------------------------------------------------------------

    async def _generate_tasks(self, goal: str, tier: ComplexityTier) -> list[dict]:

        # SIMPLE — skip LLM call entirely, return hardcoded single task
        if tier == ComplexityTier.SIMPLE:
            return [{
                "name": "research_and_answer",
                "description": f"Research and provide a complete, detailed answer to: {goal}",
                "worker": "researcher",
                "dependencies": []
            }]

        # MODERATE / COMPLEX — call LLM with tier-specific prompt
        prompt_template = (
            MODERATE_PROMPT if tier == ComplexityTier.MODERATE
            else COMPLEX_PROMPT
        )
        prompt = prompt_template.replace("{goal}", goal)

        try:
            raw = await self.generate_with_fallback(prompt)
            print(f"[Planner] Raw response ({tier.value}):\n{raw[:400]}\n")
            return self._parse_json_robust(raw)
        except Exception as e:
            print(f"[Planner] Task generation error: {e}")
            return []

    # ------------------------------------------------------------------
    # JSON parsing — robust strategies
    # ------------------------------------------------------------------

    def _parse_json_robust(self, raw: str) -> list[dict]:
        # Strategy 1: code block
        for match in re.findall(r"```(?:json)?\s*([\s\S]*?)```", raw):
            try:
                data = json.loads(match.strip())
                if isinstance(data, list):
                    return data
            except:
                continue

        # Strategy 2: array pattern
        for match in re.findall(r'\[\s*\{[\s\S]*?\}\s*\]', raw):
            try:
                data = json.loads(match)
                if isinstance(data, list) and data:
                    return data
            except:
                continue

        # Strategy 3: direct parse after stripping fences
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            data = json.loads(cleaned)
            if isinstance(data, list):
                return data
        except:
            pass

        return []

    # ------------------------------------------------------------------
    # Build Task objects from raw dicts
    # ------------------------------------------------------------------

    def _build_tasks(self, task_dicts: list[dict]) -> list[Task]:
        worker_map = {
            "researcher":  WorkerType.RESEARCHER,
            "summarizer":  WorkerType.SUMMARIZER,
            "coder":       WorkerType.CODER,
            "browser":     WorkerType.BROWSER,
            "synthesizer": WorkerType.SYNTHESIZER,
        }

        name_to_id: dict[str, str] = {}
        tasks: list[Task] = []

        for td in task_dicts:
            task_name        = td.get("name", td.get("id", "unnamed_task"))
            task_description = td.get("description", td.get("task", ""))

            worker = worker_map.get(
                td.get("worker", "researcher").lower().strip(),
                WorkerType.RESEARCHER
            )
            task = Task(
                name=task_name,
                description=task_description,
                worker=worker,
                dependencies=[],
            )
            tasks.append(task)
            name_to_id[task.name] = task.id

        # Resolve dependency names → IDs
        for task, td in zip(tasks, task_dicts):
            deps = td.get("dependencies", td.get("depends_on", []))
            task.dependencies = [
                name_to_id[d] for d in deps
                if d in name_to_id
            ]

        return tasks


planner = PlannerAgent()