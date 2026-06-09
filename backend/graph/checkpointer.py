"""
checkpointer.py — LangGraph Redis checkpointer.

LangGraph can save graph state after every node execution (checkpointing).
This means if the server restarts mid-run, the graph can resume from
the last checkpoint instead of starting over.

We back the checkpointer with Redis so it uses the same infra
we already have, not a separate SQLite file.
"""
import json
from typing import Any, AsyncIterator, Iterator, Optional, Sequence, Tuple

from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)

from graph.redis_store import store


class RedisCheckpointer(BaseCheckpointSaver):
    """
    Stores LangGraph checkpoints in Redis.

    Key schema:
        checkpoint:{thread_id}:{checkpoint_id}  →  checkpoint JSON
        checkpoint:{thread_id}:latest           →  latest checkpoint_id
    """

    # ------------------------------------------------------------------
    # Required by LangGraph BaseCheckpointSaver
    # ------------------------------------------------------------------

    def get_tuple(self, config: dict) -> Optional[CheckpointTuple]:
        """Sync get — required by interface but we use async version."""
        raise NotImplementedError("Use aget_tuple for async")

    def list(self, config: dict, **kwargs) -> Iterator[CheckpointTuple]:
        raise NotImplementedError("Use alist for async")

    def put(self, config: dict, checkpoint: Checkpoint, metadata: CheckpointMetadata) -> dict:
        raise NotImplementedError("Use aput for async")

    # ------------------------------------------------------------------
    # Async implementations — these are what LangGraph actually calls
    # ------------------------------------------------------------------

    async def aget_tuple(self, config: dict) -> Optional[CheckpointTuple]:
        thread_id = config["configurable"].get("thread_id")
        if not thread_id:
            return None

        try:
            checkpoint_id = await store.client.get(f"checkpoint:{thread_id}:latest")
            if not checkpoint_id:
                return None

            raw = await store.client.get(f"checkpoint:{thread_id}:{checkpoint_id}")
            if not raw:
                return None

            data = json.loads(raw)
            return CheckpointTuple(
                config=config,
                checkpoint=data["checkpoint"],
                metadata=data.get("metadata", {}),
                parent_config=data.get("parent_config"),
            )
        except Exception as e:
            print(f"[Checkpointer] aget_tuple error: {e}")
            return None

    async def aput(
        self,
        config: dict,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict,
    ) -> dict:
        thread_id     = config["configurable"].get("thread_id")
        checkpoint_id = checkpoint["id"]

        if not thread_id:
            return config

        try:
            payload = json.dumps({
                "checkpoint":    checkpoint,
                "metadata":      metadata,
                "parent_config": config,
            })
            key = f"checkpoint:{thread_id}:{checkpoint_id}"
            await store.client.set(key, payload, ex=86400)
            await store.client.set(f"checkpoint:{thread_id}:latest", checkpoint_id, ex=86400)
        except Exception as e:
            print(f"[Checkpointer] aput error: {e}")

        return {**config, "configurable": {**config.get("configurable", {}), "checkpoint_id": checkpoint_id}}

    async def alist(self, config: dict, **kwargs) -> AsyncIterator[CheckpointTuple]:
        # Minimal implementation — yields nothing (history not needed for MVP)
        return
        yield  # make it an async generator


# Single instance — injected into the compiled graph
redis_checkpointer = RedisCheckpointer()
