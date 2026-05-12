# dng-preflight

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Interactive pre-installation and configuration tool for **Cisco Duo Network Gateway (DNG)**. The
tool auto-detects host environment characteristics, asks the user only the questions discovery
cannot answer, and generates a tailored deployment artifact set: a scripted-config YAML, an
OS-aware installer shell script, a Markdown runbook ordered to resolve SAML's circular dependency,
a DNS record set, and a firewall rules script scoped to the detected firewall.

> **Status:** pre-alpha. Phase 0 scaffolding only. See [MVP_BUILD_PLAN.md](MVP_BUILD_PLAN.md) for
> the full scope and roadmap.

## Quickstart

```bash
git clone <repo-url> dng-preflight
cd dng-preflight
uv sync --dev
uv run pre-commit install
```

## CLI surface (planned)

```
dng-preflight inspect    [--hostname HOST] [--json | --yaml] [--output FILE]
dng-preflight plan       [--hostname HOST] [--snapshot FILE] [--save PLAN.yaml]
dng-preflight generate   --from-file PLAN.yaml [--output-dir DIR]
dng-preflight validate   --plan PLAN.yaml
```

None of these are wired up yet — Phase 0 only ships the project skeleton, lint/type/test
toolchain, and CI.

## Development

```bash
uv run ruff check          # lint
uv run ruff format --check # format check
uv run ty check src/       # type-check
uv run pytest              # tests
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the working agreement and phased-build rules.

## License

MIT — see [LICENSE](LICENSE).
