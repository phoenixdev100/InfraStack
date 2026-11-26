"""Core primitives: results, file discovery, glob matching, tool resolution, subprocess helpers."""

from __future__ import annotations

import functools
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "setup"))

from toolchain import TOOLS_BIN, resolve_tool  # noqa: E402

PASS, FAIL, NOT_RUN, NO_TARGETS = "PASS", "FAIL", "NOT RUN", "NO TARGETS"

INSTALL_HINTS = {
    "docker": "Install Docker Engine / Docker Desktop: https://docs.docker.com/get-docker/",
    "pwsh": "Install PowerShell 7: https://learn.microsoft.com/powershell/scripting/install/installing-powershell",
    "ansible-lint": "pip install -r requirements/ansible.txt (Linux/macOS/WSL only)",
    "ansible-playbook": "pip install -r requirements/ansible.txt (Linux/macOS/WSL only)",
    "checkov": "pip install -r requirements/security.txt",
    "markdownlint-cli2": "npm ci",
    "k6": "https://grafana.com/docs/k6/latest/set-up/install-k6/",
    "ruff": "pip install -r requirements/dev.txt",
    "yamllint": "pip install -r requirements/dev.txt",
    "pytest": "pip install -r requirements/dev.txt",
}


def install_hint(tool: str) -> str:
    return INSTALL_HINTS.get(tool, "python scripts/setup/install_tools.py " + tool)


@dataclass
class Finding:
    file: str
    message: str
    rule: str = ""

    def __str__(self) -> str:
        prefix = f"[{self.rule}] " if self.rule else ""
        return f"{self.file}: {prefix}{self.message}"


@dataclass
class Result:
    check_id: str
    stage: str
    status: str
    targets: int = 0
    duration_s: float = 0.0
    details: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.check_id,
            "stage": self.stage,
            "status": self.status,
            "targets": self.targets,
            "duration_s": round(self.duration_s, 2),
            "details": self.details[:200],
        }


class ToolMissing(Exception):
    def __init__(self, tool: str):
        super().__init__(tool)
        self.tool = tool


@functools.lru_cache(maxsize=1)
def repo_files() -> tuple[str, ...]:
    """Tracked + untracked-but-not-ignored files, POSIX relative paths."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "-co", "--exclude-standard", "-z"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=True,
        ).stdout.decode("utf-8")
        files = [f for f in out.split("\0") if f and (REPO_ROOT / f).is_file()]
    except (OSError, subprocess.CalledProcessError):
        skip = {".git", ".venv", ".tools", "node_modules", ".terraform", "__pycache__"}
        files = []
        for root, dirs, names in os.walk(REPO_ROOT):
            dirs[:] = [d for d in dirs if d not in skip]
            files += [Path(root, n).relative_to(REPO_ROOT).as_posix() for n in names]
    return tuple(sorted(files))


@functools.lru_cache(maxsize=512)
def glob_regex(pattern: str) -> re.Pattern:
    """Translate a gitignore-like glob (supports **, *, ?, {a,b}) to a regex."""
    i, out = 0, ["^"]
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
            continue
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
            continue
        if c == "*":
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        elif c == "{":
            end = pattern.index("}", i)
            out.append("(?:" + "|".join(re.escape(p) for p in pattern[i + 1 : end].split(",")) + ")")
            i = end
        else:
            out.append(re.escape(c))
        i += 1
    out.append("$")
    return re.compile("".join(out))


def matches(path: str, patterns: list[str]) -> bool:
    return any(glob_regex(p).match(path) for p in patterns)


def select(include: list[str], exclude: list[str] | None = None) -> list[str]:
    exclude = exclude or []
    return [f for f in repo_files() if matches(f, include) and not matches(f, exclude)]


def tool(name: str) -> str:
    found = resolve_tool(name)
    if not found:
        raise ToolMissing(name)
    return found


def tool_env() -> dict[str, str]:
    env = dict(os.environ)
    extra = [str(TOOLS_BIN), str(REPO_ROOT / "node_modules" / ".bin")]
    venv_bin = REPO_ROOT / ".venv" / ("Scripts" if os.name == "nt" else "bin")
    extra.append(str(venv_bin))
    env["PATH"] = os.pathsep.join([*extra, env.get("PATH", "")])
    env.setdefault("CHECKPOINT_DISABLE", "1")  # terraform telemetry
    env.setdefault("TF_IN_AUTOMATION", "1")
    return env


def run(cmd: list[str], cwd: Path | str | None = None, timeout: int = 900, stdin: str | None = None):
    """Run a command, returning (returncode, combined output)."""
    proc = subprocess.run(
        cmd,
        cwd=cwd or REPO_ROOT,
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=tool_env(),
    )
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def chunks(items: list[str], size: int = 80):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def have(name: str) -> bool:
    return resolve_tool(name) is not None or shutil.which(name) is not None


def docker_available() -> bool:
    exe = resolve_tool("docker")
    if not exe:
        return False
    try:
        return subprocess.run([exe, "info"], capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False
