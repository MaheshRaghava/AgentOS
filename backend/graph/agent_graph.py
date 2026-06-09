"""
agent_graph.py — The LangGraph StateGraph definition.

This is the core of the LangGraph integration.
It defines the graph structure: nodes (workers) + edges (dependencies)
+ conditional routing (retry logic, failure handling).

The graph is compiled once at startup and reused for every run.

Routing logic:
  - SIMPLE  (1 task)  : researcher → END (synthesizer skipped)
  - MODERATE (n tasks): researchers → synthesizer → END
  - COMPLEX  (n tasks): researchers + coder + browser → synthesizer → END
"""
import asyncio
from typing import Callable, Awaitable

from langgraph.graph import StateGraph, END
from graph.models import AgentState, Task, TaskStatus, WorkerType
from graph.redis_store import store

WorkerFn = Callable[[Task], Awaitable[str]]

# ---------------------------------------------------------------------------
# Helper: Inject dependency outputs into a task's description
# ---------------------------------------------------------------------------

def inject_dependency_outputs(task: Task, completed: set[str], outputs: dict[str, str]) -> Task:
    """
    For summarizer and synthesizer tasks, inject the outputs of their dependencies
    into the task description so they have actual content to work with.
    """
    if task.worker not in [WorkerType.SUMMARIZER, WorkerType.SYNTHESIZER]:
        return task
    
    if not task.dependencies:
        return task
    
    # Collect outputs from dependencies
    dependency_outputs = []
    for dep_id in task.dependencies:
        if dep_id in outputs:
            dependency_outputs.append(f"[Dependency: {dep_id}]\n{outputs[dep_id]}")
        elif dep_id in completed:
            pass
    
    if dependency_outputs:
        injected_content = "\n\n--- DEPENDENCY OUTPUTS ---\n\n" + "\n\n".join(dependency_outputs)
        injected_content += "\n\n--- ORIGINAL TASK ---\n\n"
        task.description = injected_content + task.description
        print(f"[AgentGraph] Injected {len(dependency_outputs)} dependency outputs into {task.worker.value} task: {task.name}")
    
    return task


# ---------------------------------------------------------------------------
# Node functions — each wraps one worker agent
# ---------------------------------------------------------------------------

def make_worker_node(worker_type: WorkerType, worker_fn: WorkerFn):
    """
    Factory that creates a LangGraph node function for a given worker type.
    The node:
      1. Finds all PENDING tasks assigned to this worker type
      2. Injects dependency outputs for summarizer/synthesizer tasks
      3. Runs them (respecting dependencies)
      4. Returns state updates (completed/failed lists + outputs)
    """
    async def node_fn(state: AgentState) -> dict:
        run_id    = state["run_id"]
        tasks     = [Task(**t) for t in state["tasks"]]
        completed = set(state["completed"])
        failed    = set(state["failed"])
        outputs   = dict(state["outputs"])

        # Find tasks for this worker that are ready to run
        my_tasks = [
            t for t in tasks
            if t.worker == worker_type
            and t.status == TaskStatus.PENDING
            and t.is_ready(completed)
        ]

        if not my_tasks:
            return {}  # nothing to do, pass through

        new_completed = list(state["completed"])
        new_failed    = list(state["failed"])

        # Run all ready tasks for this worker in parallel
        async def run_one(task: Task):
            from datetime import datetime

            # INJECTION: For summarizer/synthesizer, inject dependency outputs
            task = inject_dependency_outputs(task, completed, outputs)

            # Mark running in Redis
            task.status     = TaskStatus.RUNNING
            task.started_at = datetime.utcnow()
            await store.save_task(run_id, task)
            await store.publish(run_id, {
                "event":   "task_update",
                "task_id": task.id,
                "status":  "running",
                "name":    task.name,
            })

            try:
                output = await worker_fn(task)

                task.status      = TaskStatus.DONE
                task.output      = output
                task.finished_at = datetime.utcnow()
                await store.save_task(run_id, task)
                await store.publish(run_id, {
                    "event":          "task_update",
                    "task_id":        task.id,
                    "status":         "done",
                    "name":           task.name,
                    "output_preview": output[:200],
                })
                return ("done", task.id, output)

            except Exception as exc:
                task.retry_count += 1
                if task.retry_count >= task.max_retries:
                    task.status      = TaskStatus.FAILED
                    task.error       = str(exc)
                    task.finished_at = datetime.utcnow()
                    await store.save_task(run_id, task)
                    await store.publish(run_id, {
                        "event":   "task_update",
                        "task_id": task.id,
                        "status":  "failed",
                        "name":    task.name,
                        "error":   str(exc),
                    })
                    return ("failed", task.id, str(exc))
                else:
                    # Back to PENDING for retry
                    task.status = TaskStatus.PENDING
                    task.error  = str(exc)
                    await store.save_task(run_id, task)
                    return ("retry", task.id, str(exc))

        results = await asyncio.gather(*[run_one(t) for t in my_tasks])

        for status, task_id, value in results:
            if status == "done":
                new_completed.append(task_id)
                outputs[task_id] = value
            elif status == "failed":
                new_failed.append(task_id)

        # Serialize updated tasks back to dicts
        all_tasks = await store.get_all_tasks(run_id)
        updated_task_dicts = [t.model_dump(mode="json") for t in all_tasks]

        return {
            "tasks":     updated_task_dicts,
            "completed": new_completed,
            "failed":    new_failed,
            "outputs":   outputs,
        }

    node_fn.__name__ = f"{worker_type.value}_node"
    return node_fn


