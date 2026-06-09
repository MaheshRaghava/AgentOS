"""
Code execution tool — runs Python code in a subprocess sandbox.
"""
import asyncio
import subprocess
import sys
import tempfile
import os
from typing import TypedDict


class ExecResult(TypedDict):
    success: bool
    stdout: str
    stderr: str
    exit_code: int


async def execute_code(code: str, timeout: int = 30) -> ExecResult:
    """
    Write code to a temp file and run it in a subprocess.
    Returns stdout, stderr, exit_code, and success flag.
    
    Default timeout increased from 15 to 30 seconds for complex scripts.
    """
    # Write to a temp .py file
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".py",
        delete=False,
        encoding="utf-8",
    ) as f:
        f.write(code)
        tmp_path = f.name

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: _run_subprocess(tmp_path, timeout),
        )
        return result
    finally:
        # Always clean up the temp file
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def _run_subprocess(script_path: str, timeout: int) -> ExecResult:
    try:
        proc = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            # Restrict environment — no network access tricks, clean env
            env={
                "PATH": os.environ.get("PATH", ""),
                "PYTHONPATH": "",
            },
        )
        return ExecResult(
            success=proc.returncode == 0,
            stdout=proc.stdout,
            stderr=proc.stderr,
            exit_code=proc.returncode,
        )
    except subprocess.TimeoutExpired:
        return ExecResult(
            success=False,
            stdout="",
            stderr=f"Execution timed out after {timeout} seconds. Consider simplifying the code or increasing the timeout.",
            exit_code=-1,
        )
    except Exception as e:
        return ExecResult(
            success=False,
            stdout="",
            stderr=str(e),
            exit_code=-1,
        )