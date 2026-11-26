"""Check handlers referenced by tests/matrix.yaml.

Each handler receives (check: dict, files: list[str]) and returns
(status, details). Raise core.ToolMissing to report NOT RUN.
"""

from __future__ import annotations

import configparser
import json
import os
import tempfile
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

from . import policies
from .core import (
    FAIL,
    NOT_RUN,
    PASS,
    REPO_ROOT,
    ToolMissing,
    chunks,
    docker_available,
    run,
    tool,
)

RENDER_DIR = REPO_ROOT / "reports" / "generated" / "rendered"


def _expand(template: list[str], files: list[str] | None = None, file: str | None = None) -> list[str]:
    out: list[str] = []
    for part in template:
        if part == "{files}":
            out += files or []
        elif part.startswith("{tool:") and part.endswith("}"):
            out.append(tool(part[6:-1]))
        else:
            out.append(
                part.replace("{file}", file or "")
                .replace("{dir}", str(Path(file).parent.as_posix()) if file else "")
                .replace("{root}", REPO_ROOT.as_posix())
            )
    return out


def _status(details: list[str]) -> tuple[str, list[str]]:
    return (FAIL if details else PASS), details


# --------------------------------------------------------------------------
# Generic external command
# --------------------------------------------------------------------------
def command(check: dict, files: list[str]):
    args = check.get("args", {})
    template = args["command"]
    mode = check.get("mode", "batch")
    cwd_mode = args.get("cwd", "root")
    details: list[str] = []
    if mode == "once":
        units = [(None, None)]
    elif mode == "each":
        units = [(None, f) for f in files]
    else:
        units = [(batch, None) for batch in chunks(files)]
    for batch, single in units:
        cmd = _expand(template, files=batch, file=single)
        cwd = REPO_ROOT / Path(single).parent if (single and cwd_mode == "file-dir") else REPO_ROOT
        if cwd_mode == "file-dir" and single:
            cmd = [c.replace(single, Path(single).name) if c == single else c for c in cmd]
        code, out = run(cmd, cwd=cwd, timeout=args.get("timeout", 900))
        if code != 0:
            label = single or (f"{len(batch)} files" if batch else "repository")
            details.append(f"{label}: exit {code}\n{out[-4000:]}")
    return _status(details)


# --------------------------------------------------------------------------
# Built-in syntax checks (no external tools)
# --------------------------------------------------------------------------
def yaml_syntax(check: dict, files: list[str]):
    details = []
    for f in files:
        try:
            with open(REPO_ROOT / f, encoding="utf-8") as fh:
                list(yaml.safe_load_all(fh))
        except Exception as exc:  # report parser error verbatim
            details.append(f"{f}: {exc}")
    return _status(details)


def json_syntax(check: dict, files: list[str]):
    details = []
    for f in files:
        try:
            json.loads((REPO_ROOT / f).read_text(encoding="utf-8"))
        except Exception as exc:
            details.append(f"{f}: {exc}")
    return _status(details)


def toml_syntax(check: dict, files: list[str]):
    details = []
    for f in files:
        try:
            tomllib.loads((REPO_ROOT / f).read_text(encoding="utf-8"))
        except Exception as exc:
            details.append(f"{f}: {exc}")
    return _status(details)


def xml_syntax(check: dict, files: list[str]):
    details = []
    for f in files:
        try:
            ET.parse(REPO_ROOT / f)  # noqa: S314 - repository-controlled input
        except Exception as exc:
            details.append(f"{f}: {exc}")
    return _status(details)


def ini_syntax(check: dict, files: list[str]):
    details = []
    for f in files:
        parser = configparser.ConfigParser(strict=True, interpolation=None, allow_no_value=True)
        try:
            parser.read_string((REPO_ROOT / f).read_text(encoding="utf-8"), source=f)
        except Exception as exc:
            details.append(f"{f}: {exc}")
    return _status(details)