def make_synthesizer_node(worker_fn: WorkerFn):
    """
    Special node for the Synthesizer — runs last, after all workers are done.
    Passes run_id and goal to synthesizer so MongoDB save fires correctly.
    """
    async def synthesizer_node(state: AgentState) -> dict:
        run_id  = state["run_id"]
        outputs = state["outputs"]
        goal    = state["goal"]
        tasks   = [Task(**t) for t in state["tasks"]]

        done_outputs = []
        for task in tasks:
            if task.id in outputs and task.worker != WorkerType.SYNTHESIZER:
                output_text = outputs[task.id]
                done_outputs.append(f"[{task.name}]\n{output_text}")

        if not done_outputs:
            return {"final_output": "No agent outputs to synthesize."}

        synth_task = Task(
            name="Synthesize",
            description="\n\n".join(done_outputs),
            worker=WorkerType.SYNTHESIZER,
        )

        try:
            # Import synthesizer_agent directly so we can pass run_id and goal
            from agents.synthesizer import synthesizer_agent
            final_output = await synthesizer_agent.run(
                synth_task,
                run_id=run_id,
                goal=goal,
            )
        except Exception as e:
            final_output = f"## Research Results\n\n" + "\n\n---\n\n".join(done_outputs)
            print(f"[Synthesizer] Failed, using raw fallback: {e}")
            # Still save to MongoDB even on fallback
            try:
                from db.mongo import mongo_db
                await mongo_db.save_run_output(run_id, goal, final_output)
                print(f"[Synthesizer] Saved to MongoDB ✓ (fallback)")
            except Exception as save_err:
                print(f"[Synthesizer] MongoDB save failed: {save_err}")

        await store.set_final_output(run_id, final_output)
        await store.publish(run_id, {
            "event":  "final_output",
            "run_id": run_id,
            "data":   {"output": final_output},
        })
        await store.publish(run_id, {
            "event":  "run_completed",
            "run_id": run_id,
            "data":   {},
        })

        return {"final_output": final_output}

    return synthesizer_node


def make_final_output_node():
    """
    Terminal node for SIMPLE goals — no synthesizer needed.
    Also saves to MongoDB so simple goal runs appear in history.
    """
    async def final_output_node(state: AgentState) -> dict:
        run_id  = state["run_id"]
        outputs = state["outputs"]
        goal    = state["goal"]
        tasks   = [Task(**t) for t in state["tasks"]]

        # Get the single researcher output
        final_output = ""
        for task in tasks:
            if task.id in outputs:
                final_output = outputs[task.id]
                break

        if not final_output:
            final_output = "No output produced."

        print(f"[FinalOutput] Publishing final output directly ({len(final_output)} chars)")

        # Save to MongoDB — simple goals also need run history
        try:
            from db.mongo import mongo_db
            await mongo_db.save_run_output(run_id, goal, final_output)
            print(f"[FinalOutput] Saved to MongoDB ✓")
        except Exception as e:
            print(f"[FinalOutput] MongoDB save skipped: {e}")

        await store.set_final_output(run_id, final_output)
        await store.publish(run_id, {
            "event":  "final_output",
            "run_id": run_id,
            "data":   {"output": final_output},
        })
        await store.publish(run_id, {
            "event":  "run_completed",
            "run_id": run_id,
            "data":   {},
        })

        return {"final_output": final_output}

    return final_output_node


