# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning: [SemVer](https://semver.org/).

## [Unreleased]

## [1.0.0] - 2026-11-21

### Added

- v1.0.0 release: full repository audit, portability classification, and
  production-readiness reporting (see `reports/`).
- Actually-executed verification: Docker Compose stacks, kind Kubernetes
  deployment, Helm install/upgrade/rollback, Ansible localhost execution,
  restic backup/restore, k6 load test.
- Kubernetes deployment verified on kind: dev/staging/prod Kustomize overlays,
  PodSecurity restricted enforcement, NetworkPolicy verification.
- Ansible toolchain: ansible-lint production profile pass, playbook
  idempotency verified.
- PowerShell validation via PSScriptAnalyzer.
- Portability audit branch: configuration classification, customization and
  compatibility matrices.

### Fixed

- Compose memory units (`Mi`/`Gi` -> `M`/`G`), postgres/redis entrypoint
  capabilities, node-exporter mounts, OTel Loki exporter, Prometheus
  remote-write receiver, Alloy storage/discovery config.
- Ansible `win_audit_policy` -> `win_audit_rule`, `ansible.cfg` callback,
  `.ansible-lint` schema.

### Known limitations

- Tempo ingester ring: memberlist gossip fails in WSL2/Docker (environment
  limitation, documented in `reports/known-limitations.md`).
- Terraform apply, Windows/Docker Ansible roles, remote restic: blocked by
  missing infrastructure/credentials (classified BLOCKED, not PASS).

## [0.1.0] - 2026-11-20

### Added

- Initial repository architecture, governance files and engineering standards.
- Python validation framework (`scripts/pib.py`) driven by `tests/matrix.yaml`, with NOT RUN reporting for missing tools.
- Checksum-verified, pinned validator toolchain (`scripts/setup/tools.yaml`, `tools.lock.json`).
- Security policies for Kubernetes, Docker Compose, example secrets, image pinning and GitHub Actions.
- GitHub Actions CI/CD with SHA-pinned actions, least-privilege permissions, SBOM, signing and provenance.
- Reference application, integrated reference stacks, and technology configurations across all categories
  (see `reports/technology-inventory.md`).