def jsonschema_map(check: dict, files: list[str]):
    """Validate data files against JSON Schemas: args.mappings = [{schema, include}]."""
    import jsonschema

    from .core import select

    details = []
    for mapping in check["args"]["mappings"]:
        schema = json.loads((REPO_ROOT / mapping["schema"]).read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
        for f in select(mapping["include"], mapping.get("exclude")):
            text = (REPO_ROOT / f).read_text(encoding="utf-8")
            docs = [json.loads(text)] if f.endswith(".json") else [d for d in yaml.safe_load_all(text) if d is not None]
            for data in docs:
                expect_invalid = "/invalid/" in f
                errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
                if expect_invalid and not errors:
                    details.append(f"{f}: expected schema violations (negative fixture) but none found")
                elif not expect_invalid:
                    details += [f"{f}: {'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors]
    return _status(details)


# --------------------------------------------------------------------------
# Policy checks implemented in Python (see policies.py)
# --------------------------------------------------------------------------
def k8s_policy(check: dict, files: list[str]):
    findings = []
    for f in files:
        findings += policies.check_k8s_file(REPO_ROOT / f, f)
    return _status([str(x) for x in findings])


def compose_policy(check: dict, files: list[str]):
    findings = []
    for f in files:
        findings += policies.check_compose_file(REPO_ROOT / f, f)
    return _status([str(x) for x in findings])


def example_secrets(check: dict, files: list[str]):
    findings = []
    for f in files:
        findings += policies.check_example_secrets(REPO_ROOT / f, f)
    return _status([str(x) for x in findings])


def repo_hygiene(check: dict, files: list[str]):
    return _status([str(x) for x in policies.check_repo_hygiene(check.get("args", {}))])


def markdown_links(check: dict, files: list[str]):
    return _status([str(x) for x in policies.check_markdown_links(files)])


def inventory(check: dict, files: list[str]):
    from .inventory import validate_inventory

    return _status(validate_inventory())


def image_pinning(check: dict, files: list[str]):
    findings = []
    for f in files:
        findings += policies.check_image_references(REPO_ROOT / f, f)
    return _status([str(x) for x in findings])


# --------------------------------------------------------------------------
# Kubernetes rendering pipelines
# --------------------------------------------------------------------------
def _kubeconform(paths: list[str], args: dict) -> list[str]:
    """Validate against every Kubernetes version in args.kubernetes_versions (strict schemas)."""
    details = []
    for version in args.get("kubernetes_versions", ["1.34.0"]):
        cmd = [
            tool("kubeconform"),
            "-strict",
            "-summary",
            "-output",
            "text",
            "-kubernetes-version",
            version,
            "-schema-location",
            "default",
            "-schema-location",
            "https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json",
        ]
        for kind in args.get("skip_kinds", []):
            cmd += ["-skip", kind]
        code, out = run(cmd + paths, timeout=600)
        if code != 0:
            details.append(f"k8s {version}: {out[-6000:]}")
    return details


def kubeconform_files(check: dict, files: list[str]):
    manifests = [f for f in files if policies.is_k8s_manifest(REPO_ROOT / f)]
    details = []
    for batch in chunks(manifests):
        details += _kubeconform(batch, check.get("args", {}))
    return _status(details)


def kustomize_render(check: dict, files: list[str]):
    """Build each kustomization directory, schema-validate and policy-check the output."""
    args = check.get("args", {})
    details = []
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    for f in files:
        directory = Path(f).parent
        code, out = run([tool("kustomize"), "build", directory.as_posix()])
        if code != 0:
            details.append(f"{directory}: kustomize build failed\n{out[-3000:]}")
            continue
        target = RENDER_DIR / ("kustomize-" + directory.as_posix().replace("/", "_") + ".yaml")
        target.write_text(out + "\n", encoding="utf-8")
        details += [f"{directory}: {d}" for d in _kubeconform([target.as_posix()], args)]
        if args.get("policy", True):
            details += [str(x) for x in policies.check_k8s_file(target, f"{directory} (rendered)")]
    return _status(details)


def helm_chart(check: dict, files: list[str]):
    """helm lint --strict + helm template per values file in ci/ -> kubeconform + policy."""
    args = check.get("args", {})
    details = []
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    for f in files:
        chart = Path(f).parent
        values_files = sorted((REPO_ROOT / chart / "ci").glob("*-values.yaml")) or [None]
        for vf in values_files:
            extra = ["-f", vf.as_posix()] if vf else []
            label = f"{chart}" + (f" [{vf.name}]" if vf else "")
            code, out = run([tool("helm"), "lint", "--strict", chart.as_posix(), *extra])
            if code != 0:
                details.append(f"{label}: helm lint failed\n{out[-3000:]}")
                continue
            code, out = run([tool("helm"), "template", "release-name", chart.as_posix(), *extra])
            if code != 0:
                details.append(f"{label}: helm template failed\n{out[-3000:]}")
                continue
            name = "helm-" + chart.name + ("-" + vf.stem if vf else "") + ".yaml"
            target = RENDER_DIR / name
            target.write_text(out + "\n", encoding="utf-8")
            details += [f"{label}: {d}" for d in _kubeconform([target.as_posix()], args)]
            details += [str(x) for x in policies.check_k8s_file(target, f"{label} (rendered)")]
    return _status(details)


# --------------------------------------------------------------------------
# Terraform
# --------------------------------------------------------------------------
def terraform(check: dict, files: list[str]):
    """terraform fmt -check, init -backend=false, validate and (if tests exist) test."""
    tf = tool("terraform")
    dirs = sorted({Path(f).parent for f in files if Path(f).parent.name != "tests"})
    details = []
    code, out = run([tf, "fmt", "-check", "-recursive", "-diff", check["args"]["root"]])
    if code != 0:
        details.append(f"terraform fmt: files need formatting\n{out[-3000:]}")
    for d in dirs:
        code, out = run([tf, f"-chdir={d.as_posix()}", "init", "-backend=false", "-input=false", "-no-color"], timeout=900)
        if code != 0:
            details.append(f"{d}: init failed\n{out[-3000:]}")
            continue
        code, out = run([tf, f"-chdir={d.as_posix()}", "validate", "-no-color"])
        if code != 0:
            details.append(f"{d}: validate failed\n{out[-3000:]}")
        if (REPO_ROOT / d / "tests").is_dir():
            code, out = run([tf, f"-chdir={d.as_posix()}", "test", "-no-color"], timeout=900)
            if code != 0:
                details.append(f"{d}: terraform test failed\n{out[-4000:]}")
    return _status(details)


def tflint(check: dict, files: list[str]):
    exe = tool("tflint")
    config = (REPO_ROOT / check["args"]["config"]).as_posix()
    dirs = sorted({Path(f).parent for f in files if Path(f).parent.name != "tests"})
    code, out = run([exe, "--init", f"--config={config}"], timeout=600)
    if code != 0:
        return FAIL, [f"tflint --init failed\n{out[-2000:]}"]
    details = []
    for d in dirs:
        code, out = run([exe, f"--chdir={d.as_posix()}", f"--config={config}", "--no-color"])
        if code != 0:
            details.append(f"{d}:\n{out[-3000:]}")
    return _status(details)


# --------------------------------------------------------------------------
# Docker-backed validators (nginx -t, haproxy -c, ...). NOT RUN without Docker.
# --------------------------------------------------------------------------
def docker_validate(check: dict, files: list[str]):
    if not docker_available():
        raise ToolMissing("docker")
    args = check["args"]
    docker = tool("docker")
    details = []
    for f in files:
        mount_dir = (REPO_ROOT / Path(f).parent).as_posix() if args.get("mount") == "file-dir" else REPO_ROOT.as_posix()
        rel = Path(f).name if args.get("mount") == "file-dir" else f
        cmd = [docker, "run", "--rm", "--network", "none", "-v", f"{mount_dir}:/work:ro"]
        cmd += args.get("docker_args", [])
        cmd += [args["image"], *[c.replace("{file}", f"/work/{rel}") for c in args["command"]]]
        code, out = run(cmd, timeout=300)
        if code != 0:
            details.append(f"{f}: exit {code}\n{out[-3000:]}")
    return _status(details)


def compose_config(check: dict, files: list[str]):
    if not docker_available():
        raise ToolMissing("docker")
    details = []
    for f in files:
        env_example = REPO_ROOT / Path(f).parent / ".env.example"
        cmd = [tool("docker"), "compose", "-f", f]
        if env_example.exists():
            cmd += ["--env-file", env_example.as_posix()]
        code, out = run([*cmd, "config", "--quiet"])
        if code != 0:
            details.append(f"{f}: {out[-3000:]}")
    return _status(details)


# --------------------------------------------------------------------------
# PowerShell
# --------------------------------------------------------------------------
_PS_PARSE = (
    "$ErrorActionPreference='Stop'; $bad=0; foreach($f in $args){ $t=$null; $e=$null; "
    "[void][System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $f), [ref]$t, [ref]$e); "
    'foreach($x in $e){ Write-Output ("{0}:{1}: {2}" -f $f,$x.Extent.StartLineNumber,$x.Message); $bad=1 } }; exit $bad'
)


def powershell_parse(check: dict, files: list[str]):
    try:
        exe = tool("pwsh")
    except ToolMissing:
        exe = tool("powershell") if os.name == "nt" else tool("pwsh")
    details = []
    for batch in chunks(files, 40):
        with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8") as fh:
            fh.write(_PS_PARSE.replace("$args", "@(" + ",".join(f"'{b}'" for b in batch) + ")"))
            script = fh.name
        try:
            code, out = run([exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", script])
        finally:
            os.unlink(script)
        if code != 0:
            details.append(out[-4000:])
    return _status(details)


def psscriptanalyzer(check: dict, files: list[str]):
    exe = tool("pwsh")
    code, _ = run([exe, "-NoProfile", "-Command", "if (Get-Module -ListAvailable PSScriptAnalyzer) { exit 0 } else { exit 3 }"])
    if code != 0:
        return NOT_RUN, ["PSScriptAnalyzer module not installed: Install-Module PSScriptAnalyzer -Scope CurrentUser"]
    settings = (REPO_ROOT / check["args"]["settings"]).as_posix()
    details = []
    for f in files:
        code, out = run(
            [
                exe,
                "-NoProfile",
                "-Command",
                f"$r = Invoke-ScriptAnalyzer -Path '{f}' -Settings '{settings}'; $r | Format-Table -AutoSize | Out-String -Width 200; "
                "if ($r | Where-Object Severity -in 'Error','Warning') { exit 1 }",
            ]
        )
        if code != 0:
            details.append(f"{f}:\n{out[-3000:]}")
    return _status(details)


# --------------------------------------------------------------------------
# pytest-based suites
# --------------------------------------------------------------------------
def pytest_suite(check: dict, files: list[str]):
    args = check["args"]
    junit = REPO_ROOT / "reports" / "generated" / f"junit-{check['id']}.xml"
    junit.parent.mkdir(parents=True, exist_ok=True)
    cmd = [tool("pytest"), *args.get("paths", []), "-q", "-rs", f"--junitxml={junit.as_posix()}"]
    if args.get("markers"):
        cmd += ["-m", args["markers"]]
    code, out = run(cmd, timeout=args.get("timeout", 1800))
    summary = [
        line for line in out.splitlines() if line.startswith(("SKIPPED", "FAILED", "ERROR")) or " passed" in line or " failed" in line
    ]
    if code == 5:  # no tests collected
        return NOT_RUN, ["pytest collected no tests"]
    return (PASS if code == 0 else FAIL), (summary if code == 0 else [out[-6000:]])


HANDLERS = {name: obj for name, obj in globals().items() if callable(obj) and not name.startswith("_")}
