"""
base.py — BaseAgent with modern google-genai SDK and multi-model fallback.

All agents inherit this class and call:
    text = await self.generate_with_fallback(prompt)

Uses the new google-genai SDK with stateless client.
Timeout of 15s per model call — prevents 60s SDK-internal retry hang.
"""
import asyncio
from google import genai
from google.genai import errors, types
from config import settings


class BaseAgent:

    def __init__(self):
        self.client = genai.Client(api_key=settings.gemini_api_key)

    async def generate_with_fallback(self, prompt: str) -> str:
        last_error = None
        loop = asyncio.get_event_loop()

        for i, model_name in enumerate(settings.gemini_model_chain):
            try:
                response = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda m=model_name: self.client.models.generate_content(
                            model=m,
                            contents=prompt,
                            config=types.GenerateContentConfig(
                                http_options=types.HttpOptions(timeout=10000)
                            ),
                        )
                    ),
                    timeout=15.0,
                )

                if i > 0:
                    print(f"[BaseAgent] ✅ Recovered using fallback model: {model_name}")

                return response.text.strip()

            except asyncio.TimeoutError:
                print(f"[BaseAgent] ⏱️ {model_name} timed out after 15s → trying next model")
                last_error = Exception(f"{model_name} timed out")
                await asyncio.sleep(0.5)
                continue

            except errors.APIError as exc:
                if exc.code in (429, 404, 500, 503, 504):
                    label = {
                        429: "quota",
                        404: "not found",
                        500: "server",
                        503: "server",
                        504: "deadline exceeded",
                    }.get(exc.code, "api")
                    print(f"[BaseAgent] ⚠️ {model_name} {label} error (code {exc.code}) → trying next model")
                    last_error = exc
                    await asyncio.sleep(0.5)
                    continue
                else:
                    print(f"[BaseAgent] ❌ Critical API error in {model_name}: {exc}")
                    raise exc

            except Exception as exc:
                error_str = str(exc).lower()
                # Catch string-based timeout/deadline errors
                if any(e in error_str for e in ("timed out", "deadline", "timeout", "read operation")):
                    print(f"[BaseAgent] ⏱️ {model_name} timeout exception → trying next model")
                    last_error = exc
                    await asyncio.sleep(0.5)
                    continue
                print(f"[BaseAgent] ❌ Unexpected error in {model_name}: {exc}")
                raise exc

        raise RuntimeError(
            f"🚨 All {len(settings.gemini_model_chain)} models exhausted. "
            f"Last error: {last_error}"
        )
