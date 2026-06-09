"""
task_graph.py — Thin wrapper that bridges LangGraph state and Redis.

LangGraph's StateGraph handles DAG traversal and node routing.
This file only handles:
  1. Creating a run (saving initial state to Redis)
  2. Read helpers used by the WebSocket and REST API
  3. Convenience methods still used by websocket.py and routes.py

The actual state transitions (PENDING → RUNNING → DONE → FAILED)
now happen inside agent_graph.py node functions.
"""
from graph.models import Run, RunStatus, Task, TaskStatus
from graph.redis_store import store


class TaskGraph:

    # ------------------------------------------------------------------
    # Create — called by routes.py after planner returns tasks
    # ------------------------------------------------------------------

    async def create_run(self, run: Run) -> None:
        """Save run + all tasks to Redis. LangGraph state is initialized separately."""
        await store.save_run(run)
        for task in run.tasks:
            await store.save_task(run.id, task)
        print(f"[Graph] Run {run.id} created — {len(run.tasks)} tasks")

    # ------------------------------------------------------------------
    # Read helpers — used by REST API and WebSocket initial snapshot
    # ------------------------------------------------------------------

    async def get_all_tasks(self, run_id: str) -> list[Task]:
        return await store.get_all_tasks(run_id)

    async def get_run(self, run_id: str) -> Run | None:
        return await store.get_run(run_id)

    # ------------------------------------------------------------------
    # Status checks — used by dispatcher to detect terminal states
    # ------------------------------------------------------------------

    async def is_run_complete(self, run_id: str) -> bool:
        tasks = await store.get_all_tasks(run_id)
        return all(t.status in (TaskStatus.DONE, TaskStatus.SKIPPED) for t in tasks)

    async def has_failed_tasks(self, run_id: str) -> bool:
        tasks = await store.get_all_tasks(run_id)
        return any(t.status == TaskStatus.FAILED for t in tasks)

    async def mark_running(self, run_id: str, task_id: str) -> None:
        from datetime import datetime
        task = await store.get_task(run_id, task_id)
        if not task:
            return
        task.status     = TaskStatus.RUNNING
        task.started_at = datetime.utcnow()
        await store.save_task(run_id, task)

    async def mark_done(self, run_id: str, task_id: str, output: str) -> None:
        from datetime import datetime
        task = await store.get_task(run_id, task_id)
        if not task:
            return
        task.status     = TaskStatus.DONE
        task.output     = output
        task.finished_at = datetime.utcnow()
        await store.save_task(run_id, task)

    async def mark_failed(self, run_id: str, task_id: str, error: str) -> Task | None:
        from datetime import datetime
        task = await store.get_task(run_id, task_id)
        if not task:
            return None
        task.retry_count += 1
        if task.retry_count >= task.max_retries:
            task.status      = TaskStatus.FAILED
            task.error       = error
            task.finished_at = datetime.utcnow()
        else:
            task.status = TaskStatus.PENDING
            task.error  = error
        await store.save_task(run_id, task)
        return task


graph = TaskGraph()