# ---------------------------------------------------------------------------
# Routing functions — LangGraph conditional edges
# ---------------------------------------------------------------------------

def route_after_workers(state: AgentState) -> str:
    """
    After each worker batch, decide what to do next:

    - Still pending tasks that are now ready? → route to correct worker
    - All tasks done and only 1 task existed (SIMPLE goal)? → go to final_output (skip synthesizer)
    - All tasks done and multiple tasks existed (MODERATE/COMPLEX)? → go to synthesizer
    - Permanent failures with nothing running? → synthesizer (partial results)
    """
    tasks     = [Task(**t) for t in state["tasks"]]
    completed = set(state["completed"])
    failed    = set(state["failed"])

    # Non-synthesizer tasks only
    worker_tasks = [t for t in tasks if t.worker != WorkerType.SYNTHESIZER]

    # Check if any are still pending
    pending = [
        t for t in worker_tasks
        if t.status == TaskStatus.PENDING
    ]

    if not pending:
        # All worker tasks are done
        # SIMPLE goal = only 1 task → skip synthesizer, go direct to final_output
        if len(worker_tasks) == 1:
            print("[Router] Single task run — routing to final_output (skipping synthesizer)")
            return "final_output"

        # MODERATE / COMPLEX = multiple tasks → synthesizer merges
        return "synthesizer"

    # Find the next ready task's worker type
    for task in pending:
        if task.is_ready(completed):
            return task.worker.value

    # Pending tasks exist but none are ready yet — check for unrecoverable failure
    running = [t for t in tasks if t.status == TaskStatus.RUNNING]
    if not running and failed:
        if len(worker_tasks) == 1:
            return "final_output"
        return "synthesizer"

    # Default fallback
    return "synthesizer"


# ---------------------------------------------------------------------------
# Graph builder — call this once at startup
# ---------------------------------------------------------------------------

def build_agent_graph(workers: dict[WorkerType, WorkerFn]):
    """
    Build and compile the LangGraph StateGraph.

    Graph structure:
        START → researcher (entry point)
              → [researcher | coder | summarizer | browser]  (conditional)
              → synthesizer (MODERATE / COMPLEX goals)
              → END

              OR

        START → researcher (entry point)
              → final_output (SIMPLE goals — skips synthesizer)
              → END

    Routing is conditional — after each worker node, the router
    checks task count and readiness to decide next step.
    """
    builder = StateGraph(AgentState)

    # Add a node for each worker type
    for worker_type, worker_fn in workers.items():
        if worker_type == WorkerType.SYNTHESIZER:
            builder.add_node(
                worker_type.value,
                make_synthesizer_node(worker_fn)
            )
        else:
            builder.add_node(
                worker_type.value,
                make_worker_node(worker_type, worker_fn)
            )

    # Add the simple-goal terminal node (no synthesizer)
    builder.add_node("final_output", make_final_output_node())

    # Entry point — always start with researcher node
    builder.set_entry_point(WorkerType.RESEARCHER.value)

    # Conditional edges from each worker → next worker, synthesizer, or final_output
    worker_nodes  = [wt.value for wt in WorkerType if wt != WorkerType.SYNTHESIZER]
    possible_next = {wt.value: wt.value for wt in WorkerType}
    possible_next["synthesizer"]  = WorkerType.SYNTHESIZER.value
    possible_next["final_output"] = "final_output"

    for node_name in worker_nodes:
        builder.add_conditional_edges(
            node_name,
            route_after_workers,
            possible_next,
        )

    # Both terminal nodes end the graph
    builder.add_edge(WorkerType.SYNTHESIZER.value, END)
    builder.add_edge("final_output", END)

    return builder.compile()