"""
WebSocket endpoint — streams task events to the React dashboard in real time.
Also update main.py to include the websocket router (see Commands tab).
"""
import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from graph.redis_store import store

ws_router = APIRouter()


@ws_router.websocket("/ws/{run_id}")
async def websocket_run(websocket: WebSocket, run_id: str):
    """
    Client connects here after POST /goal returns a run_id.
    We subscribe to Redis pub/sub for that run and forward every event.
    """
    await websocket.accept()
    print(f"[WS] Client connected for run: {run_id}")

    # Send current task state immediately on connect
    # so the UI doesn't show a blank screen while waiting for first event
    try:
        run = await store.get_run(run_id)
        if run:
            await websocket.send_json({
                "event": "run_state",
                "run_id": run_id,
                "data": {
                    "status": run.status,
                    "goal": run.goal,
                    "tasks": [
                        {
                            "id":          t.id,
                            "name":        t.name,
                            "worker":      t.worker,
                            "status":      t.status,
                            "description": t.description,
                            "dependencies": t.dependencies,
                        }
                        for t in run.tasks
                    ],
                },
            })
    except Exception as e:
        print(f"[WS] Error sending initial state: {e}")

    # Subscribe to Redis pub/sub channel for this run
    pubsub = store.pubsub()
    await pubsub.subscribe(f"run:{run_id}:pubsub")

    try:
        while True:
            # Poll for new Redis messages every 100ms
            message = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=0.1,
            )

            if message and message.get("type") == "message":
                try:
                    event = json.loads(message["data"])
                    await websocket.send_json(event)

                    # If run is complete, send final output and close
                    if event.get("event") in ("run_completed", "run_failed"):
                        break

                except Exception as e:
                    print(f"[WS] Error forwarding event: {e}")

            # Check if client disconnected
            try:
                await asyncio.wait_for(
                    websocket.receive_text(), timeout=0.01
                )
            except asyncio.TimeoutError:
                pass  # Normal — client is just listening
            except WebSocketDisconnect:
                print(f"[WS] Client disconnected: {run_id}")
                break

            await asyncio.sleep(0.05)

    except WebSocketDisconnect:
        print(f"[WS] Client disconnected: {run_id}")
    except Exception as e:
        print(f"[WS] Error: {e}")
    finally:
        await pubsub.unsubscribe(f"run:{run_id}:pubsub")
        await pubsub.close()
        print(f"[WS] Closed connection: {run_id}")
