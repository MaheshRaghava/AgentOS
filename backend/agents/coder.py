"""
Coder agent — writes Python code, executes it in a sandbox, self-corrects on failure.
Called by dispatcher when task.worker == WorkerType.CODER
"""
import asyncio
from config import settings
from graph.models import Task
from tools.code_exec import execute_code
from agents.base import BaseAgent

CODER_PROMPT = """You are an expert Python programmer. Write clean, working Python code for the task below.

TASK: {description}

Rules:
- Output ONLY the Python code. No explanation, no markdown, no code fences.
- The code must be self-contained and runnable as a script.
- Print the final result using print() so it appears in stdout.
- Do not use external libraries unless they are standard Python.
- NEVER use input() or any interactive prompts — the code runs non-interactively.
- Instead of input(), use hardcoded example values that demonstrate the functionality clearly.
- If the task asks for a calculator or tool, hardcode 2-3 representative example calls and print their results.
"""

FIX_PROMPT = """The Python code you wrote produced an error. Fix it.

TASK: {description}

PREVIOUS CODE:
{code}

ERROR:
{error}

Rules:
- Output ONLY the fixed Python code. No explanation, no markdown fences.
- NEVER use input() — the code runs non-interactively. Use hardcoded example values instead.
"""

# Dangerous operations that should never be executed
DANGEROUS_KEYWORDS = [
    "os.remove", "os.unlink", "os.rmdir", "os.system",
    "shutil.rmtree", "shutil.move", "shutil.copy",
    "subprocess.run", "subprocess.call", "subprocess.Popen",
    "__import__", "eval(", "exec(",
    "open(", "glob.glob",
]

MAX_RETRIES = 3


class CoderAgent(BaseAgent):

    def __init__(self):
        super().__init__()  # BaseAgent handles model chain

    def _is_dangerous(self, code: str) -> str | None:
        """
        Check for dangerous operations in generated code.
        Returns the matched keyword if dangerous, None if safe.
        """
        for keyword in DANGEROUS_KEYWORDS:
            if keyword in code:
                return keyword
        return None

    async def run(self, task: Task) -> str:
        print(f"[Coder] Starting: {task.name}")

        code = await self._generate_code(task.description)

        # Safety check — block dangerous operations before execution
        danger = self._is_dangerous(code)
        if danger:
            print(f"[Coder] BLOCKED dangerous code — contains: {danger}")
            return f"⚠️ Security: This task would generate code containing `{danger}`, which is not allowed for safety reasons. Please provide a safer coding task."

        last_error = ""

        for attempt in range(MAX_RETRIES):
            print(f"[Coder] Executing code (attempt {attempt + 1}/{MAX_RETRIES})")
            result = await execute_code(code)

            if result["success"]:
                output = result["stdout"].strip() or "Code executed successfully (no output)."
                print(f"[Coder] Success on attempt {attempt + 1}")
                return f"Code:\n```python\n{code}\n```\n\nOutput:\n{output}"

            last_error = result["stderr"] or result.get("error", "Unknown error")
            print(f"[Coder] Attempt {attempt + 1} failed: {last_error[:100]}")

            if attempt < MAX_RETRIES - 1:
                code = await self._fix_code(task.description, code, last_error)

                # Re-check safety after fix attempt
                danger = self._is_dangerous(code)
                if danger:
                    print(f"[Coder] BLOCKED dangerous code after fix — contains: {danger}")
                    return f"⚠️ Security: Cannot execute code containing `{danger}`."

        # All retries exhausted — return code with error info
        return f"Code (with errors after {MAX_RETRIES} attempts):\n```python\n{code}\n```\n\nLast error:\n{last_error}"

    async def _generate_code(self, description: str) -> str:
        prompt = CODER_PROMPT.replace("{description}", description)
        raw = await self.generate_with_fallback(prompt)
        return self._clean_code(raw)

    async def _fix_code(self, description: str, code: str, error: str) -> str:
        prompt = FIX_PROMPT\
            .replace("{description}", description)\
            .replace("{code}", code)\
            .replace("{error}", error)
        raw = await self.generate_with_fallback(prompt)
        return self._clean_code(raw)

    def _clean_code(self, raw: str) -> str:
        """Strip markdown fences if Gemini adds them."""
        import re
        cleaned = re.sub(r"```(?:python)?\s*", "", raw).replace("```", "").strip()
        return cleaned


coder_agent = CoderAgent()

async def run_coder(task: Task) -> str:
    return await coder_agent.run(task)