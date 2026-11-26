"""Repository security and quality policies implemented in Python.

These are deliberately dependency-free so they run everywhere. In a cluster,
the same intent is enforced at admission time by Pod Security Admission and
the Kyverno policies in kubernetes/policies/ (defence in depth).

Exemptions are explicit and auditable:
  * Kubernetes: annotation  policy.blueprint.example.com/exempt: "rule-a,rule-b"
                plus        policy.blueprint.example.com/exempt-reason: "<why>"
  * Compose:    service key x-policy-exempt: {rules: [...], reason: "..."}
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import yaml

from .core import REPO_ROOT, Finding, repo_files

EXEMPT_KEY = "policy.blueprint.example.com/exempt"
EXEMPT_REASON_KEY = "policy.blueprint.example.com/exempt-reason"

WORKLOAD_KINDS = {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob", "Pod", "ReplicaSet"}
LONG_RUNNING = {"Deployment", "StatefulSet", "DaemonSet"}
SECRET_KEY_RE = re.compile(r"(PASSWORD|PASSWD|SECRET|TOKEN|API_KEY|PRIVATE_KEY|ACCESS_KEY|CREDENTIAL)", re.I)
PLACEHOLDER_RE = re.compile(
    r"^(|CHANGE_ME.*|YOUR_[A-Z0-9_]+|<[^>]+>|\$\{[^}]+\}|example.*|changeme|dummy.*|test.*|placeholder.*|REPLACE_ME.*|xxx+|\*+)$",
    re.I,
)


# --------------------------------------------------------------------------
# Kubernetes
# --------------------------------------------------------------------------
def load_yaml_docs(path: Path) -> list:
    with path.open(encoding="utf-8") as fh:
        return [d for d in yaml.safe_load_all(fh) if d is not None]


def is_k8s_manifest(path: Path) -> bool:
    try:
        docs = load_yaml_docs(path)
    except Exception:
        return False
    return bool(docs) and all(isinstance(d, dict) and "apiVersion" in d and "kind" in d and d.get("kind") != "Kustomization" for d in docs)


def _pod_spec(doc: dict) -> tuple[dict, dict]:
    """Return (pod_spec, pod_metadata) for any workload kind."""
    kind = doc.get("kind")
    spec = doc.get("spec") or {}
    if kind == "Pod":
        return spec, doc.get("metadata") or {}
    tmpl = ((spec.get("jobTemplate") or {}).get("spec") or {}).get("template") or {} if kind == "CronJob" else spec.get("template") or {}
    return tmpl.get("spec") or {}, tmpl.get("metadata") or {}


def _exemptions(*metas: dict) -> tuple[set[str], bool]:
    rules: set[str] = set()
    has_reason = True
    for m in metas:
        ann = (m or {}).get("annotations") or {}
        if EXEMPT_KEY in ann:
            rules |= {r.strip() for r in str(ann[EXEMPT_KEY]).split(",") if r.strip()}
            has_reason = has_reason and bool(str(ann.get(EXEMPT_REASON_KEY, "")).strip())
    return rules, has_reason


def check_k8s_doc(doc: dict, label: str) -> list[Finding]:
    kind = doc.get("kind")
    name = (doc.get("metadata") or {}).get("name", "?")
    where = f"{label} {kind}/{name}"
    out: list[Finding] = []

    if (kind == "Secret" and doc.get("data")) or (kind == "Secret" and doc.get("stringData")):
        values = list((doc.get("data") or {}).values()) + list((doc.get("stringData") or {}).values())
        if not all(PLACEHOLDER_RE.match(str(v)) or str(v).startswith("CHANGE_ME") for v in values):
            out.append(Finding(where, "Secret contains non-placeholder values; use External Secrets/SOPS", "no-inline-secrets"))

    if kind == "Service" and (doc.get("spec") or {}).get("type") == "NodePort":
        rules, _ = _exemptions(doc.get("metadata") or {})
        if "nodeport" not in rules:
            out.append(Finding(where, "NodePort services bypass ingress controls", "nodeport"))

    if kind not in WORKLOAD_KINDS:
        return out

    pod, pod_meta = _pod_spec(doc)
    exempt, has_reason = _exemptions(doc.get("metadata") or {}, pod_meta)
    if exempt and not has_reason:
        out.append(Finding(where, f"exemptions {sorted(exempt)} lack {EXEMPT_REASON_KEY}", "exempt-reason"))

    def need(rule: str, ok: bool, msg: str):
        if not ok and rule not in exempt:
            out.append(Finding(where, msg, rule))

    psc = pod.get("securityContext") or {}
    for flag in ("hostNetwork", "hostPID", "hostIPC"):
        need("host-namespaces", not pod.get(flag), f"{flag}: true is not allowed")
    need(
        "automount-token",
        pod.get("automountServiceAccountToken") is False,
        "set automountServiceAccountToken: false (mount explicitly only when the API is needed)",
    )
    need(
        "seccomp",
        ((psc.get("seccompProfile") or {}).get("type") in ("RuntimeDefault", "Localhost")),
        "pod securityContext.seccompProfile.type must be RuntimeDefault",
    )
    for vol in pod.get("volumes") or []:
        need("host-path", "hostPath" not in vol, f"hostPath volume '{vol.get('name')}' is not allowed")

    containers = [("container", c) for c in pod.get("containers") or []]
    containers += [("initContainer", c) for c in pod.get("initContainers") or []]
    need("containers", bool(containers), "workload defines no containers")
    for ctype, c in containers:
        cname = f"{ctype} '{c.get('name')}'"
        image = str(c.get("image", ""))
        tag_part = image.rsplit("/", 1)[-1]
        need(
            "image-tag",
            "@sha256:" in image or (":" in tag_part and not tag_part.endswith(":latest")),
            f"{cname}: image '{image}' must use an explicit non-latest tag or digest",
        )
        csc = c.get("securityContext") or {}
        need("non-root", csc.get("runAsNonRoot", psc.get("runAsNonRoot")) is True, f"{cname}: runAsNonRoot must be true")
        need("privileged", not csc.get("privileged"), f"{cname}: privileged containers are not allowed")
        need("privilege-escalation", csc.get("allowPrivilegeEscalation") is False, f"{cname}: allowPrivilegeEscalation must be false")
        drops = [str(x).upper() for x in ((csc.get("capabilities") or {}).get("drop") or [])]
        need("drop-capabilities", "ALL" in drops, f"{cname}: capabilities.drop must include ALL")
        need("read-only-rootfs", csc.get("readOnlyRootFilesystem") is True, f"{cname}: readOnlyRootFilesystem must be true")
        res = c.get("resources") or {}
        req, lim = res.get("requests") or {}, res.get("limits") or {}
        need("resources", "cpu" in req and "memory" in req, f"{cname}: resources.requests.cpu and .memory are required")
        need("resources", "memory" in lim, f"{cname}: resources.limits.memory is required")
        if ctype == "container" and kind in LONG_RUNNING:
            need("probes", "readinessProbe" in c, f"{cname}: readinessProbe is required")
            need("probes", "livenessProbe" in c, f"{cname}: livenessProbe is required")
        for env in c.get("env") or []:
            ename = str(env.get("name", ""))
            if (
                SECRET_KEY_RE.search(ename)
                and not ename.upper().endswith(("_FILE", "_PATH", "_REF", "_ENV"))
                and "value" in env
                and not PLACEHOLDER_RE.match(str(env["value"]))
            ):
                out.append(Finding(where, f"{cname}: env {ename} has an inline secret value; use secretKeyRef", "no-inline-secrets"))
    return out


def check_k8s_file(path: Path, label: str) -> list[Finding]:
    try:
        docs = load_yaml_docs(path)
    except Exception as exc:
        return [Finding(label, f"YAML parse error: {exc}", "yaml")]
    out: list[Finding] = []
    for doc in docs:
        if isinstance(doc, dict) and doc.get("kind") == "List":
            for item in doc.get("items") or []:
                out += check_k8s_doc(item, label)
        elif isinstance(doc, dict):
            out += check_k8s_doc(doc, label)
    return out


# --------------------------------------------------------------------------
# Docker Compose
# --------------------------------------------------------------------------
DB_IMAGES = re.compile(r"(^|/)(postgres|mysql|mariadb|redis|valkey|mongo|memcached|rabbitmq|kafka|nats|elasticsearch|opensearch)[:@]")


def _compose_exempt(svc: dict) -> set[str]:
    ex = svc.get("x-policy-exempt") or {}
    return set(ex.get("rules", [])) if ex.get("reason") else set()


def check_compose_file(path: Path, label: str) -> list[Finding]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return [Finding(label, f"YAML parse error: {exc}", "yaml")]
    out: list[Finding] = []
    if "version" in data:
        out.append(Finding(label, "top-level 'version' is obsolete in the Compose Specification", "compose-version"))
    for name, svc in (data.get("services") or {}).items():
        where = f"{label} service '{name}'"
        svc = svc or {}
        if svc.get("x-policy-exempt") and not (svc["x-policy-exempt"] or {}).get("reason"):
            out.append(Finding(where, "x-policy-exempt requires a 'reason'", "exempt-reason"))
        exempt = _compose_exempt(svc)

        def need(rule: str, ok: bool, msg: str, exempt: set = exempt, where: str = where):
            if not ok and rule not in exempt:
                out.append(Finding(where, msg, rule))

        image = str(svc.get("image", ""))
        if image:
            tag_part = image.rsplit("/", 1)[-1]
            need(
                "image-tag",
                "@sha256:" in image or (":" in tag_part and not tag_part.endswith(":latest") and "${" not in tag_part.split(":")[0]),
                f"image '{image}' must be pinned to an explicit tag or digest",
            )
        else:
            need("image-tag", "build" in svc, "service needs image or build")
        need("privileged", not svc.get("privileged"), "privileged: true is not allowed")
        need("host-network", svc.get("network_mode") != "host", "network_mode: host is not allowed")
        need(
            "restart",
            svc.get("restart") in ("unless-stopped", "always", "on-failure") or bool((svc.get("deploy") or {}).get("restart_policy")),
            "set a restart policy",
        )
        hc = svc.get("healthcheck") or {}
        need("healthcheck", bool(hc) and not hc.get("disable"), "a healthcheck is required")
        need(
            "no-new-privileges",
            any("no-new-privileges:true" in str(s).replace(" ", "") for s in svc.get("security_opt") or []),
            "security_opt must include no-new-privileges:true",
        )
        need("cap-drop", "ALL" in [str(c).upper() for c in svc.get("cap_drop") or []], "cap_drop: [ALL] is required")
        limits = ((svc.get("deploy") or {}).get("resources") or {}).get("limits") or {}
        need("resources", "memory" in limits or "mem_limit" in svc, "a memory limit is required (deploy.resources.limits.memory)")
        env = svc.get("environment") or {}
        items = env.items() if isinstance(env, dict) else (e.split("=", 1) if "=" in e else (e, "") for e in env)
        for key, value in items:
            if (
                SECRET_KEY_RE.search(str(key))
                and not str(key).endswith("_FILE")
                and value is not None
                and not PLACEHOLDER_RE.match(str(value))
            ):
                out.append(Finding(where, f"environment {key} has an inline secret; use ${{VAR}} or Docker secrets", "no-inline-secrets"))
        if DB_IMAGES.search(image):
            for p in svc.get("ports") or []:
                spec = str(p.get("published", "")) + ":" + str(p.get("host_ip", "")) if isinstance(p, dict) else str(p)
                host_ip = p.get("host_ip") if isinstance(p, dict) else (spec.split(":")[0] if spec.count(":") >= 2 else None)
                need("db-exposure", host_ip in ("127.0.0.1", "::1"), f"data service publishes port {spec} beyond localhost")
    return out


# --------------------------------------------------------------------------
# Example/template secrets must be placeholders
# --------------------------------------------------------------------------
def check_example_secrets(path: Path, label: str) -> list[Finding]:
    out = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        m = re.match(r"^\s*(?:export\s+)?([A-Za-z0-9_.-]+)\s*[=:]\s*(.*?)\s*$", line)
        if not m or line.lstrip().startswith("#"):
            continue
        key, value = m.group(1), m.group(2).strip().strip("'\"")
        value = value.split(" #", 1)[0].strip()
        if SECRET_KEY_RE.search(key) and not key.upper().endswith(("_FILE", "_PATH", "_REF", "_ENV")) and not PLACEHOLDER_RE.match(value):
            out.append(Finding(f"{label}:{n}", f"{key} must be a placeholder such as CHANGE_ME", "example-secrets"))
    return out


# --------------------------------------------------------------------------
# Container image references: pinned, not latest
# --------------------------------------------------------------------------
IMAGE_LINE = re.compile(r"^\s*(?:-\s*)?image:\s*['\"]?([^\s'\"#]+)")
FROM_LINE = re.compile(r"^\s*FROM\s+(?:--platform=\S+\s+)?(\S+)", re.I)


def check_image_references(path: Path, label: str) -> list[Finding]:
    out = []
    stages: set[str] = set()
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        m = FROM_LINE.match(line) if path.name.startswith("Dockerfile") or path.suffix == ".Dockerfile" else IMAGE_LINE.match(line)
        if not m:
            continue
        ref = m.group(1)
        if path.name.startswith("Dockerfile"):
            as_match = re.search(r"\s+AS\s+(\S+)", line, re.I)
            if as_match:
                stages.add(as_match.group(1).lower())
            if ref.lower() in stages or ref == "scratch":
                continue
        if "{{" in ref or ref.startswith("$"):
            continue
        last = ref.rsplit("/", 1)[-1]
        if "@sha256:" not in ref and (":" not in last or last.endswith(":latest")):
            out.append(Finding(f"{label}:{n}", f"image '{ref}' must be pinned (tag or digest), never latest", "image-pinning"))
    return out


# --------------------------------------------------------------------------
# Repository hygiene
# --------------------------------------------------------------------------
ALLOWED_EMPTY = {"__init__.py", "py.typed"}
SPECIAL_DIR_NAMES = re.compile(r"^(\.[a-z0-9-]+|[a-z0-9][a-z0-9._-]*|__[a-z]+__|[A-Z][A-Za-z]+)$")


def check_repo_hygiene(args: dict) -> list[Finding]:
    out: list[Finding] = []
    files = repo_files()
    max_bytes = args.get("max_file_kb", 512) * 1024
    seen: dict[str, str] = {}
    dirs: set[str] = set()
    allow_dup = [re.compile(p) for p in args.get("allow_duplicates", [])]
    for f in files:
        p = REPO_ROOT / f
        parts = f.split("/")
        dirs.update("/".join(parts[:i]) for i in range(1, len(parts)))
        if " " in f:
            out.append(Finding(f, "paths must not contain spaces", "naming"))
        for d in parts[:-1]:
            # .github/ISSUE_TEMPLATE is a GitHub-required uppercase name.
            if f == ".github/ISSUE_TEMPLATE" or (d == "ISSUE_TEMPLATE" and parts[0] == ".github"):
                continue
            if not SPECIAL_DIR_NAMES.match(d):
                out.append(Finding(f, f"directory '{d}' must be lowercase kebab-case", "naming"))
                break
        size = p.stat().st_size
        if size == 0 and p.name not in ALLOWED_EMPTY:
            out.append(Finding(f, "empty file (no placeholders allowed)", "empty-file"))
        if size > max_bytes:
            out.append(Finding(f, f"file larger than {args.get('max_file_kb', 512)} KiB", "large-file"))
        if p.name == ".gitkeep":
            out.append(Finding(f, ".gitkeep placeholders are not allowed; add real content", "empty-dir"))
        if size >= args.get("dup_min_bytes", 200) and not any(r.search(f) for r in allow_dup):
            data = p.read_bytes().replace(b"\r\n", b"\n")
            h = hashlib.sha256(data).hexdigest()
            if h in seen:
                out.append(Finding(f, f"identical to {seen[h]} (duplicate configuration)", "duplicate"))
            else:
                seen[h] = f
        if p.suffix not in (".ps1", ".psm1", ".psd1", ".bat", ".cmd") and size and size < max_bytes:
            try:
                if b"\r\n" in p.read_bytes():
                    out.append(Finding(f, "CRLF line endings (repository standard is LF)", "line-endings"))
            except OSError:
                pass
    for d in sorted(dirs):
        depth = d.count("/") + 1
        if d.startswith((".", "node_modules")) or any(d.startswith(x) for x in args.get("readme_exempt", [])):
            continue
        if depth <= args.get("readme_depth", 2) and f"{d}/README.md" not in files:
            out.append(Finding(d + "/", "directory requires a README.md", "readme"))
    return out


# --------------------------------------------------------------------------
# Markdown relative links
# --------------------------------------------------------------------------
LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def check_markdown_links(files: list[str]) -> list[Finding]:
    out = []
    all_files = set(repo_files())
    all_dirs = {"/".join(f.split("/")[:i]) for f in all_files for i in range(1, f.count("/") + 1)}
    for f in files:
        text = (REPO_ROOT / f).read_text(encoding="utf-8")
        text = re.sub(r"```.*?```", "", text, flags=re.S)
        for target in LINK_RE.findall(text):
            if re.match(r"^[a-z]+:", target) or target.startswith("#"):
                continue
            rel = target.split("#", 1)[0]
            if not rel:
                continue
            resolved = (Path(f).parent / rel).as_posix()
            norm = Path(resolved).as_posix()
            parts: list[str] = []
            for part in norm.split("/"):
                if part == "..":
                    if parts:
                        parts.pop()
                elif part not in (".", ""):
                    parts.append(part)
            norm = "/".join(parts)
            if norm not in all_files and norm not in all_dirs:
                out.append(Finding(f, f"broken relative link: {target}", "md-links"))
    return out
