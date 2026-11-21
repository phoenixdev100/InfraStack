# Security Policy

## Reporting a vulnerability

**Do not open a public issue for security problems.** Use GitHub's
[private vulnerability reporting](https://docs.github.com/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
("Security" tab → "Report a vulnerability") for this repository.

Include: affected path(s), impact, reproduction steps, and suggested remediation if known.
Target response times (adjust to your organisation's SLA when adopting):

| Severity | Acknowledge | Fix or mitigation |
|---|---|---|
| Critical | 1 business day | 7 days |
| High | 2 business days | 30 days |
| Medium/Low | 5 business days | next planned release |

## What counts as a vulnerability here

This repository ships **configuration templates and tooling**, so vulnerabilities include:

- An insecure default in a template (e.g. disabled TLS verification, world-readable secrets, privileged containers).
- A validation or policy check that reports PASS for an insecure configuration.
- A committed secret, credential, private key, or personal data.
- A supply-chain weakness (unpinned action/image/tool, missing checksum verification).

## Secrets policy

- Never commit real secrets. Only placeholders (`CHANGE_ME`, `YOUR_SECRET_HERE`) and
  documentation-reserved domains/IPs (`example.com`, `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`) are allowed.
- Real secrets are provisioned at deploy time from a secrets manager - see
  [security/secrets-management/README.md](identity/secrets/).
- Enforcement: Gitleaks (pre-commit + CI, including full history), the `example-secrets` policy check,
  and Kubernetes/Compose inline-secret policies (`scripts/pibkit/policies.py`).
- If a secret is committed: **rotate it first**, then purge history. Rotation is mandatory even after a purge,
  because clones and forks may retain it.

## Supported versions

Only the `main` branch receives security fixes. Pinned third-party versions are tracked in
[reports/technology-inventory.md](reports/technology-inventory.md) and updated by Renovate.
