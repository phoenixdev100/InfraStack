"""Pinned, checksum-verified tool installation shared by the setup scripts.

Design:
  * tools.yaml       - human-edited versions and URL templates.
  * tools.lock.json  - generated; resolved URL + digest per tool/platform.
  * .tools/bin       - install location (git-ignored).

Only the Python standard library and PyYAML are required.
"""

from __future__ import annotations

import bz2
import hashlib
import io
import json
import os
import platform
import stat
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SETUP_DIR = Path(__file__).resolve().parent
MANIFEST = SETUP_DIR / "tools.yaml"
LOCKFILE = SETUP_DIR / "tools.lock.json"
TOOLS_BIN = REPO_ROOT / ".tools" / "bin"
USER_AGENT = "production-infrastructure-blueprint-toolchain/1.0"


def current_platform() -> str:
    system = {"Linux": "linux", "Darwin": "darwin", "Windows": "windows"}.get(platform.system())
    machine = platform.machine().lower()
    arch = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(machine)
    if not system or not arch:
        raise SystemExit(f"Unsupported platform: {platform.system()} {platform.machine()}")
    return f"{system}-{arch}"


def exe_name(tool: str, plat: str | None = None) -> str:
    plat = plat or current_platform()
    return f"{tool}.exe" if plat.startswith("windows") else tool


def fetch(url: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310 - https tool downloads, checksum-verified
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - https tool downloads, checksum-verified
        return resp.read()


def digest(data: bytes, algo: str) -> str:
    return hashlib.new(algo, data).hexdigest()


def parse_checksum_file(text: str) -> dict[str, str]:
    """Parse `<hex>  <filename>` style checksum files (GNU coreutils format)."""
    result: dict[str, str] = {}
    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2:
            result[parts[-1].lstrip("*").split("/")[-1]] = parts[0].lower()
    return result


def load_manifest() -> dict:
    import yaml  # local import keeps install_tools usable for error messages

    with MANIFEST.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_lock() -> dict:
    if not LOCKFILE.exists():
        raise SystemExit(f"{LOCKFILE} missing - run scripts/setup/update_tool_checksums.py")
    return json.loads(LOCKFILE.read_text(encoding="utf-8"))


def extract(data: bytes, url: str, member: str | None) -> bytes:
    """Return the executable bytes from an archive or raw download."""
    name = url.rsplit("/", 1)[-1]
    if name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            return zf.read(member)
    if name.endswith((".tar.gz", ".tgz", ".tar.xz")):
        with tarfile.open(fileobj=io.BytesIO(data)) as tf:
            fh = tf.extractfile(member)
            if fh is None:
                raise RuntimeError(f"{member} not found in {name}")
            return fh.read()
    if name.endswith(".bz2"):
        return bz2.decompress(data)
    return data


def install(tool: str, entry: dict, plat: str) -> Path:
    data = fetch(entry["url"])
    actual = digest(data, entry["algo"])
    if actual != entry["digest"]:
        raise RuntimeError(f"{tool}: checksum mismatch for {entry['url']}\n  expected {entry['digest']}\n  actual   {actual}")
    binary = extract(data, entry["url"], entry.get("member"))
    TOOLS_BIN.mkdir(parents=True, exist_ok=True)
    target = TOOLS_BIN / exe_name(tool, plat)
    target.write_bytes(binary)
    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    (TOOLS_BIN / f".{tool}.version").write_text(entry["version"], encoding="utf-8")
    return target


def installed_version(tool: str) -> str | None:
    marker = TOOLS_BIN / f".{tool}.version"
    return marker.read_text(encoding="utf-8").strip() if marker.exists() else None


def main_install(argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Install pinned, checksum-verified tools into .tools/bin")
    parser.add_argument("tools", nargs="*", help="tool names (default: all)")
    parser.add_argument("--force", action="store_true", help="reinstall even if the pinned version is present")
    args = parser.parse_args(argv)

    lock = load_lock()
    plat = current_platform()
    wanted = args.tools or sorted(lock["tools"])
    failures = 0
    for tool in wanted:
        spec = lock["tools"].get(tool)
        if spec is None:
            print(f"[FAIL] {tool}: not in lock file")
            failures += 1
            continue
        entry = spec["artifacts"].get(plat)
        if entry is None:
            print(f"[NOT RUN] {tool}: no artifact for {plat}")
            continue
        entry = {**entry, "version": spec["version"]}
        if not args.force and installed_version(tool) == spec["version"] and (TOOLS_BIN / exe_name(tool)).exists():
            print(f"[OK] {tool} {spec['version']} already installed")
            continue
        try:
            path = install(tool, entry, plat)
            print(f"[OK] {tool} {spec['version']} -> {path.relative_to(REPO_ROOT)}")
        except Exception as exc:  # report and continue with remaining tools
            print(f"[FAIL] {tool}: {exc}")
            failures += 1
    return 1 if failures else 0


def main_update(argv: list[str]) -> int:
    manifest = load_manifest()
    lock: dict = {"_comment": "Generated by update_tool_checksums.py - do not edit by hand.", "tools": {}}
    cache: dict[str, dict[str, str]] = {}
    errors = 0
    for tool, spec in manifest["tools"].items():
        version = spec["version"]
        cs = spec.get("checksums", {})
        algo = cs.get("algo", "sha256")
        out = {"version": version, "artifacts": {}}
        for plat, art in spec["artifacts"].items():
            url = art["url"].format(v=version)
            member = art.get("member", "").format(v=version) or None
            fname = url.rsplit("/", 1)[-1]
            try:
                if cs.get("compute"):
                    value, source = digest(fetch(url), algo), "computed-from-download"
                elif "per_file_suffix" in cs:
                    value = fetch(url + cs["per_file_suffix"]).decode().split()[0].lower()
                    source = url + cs["per_file_suffix"]
                else:
                    sums_url = cs["url"].format(v=version)
                    if sums_url not in cache:
                        cache[sums_url] = parse_checksum_file(fetch(sums_url).decode())
                    value, source = cache[sums_url][fname.replace("%2F", "/")], sums_url
                out["artifacts"][plat] = {"url": url, "member": member, "algo": algo, "digest": value, "source": source}
                print(f"[OK] {tool} {version} {plat}")
            except Exception as exc:
                print(f"[FAIL] {tool} {plat}: {exc}")
                errors += 1
        lock["tools"][tool] = out
    LOCKFILE.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {LOCKFILE.relative_to(REPO_ROOT)}")
    return 1 if errors else 0


def resolve_tool(name: str) -> str | None:
    """Locate a tool: .tools/bin, then the repo virtualenv, node_modules, then PATH."""
    import shutil

    candidates = [TOOLS_BIN / exe_name(name)]
    venv = REPO_ROOT / ".venv"
    candidates += [venv / "Scripts" / f"{name}.exe", venv / "bin" / name]
    candidates += [REPO_ROOT / "node_modules" / ".bin" / (f"{name}.cmd" if os.name == "nt" else name)]
    for c in candidates:
        if c.exists():
            return str(c)
    return shutil.which(name)


if __name__ == "__main__":
    sys.exit(main_install(sys.argv[1:]))
