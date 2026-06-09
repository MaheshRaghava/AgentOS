"""
dispatcher.py — Orchestrates a run using the LangGraph StateGraph.

Handles:
  1. Builds the initial AgentState
  2. Invokes the compiled graph
  3. Handles run-level status updates in Redis
"""
from typing import Callable, Awaitable

from graph.models import AgentState, Run, RunStatus, Task, WorkerType
from graph.redis_store import store
from graph.agent_graph import build_agent_graph
from graph.checkpointer import redis_checkpointer

WorkerFn = Callable[[Task], Awaitable[str]]


class Dispatcher:

    def __init__(self):
        self._workers: dict[WorkerType, WorkerFn] = {}
        self._graph = None   # compiled LangGraph — built lazily after all workers registered

    def register(self, worker_type: WorkerType, fn: WorkerFn) -> None:
        self._workers[worker_type] = fn
        self._graph = None   # invalidate compiled graph so it rebuilds with new worker
        print(f"[Dispatcher] Registered: {worker_type.value}")

    def _get_graph(self):
        """Compile the LangGraph StateGraph (once, lazily)."""
        if self._graph is None:
            self._graph = build_agent_graph(self._workers)
            print("[Dispatcher] LangGraph StateGraph compiled ✓")
        return self._graph

    # ------------------------------------------------------------------
    # Main entry point — called by routes.py via BackgroundTasks
    # ------------------------------------------------------------------

    async def run(self, run: Run) -> str:
        await store.update_run_status(run.id, RunStatus.RUNNING)
        await store.publish(run.id, {
            "event": "run_started",
            "run_id": run.id,
            "data": {}
        })
        print(f"[Dispatcher] Run {run.id} started via LangGraph")

        # Build the initial AgentState — this is what flows through the graph
        initial_state: AgentState = {
            "run_id":       run.id,
            "goal":         run.goal,
            "tasks":        [t.model_dump(mode="json") for t in run.tasks],
            "completed":    [],
            "failed":       [],
            "outputs":      {},
            "final_output": "",
            "error":        "",
        }

        # LangGraph config — thread_id scopes checkpointing to this run
        config = {
            "configurable": {
                "thread_id": run.id,
            }
        }

        try:
            compiled_graph = self._get_graph()

            # ainvoke runs the full graph to completion
            # LangGraph handles: node execution, conditional routing,
            # parallel tasks via Send API, state passing between nodes
            final_state: AgentState = await compiled_graph.ainvoke(
                initial_state,
                config=config,
            )

            final_output = final_state.get("final_output", "No output produced.")

            await store.update_run_status(run.id, RunStatus.COMPLETED)
            print(f"[Dispatcher] Run {run.id} COMPLETED via LangGraph")
            return final_output

        except Exception as e:
            error_msg = f"Run failed: {str(e)}"
            print(f"[Dispatcher] Run {run.id} FAILED: {e}")
            await store.update_run_status(run.id, RunStatus.FAILED)
            await store.publish(run.id, {
                "event":  "run_failed",
                "run_id": run.id,
                "data":   {"error": str(e)},
            })
            return error_msg


dispatcher = Dispatcher()
