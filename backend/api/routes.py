"""
routes.py — updated with intent router + vague goal detection.

Flow:
  1. Check for greetings → friendly response
  2. Check for profanity/abuse → professional response
  3. Check for incomplete/vague goals → guidance message
  4. Proceed to planner → DAG → agents
"""
import asyncio

from fastapi import APIRouter, BackgroundTasks, HTTPException

from graph.models import GoalRequest, GoalResponse, Run
from graph.redis_store import store
from graph.task_graph import graph
from graph.dispatcher import dispatcher
from agents.planner import planner
from graph.models import WorkerType

from agents.researcher import run_researcher
from agents.summarizer import run_summarizer
from agents.coder import run_coder
from agents.browser import run_browser
from agents.synthesizer import run_synthesizer

router = APIRouter()

# Register real workers
dispatcher.register(WorkerType.RESEARCHER,  run_researcher)
dispatcher.register(WorkerType.SUMMARIZER,  run_summarizer)
dispatcher.register(WorkerType.CODER,       run_coder)
dispatcher.register(WorkerType.BROWSER,     run_browser)
dispatcher.register(WorkerType.SYNTHESIZER, run_synthesizer)
print("[Routes] Workers registered ✓")


# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------

GREETINGS = {
    "hi", "hello", "hey", "howdy", "hiya", "sup", "what's up",
    "good morning", "good afternoon", "good evening", "greetings",
    # Expanded greetings
    "whats up", "wassup", "wazzup", "yo", "heya", "helo", "hii",
    "hiii", "hihi", "heyy", "heyyy",
}

PROFANITY = {
    "fuck", "fucking", "f***", "f**k", "shit", "damn", "bitch",
    "asshole", "bastard", "wtf", "stfu", "gtfo", "lmfao",
    "fuck you", "fuck off", "shut up", "screw you"
}

VAGUE_GOALS = {
    "do something", "help me", "do it", "run this", "go", "start",
    "begin", "anything", "something", "test", "ok", "okay", "sure",
    "yes", "no", "maybe", "idk", "dunno", "help", "run", "execute",
    "do", "make", "create", "build", "write", "create the", "create a",
    "create an", "make the", "make a", "write the", "write a", "write an",
    "build the", "build a", "build an", "do the", "do a", "i want",
    "i need", "i want to", "i need to", "can you", "please",
}

VAGUE_PATTERNS = [
    "create the", "create a", "create an",
    "make the", "make a", "make an",
    "write the", "write a", "write an",
    "build the", "build a", "build an",
    "do the", "do a", "do an",
    "i want to", "i need to",
    "can you help", "please help",
]


def _classify_intent(goal: str) -> str:
    """
    Returns: 'greeting', 'abusive', 'incomplete', or 'task'
    """
    cleaned = goal.strip().lower().rstrip('?!.')

    # Greeting check
    if cleaned in GREETINGS:
        return "greeting"

    # Profanity check
    words = cleaned.split()
    for word in words:
        if word in PROFANITY:
            return "abusive"
    if cleaned in PROFANITY:
        return "abusive"

    # Too short
    if len(cleaned) < 5:
        return "incomplete"

    # Exact vague match
    if cleaned in VAGUE_GOALS:
        return "incomplete"

    # Vague pattern with no meaningful continuation (under 15 chars)
    for pattern in VAGUE_PATTERNS:
        if cleaned.startswith(pattern) and len(cleaned) < 15:
            return "incomplete"

    # Two words or less with no digit (catches "create the", "run it", etc.)
    words = cleaned.split()
    if len(words) <= 2 and not any(c.isdigit() for c in cleaned):
        return "incomplete"

    return "task"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/goal", response_model=GoalResponse, tags=["runs"])
async def create_goal(
    body: GoalRequest,
    background_tasks: BackgroundTasks,
) -> GoalResponse:

    intent = _classify_intent(body.goal)

    if intent == "greeting":
        raise HTTPException(
            status_code=400,
            detail="Hi! I'm AgentOS — a multi-agent task execution system. Give me a research or coding task and I'll put my agents to work. Try: 'Compare React vs Vue vs Angular' or 'Write a Python sorting function'."
        )

    if intent == "abusive":
        raise HTTPException(
            status_code=400,
            detail="Please keep it professional. AgentOS is here to help with research and coding tasks."
        )

    if intent == "incomplete":
        raise HTTPException(
            status_code=400,
            detail="That looks incomplete. Could you be more specific? For example: 'Compare React vs Vue vs Angular', 'Write a Python sorting function', or 'Research the latest AI trends in 2026'."
        )

    # intent == "task" — proceed to planner
    try:
        await store.connect()
    except Exception:
        pass

    try:
        tasks = await planner.plan(body.goal)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Planner failed: {str(e)}")

    run = Run(goal=body.goal, tasks=tasks)
    await graph.create_run(run)

    background_tasks.add_task(dispatcher.run, run)

    worker_types = set()
    for t in tasks:
        if hasattr(t, 'worker'):
            if hasattr(t.worker, 'value'):
                worker_types.add(t.worker.value)
            else:
                worker_types.add(str(t.worker))
        elif isinstance(t, dict):
            worker_types.add(t.get('worker', 'unknown'))
        else:
            worker_types.add('unknown')

    worker_types = list(worker_types)

    return GoalResponse(
        run_id=run.id,
        message=f"Run started — {len(tasks)} task(s) allocated: {', '.join(worker_types)}"
    )


@router.get("/runs/{run_id}", tags=["runs"])
async def get_run(run_id: str):
    try:
        await store.connect()
    except Exception:
        pass

    run = await store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    return {
        "run_id":       run.id,
        "goal":         run.goal,
        "status":       run.status,
        "final_output": run.final_output,
        "tasks": [
            {
                "id":          t.id,
                "name":        t.name,
                "worker":      t.worker.value if hasattr(t.worker, 'value') else str(t.worker),
                "status":      t.status.value if hasattr(t.status, 'value') else str(t.status),
                "description": t.description,
                "output":      t.output,
                "error":       t.error,
                "retry_count": t.retry_count,
                "started_at":  t.started_at,
                "finished_at": t.finished_at,
            }
            for t in run.tasks
        ],
    }


@router.get("/runs/history", tags=["runs"])
async def get_run_history():
    from db.mongo import mongo_db
    runs = await mongo_db.get_run_history(limit=20)
    return {"runs": runs}