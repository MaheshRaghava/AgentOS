import json
from typing import Optional

import redis.asyncio as aioredis

from config import settings
from graph.models import Run, Task, TaskStatus


class RedisStore:
    """
    Key schema:
        run:{run_id}           →  Run JSON (no tasks)
        run:{run_id}:tasks     →  Hash { task_id: Task JSON }
        run:{run_id}:pubsub    →  pub/sub channel (Phase 5)
    """

    def __init__(self):
        self._client: Optional[aioredis.Redis] = None

    async def connect(self):
        self._client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        await self._client.ping()
        print("[Redis] Connected ✓")

    async def disconnect(self):
        if self._client:
            await self._client.aclose()

    @property
    def client(self) -> aioredis.Redis:
        if not self._client:
            raise RuntimeError("Call await store.connect() first")
        return self._client

    # --- Run helpers ---------------------------------------------------

    async def save_run(self, run: Run) -> None:
        payload = run.model_dump_json(exclude={"tasks"})
        await self.client.set(f"run:{run.id}", payload, ex=86400)

    async def get_run(self, run_id: str) -> Optional[Run]:
        raw = await self.client.get(f"run:{run_id}")
        if not raw:
            return None
        data = json.loads(raw)
        data["tasks"] = await self._load_tasks(run_id)
        return Run(**data)

    async def update_run_status(self, run_id: str, status: str) -> None:
        raw = await self.client.get(f"run:{run_id}")
        if raw:
            data = json.loads(raw)
            data["status"] = status
            await self.client.set(f"run:{run_id}", json.dumps(data), ex=86400)

    async def set_final_output(self, run_id: str, output: str) -> None:
        raw = await self.client.get(f"run:{run_id}")
        if raw:
            data = json.loads(raw)
            data["final_output"] = output
            await self.client.set(f"run:{run_id}", json.dumps(data), ex=86400)

    # --- Task helpers --------------------------------------------------

    async def save_task(self, run_id: str, task: Task) -> None:
        await self.client.hset(
            f"run:{run_id}:tasks",
            task.id,
            task.model_dump_json(),
        )
        await self.client.expire(f"run:{run_id}:tasks", 86400)

    async def get_task(self, run_id: str, task_id: str) -> Optional[Task]:
        raw = await self.client.hget(f"run:{run_id}:tasks", task_id)
        return Task(**json.loads(raw)) if raw else None

    async def get_all_tasks(self, run_id: str) -> list[Task]:
        raw_map = await self.client.hgetall(f"run:{run_id}:tasks")
        return [Task(**json.loads(v)) for v in raw_map.values()]

    async def _load_tasks(self, run_id: str) -> list[dict]:
        raw_map = await self.client.hgetall(f"run:{run_id}:tasks")
        return [json.loads(v) for v in raw_map.values()]

    # --- Pub/Sub (Phase 5) ---------------------------------------------

    async def publish(self, run_id: str, event: dict) -> None:
        await self.client.publish(f"run:{run_id}:pubsub", json.dumps(event))

    def pubsub(self):
        return self.client.pubsub()


store = RedisStore()
