# production-infrastructure-blueprint (InfraStack)

> **Naming:** **InfraStack** is the public-facing project name. **PIB**
> (Production Infrastructure Blueprint) remains the internal CLI/framework
> identity for v1.0.0 (`scripts/pib.py`, `pibkit`, `pib-*` resource names).
> This naming is intentional for backward compatibility.

Enterprise-grade production infrastructure, DevOps, SRE, security, and
configuration reference repository.

This repo is a **working reference implementation** - not just examples.
Every configuration is validated by a declarative test matrix that runs
lint, schema, policy, and security checks on every file.

## What's inside

| Area | Contents |
|------|----------|
| `apps/` | Reference application (dependency-free Python service) |
| `web-servers/` | nginx, caddy, apache, traefik, envoy, haproxy, iis, lighttpd, openresty |
| `databases/` | PostgreSQL, Redis, MongoDB, MariaDB, PgBouncer + group READMEs |
| `observability/` | Prometheus, Alertmanager, Grafana, Loki, Tempo, Alloy, OTel, SLOs, runbooks |
| `kubernetes/` | Hardened manifests, Kustomize overlays, Helm chart, admission policies |
| `iac/` | Terraform modules+envs, Ansible playbooks, Packer templates |
| `stacks/` | Docker Compose: web-app, observability, object-storage (Garage S3) |
| `security/` | Scanning configs, OPA policies, K8s admission examples |
| `identity/` | OIDC, RBAC, secrets management (ESO/SOPS/Vault) |
| `cicd/` | GitHub Actions patterns, release engineering, deploy strategies |
| `storage/` | restic backup/restore, snapshot policies |
| `messaging/` | RabbitMQ, NATS, Kafka configs |
| `networking/` | DNS (unbound), nftables/ufw, TLS baseline |
| `linux/` `windows/` | sysctl, sshd, systemd, PowerShell, GPO |
| `api/` | OpenAPI spec, rate-limit patterns |
| `virtualization/` `ai-ml/` `email/` `frontend/` `edge/` `governance/` `registries/` `automation/` `config-formats/` `docs/` | Full category coverage |
| `scripts/` | Validation framework (`pibkit`), checksum-verified tool installer |
| `tests/` | Unit, integration, e2e, performance, security tests |
| `inventory/` | Machine-readable technology inventory |
| `reports/` | Validation, test, security, performance results |

## Quick start

```bash
# Install validator tools (checksum-verified)
python scripts/setup/install_tools.py --all

# Install Python dev deps
python -m venv .venv && .venv/Scripts/pip install -r requirements/dev.txt   # Windows
# or: source .venv/bin/activate && pip install -r requirements/dev.txt       # Linux/macOS

# Run validation stages
python scripts/pib.py run lint validate security docs unit

# Run the local platform
cd stacks/web-app-stack && docker compose up -d
cd ../observability-stack && docker compose up -d
```

## Validation philosophy

- **PASS** = check ran and passed
- **FAIL** = check ran and found issues
- **NOT RUN** = required tool unavailable (never silently skipped)
- **NO TARGETS** = no files matched the check's patterns

See `tests/matrix.yaml` for the full validator→file mapping and
`docs/adr/0001-validation-framework-python.md` for the design decision.

## Security

- No real secrets anywhere - placeholders (`CHANGE_ME`, `${VAR}`) only
- All GitHub Actions SHA-pinned with version comments
- Images pinned to explicit tags (never `latest`)
- `gitleaks`, `trivy`, `checkov` run in the security stage
- See `SECURITY.md` for reporting vulnerabilities

## License

Apache-2.0 - see `LICENSE`.
