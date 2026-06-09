"""
File read/write tool — sandboxed to a temp directory.
Used by coder agent to save output artifacts (scripts, reports, data files).
"""
import os
import tempfile
from pathlib import Path


# All file operations are sandboxed to this directory
SANDBOX_DIR = Path(tempfile.gettempdir()) / "agentos_sandbox"
SANDBOX_DIR.mkdir(exist_ok=True)


def _safe_path(filename: str) -> Path:
    """Prevent path traversal — all files stay inside SANDBOX_DIR."""
    safe = SANDBOX_DIR / Path(filename).name   # .name strips any directory component
    return safe


async def write_file(filename: str, content: str) -> str:
    """Write content to a sandboxed file. Returns the full path."""
    path = _safe_path(filename)
    path.write_text(content, encoding="utf-8")
    print(f"[FileRW] Written: {path}")
    return str(path)


async def read_file(filename: str) -> str:
    """Read a file from the sandbox. Returns content or error string."""
    path = _safe_path(filename)
    if not path.exists():
        return f"[FileRW] File not found: {filename}"
    return path.read_text(encoding="utf-8")


async def list_files() -> list[str]:
    """List all files currently in the sandbox."""
    return [f.name for f in SANDBOX_DIR.iterdir() if f.is_file()]


async def delete_file(filename: str) -> bool:
    """Delete a file from the sandbox."""
    path = _safe_path(filename)
    if path.exists():
        path.unlink()
        return True
    return False
