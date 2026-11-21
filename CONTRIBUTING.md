# Contributing

Thank you for improving the blueprint. Quality, correctness and security matter more than file count.

## 1. Set up

```bash
make setup            # or: task setup
# Windows without make: see AGENTS.md "Windows" section
```

`make setup` creates `.venv`, installs pinned Python/Node tooling and downloads **checksum-verified**
validator binaries into `.tools/bin` (see `scripts/setup/tools.yaml` / `tools.lock.json`).

## 2. Add or change a technology

1. Put it under the right category using the standard layout (see [../standards/technology-layout.md](docs/standards/technology-layout.md)).
2. Every technology directory needs a `README.md` following [../standards/readme-template.md](docs/standards/readme-template.md),
   including **classification**, supported versions, security notes, validation and rollback.
3. Register it in [`inventory/technologies.yaml`](inventory/technologies.yaml) with its validators.
4. Wire a validator into [`tests/matrix.yaml`](tests/matrix.yaml). Prefer the official upstream validator
   (`nginx -t`, `promtool`, `terraform validate`, ...). If none exists, add a schema or policy test.
5. Add tests: positive **and** negative cases for policies; integration tests for runnable services.
6. Run `make lint validate test-security docs-check test-unit` and fix every failure.

## 3. Rules (enforced by CI)

- No real secrets, tokens, keys, certificates, internal hostnames or personal data. Placeholders only.
- Images, actions and tools are pinned (tag + digest via Renovate, commit SHA for actions, checksums for binaries).
- No empty placeholder files or `.gitkeep`; no duplicated configs - use overlays/templates/includes.
- Never weaken a security control to make a check pass. Exemptions must be explicit, scoped, and justified
  (`policy.blueprint.example.com/exempt` + `exempt-reason`, `x-policy-exempt`, `.trivyignore.yaml` with expiry).
- Never claim a test passed unless it ran. Missing tools are reported as **NOT RUN**.
- Never run load tests against systems you do not own; defaults target `localhost` only.

## 4. Commits and pull requests

- [Conventional Commits](https://www.conventionalcommits.org/) (`feat(nginx): ...`, `fix(k8s): ...`).
- Update [CHANGELOG.md](CHANGELOG.md) under `Unreleased`.
- Fill in the PR template, including which checks you ran locally and which were NOT RUN.
- Significant design choices need an ADR in [docs/decisions/](docs/adr/).

## 5. Releases

Tag `vX.Y.Z` on `main` after updating the changelog. The `release` workflow verifies, builds, signs (Sigstore
keyless), attests provenance and publishes a GitHub Release. It never deploys anything.
