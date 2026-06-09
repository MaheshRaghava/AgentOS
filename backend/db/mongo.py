"""
MongoDB client — saves completed runs for the dashboard history view.
Uses Motor (async MongoDB driver) so it never blocks FastAPI.
Falls back gracefully if MongoDB is not connected.
"""
from datetime import datetime
from typing import Optional

from config import settings


class MongoDB:

    def __init__(self):
        self._client = None
        self._db = None

    async def connect(self):
        try:
            import motor.motor_asyncio as motor
            self._client = motor.AsyncIOMotorClient(settings.mongodb_uri)
            self._db = self._client[settings.mongodb_db_name]
            # Test connection
            await self._client.admin.command("ping")
            print("[MongoDB] Connected ✓")
        except Exception as e:
            print(f"[MongoDB] Not connected (runs won't be saved to history): {e}")
            self._client = None
            self._db = None

    async def disconnect(self):
        if self._client:
            self._client.close()

    async def save_run_output(self, run_id: str, goal: str, output: str) -> None:
        """Save a completed run to the runs collection."""
        if self._db is None:
            print("[MongoDB] No database connection, skipping save")
            return
        try:
            await self._db.runs.update_one(
                {"run_id": run_id},
                {"$set": {
                    "run_id":       run_id,
                    "goal":         goal,
                    "final_output": output,
                    "completed_at": datetime.utcnow(),
                }},
                upsert=True,
            )
            print(f"[MongoDB] Saved run {run_id} to history")
        except Exception as e:
            print(f"[MongoDB] Save failed: {e}")

    async def get_run_history(self, limit: int = 20) -> list[dict]:
        """Fetch recent runs for the dashboard history panel."""
        if self._db is None:
            return []
        try:
            cursor = self._db.runs\
                .find({}, {"_id": 0})\
                .sort("completed_at", -1)\
                .limit(limit)
            return await cursor.to_list(length=limit)
        except Exception as e:
            print(f"[MongoDB] Fetch failed: {e}")
            return []

    async def get_run(self, run_id: str) -> Optional[dict]:
        if self._db is None:
            return None
        try:
            return await self._db.runs.find_one({"run_id": run_id}, {"_id": 0})
        except Exception:
            return None


mongo_db = MongoDB()