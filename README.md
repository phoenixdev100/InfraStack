# InfraStack

**Production Infrastructure Blueprint** — a working library of enterprise-grade
infrastructure configurations, validated by an automated test matrix.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/phoenixdev100/InfraStack/actions/workflows/ci.yml/badge.svg)](https://github.com/phoenixdev100/InfraStack/actions/workflows/ci.yml)
[![InfraStack](https://img.shields.io/badge/project-InfraStack-blue)](https://github.com/phoenixdev100/InfraStack)

> **Naming:** **InfraStack** is the public project name. **PIB**
> (Production Infrastructure Blueprint) remains the internal CLI/framework
> identity (`scripts/pib.py`, `pibkit`, `pib-*` resource names) for
> backward compatibility.

InfraStack is not a collection of snippets — it is a **reference
implementation** you can clone, validate, and adapt. Every configuration is
checked by a declarative validation matrix covering lint, schema, policy,
and security rules.

**Build. Validate. Deploy. Secure.**

---

## Contents

| Area | What's inside |
|------|---------------|
| **Applications** | `apps/` reference service · `stacks/` Compose stacks (web-app, observability, Garage S3 object storage) |
| **Kubernetes** | `kubernetes/` base manifests, Kustomize overlays, Helm chart, platform add-ons (cert-manager, Gateway API, Velero, Argo CD), Kyverno policies, HPA, backup CronJobs |
| **IaC** | `iac/` Terraform modules + envs, Ansible roles/playbooks, Packer templates |
| **Linux / Windows** | `linux/` sysctl, sshd, systemd sandboxing, fail2ban, auditd, auto-updates · `windows/` PowerShell, GPO, firewall, scheduled tasks |
| **Networking** | `networking/` DNS, firewall, TLS, WireGuard VPN |
| **Data** | `databases/` PostgreSQL, MariaDB, MongoDB, Redis, PgBouncer, search, time-series, vector · `messaging/` RabbitMQ, NATS, Kafka · `storage/` backup + snapshots |
| **Observability** | `observability/` Prometheus, Alertmanager, Grafana, Loki, Alloy, OTel, SLOs, runbooks |
| **Security** | `security/` K8s policies, scanning, secrets patterns · `identity/` OIDC, RBAC, secrets · `governance/` compliance |
| **Web / Edge** | `web-servers/` nginx, caddy, apache, traefik, envoy, haproxy, iis, lighttpd, openresty · `edge/` mdm, waf · `frontend/` cdn, static · `api/` OpenAPI + rate limits |
| **Platform** | `virtualization/` Proxmox, cloud-init · `ai-ml/` GPU, serving · `email/` postfix, transactional · `registries/` harbor, zot · `automation/` · `config-formats/` schemas |
| **Tooling** | `scripts/` PIB validation framework · `tests/` unit→e2e→performance · `inventory/` tech inventory · `reports/` verification evidence · `docs/` architecture, ADRs, standards |

## Quick start

```bash
# 1. Clone
git clone https://github.com/phoenixdev100/InfraStack.git && cd InfraStack

# 2. Install validator tools (checksum-verified)
python scripts/setup/install_tools.py --all

# 3. Python deps
python -m venv .venv
.venv/Scripts/activate          # Windows
# source .venv/bin/activate     # Linux/macOS
pip install -r requirements/dev.txt

# 4. Validate the repository
python scripts/pib.py run lint validate security docs unit

# 5. Run the local platform
docker compose -f stacks/web-app-stack/compose.yaml up -d
docker compose -f stacks/observability-stack/compose.yaml up -d
```

## How validation works

`tests/matrix.yaml` maps every validator to the files it checks.
`python scripts/pib.py run <stage>` executes them; results are written to
`reports/generated/` (machine output) and summarized honestly:

| Result | Meaning |
|--------|---------|
| **PASS** | check ran and passed |
| **FAIL** | check ran and found issues |
| **NOT RUN** | required tool unavailable — never silently skipped |
| **NO TARGETS** | no files matched the check's patterns |

Stages: `lint` · `validate` · `security` · `docs` · `unit` · `integration` · `e2e` · `performance`

## Security posture

- No real secrets — placeholders (`CHANGE_ME`, `${VAR}`) only; `.env` files gitignored
- Images pinned to explicit tags; container hardening (non-root, `cap_drop`, `no-new-privileges`, healthchecks, limits)
- Kubernetes: NetworkPolicies, Pod Security, ResourceQuota/LimitRange, admission policies, signed-image verification (Kyverno + cosign)
- Linux: systemd sandboxing (`systemd-analyze security` 9.6 → 1.1–1.9), sshd drop-ins, fail2ban, auditd, UFW
- CI: SHA-pinned actions, least-privilege permissions, gitleaks + trivy + checkov gates
- See `SECURITY.md` for vulnerability reporting

## Documentation

- `docs/` — architecture, ADRs, standards, decisions
- `reports/` — validation, security, readiness, verification evidence
- `reports/compatibility-matrix.md` — what's tested on which platform
- `reports/known-limitations.md` — honest list of what is *not* verified
- `reports/troubleshooting.md` — centralized troubleshooting index

## Contributing

See `CONTRIBUTING.md`. Configs must pass the validation matrix; new
technologies need a real config (not a README-only stub), an inventory
entry, and honest maturity labels.

## License

MIT — see `LICENSE`.
