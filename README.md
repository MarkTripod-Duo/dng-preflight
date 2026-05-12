# dng-preflight

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Interactive pre-installation and configuration tool for **Cisco Duo Network Gateway (DNG)**. The
tool auto-detects host environment characteristics, asks the user only the questions discovery
cannot answer, and generates a tailored deployment artifact set: a scripted-config YAML, an
OS-aware installer shell script, a Markdown runbook ordered to resolve SAML's circular dependency,
a DNS record set, and a firewall rules script scoped to the detected firewall.

> **Status:** alpha. The three-phase pipeline (discovery → interview → generation) is feature-complete
> against the MVP scope in [MVP_BUILD_PLAN.md](MVP_BUILD_PLAN.md). DNG schema fidelity is locked to
> the public documentation as of generator authoring; review every artifact before applying.

## How it works

```
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│   inspect    │ → │     plan     │ → │   generate   │
│ (read-only   │   │  (questions  │   │ (DngConfig → │
│  probes)     │   │   only what  │   │  artifacts)  │
│              │   │  discovery   │   │              │
│              │   │  can't       │   │              │
│              │   │  answer)     │   │              │
└──────────────┘   └──────────────┘   └──────────────┘
       │                  │                  │
       ▼                  ▼                  ▼
EnvironmentSnapshot  InterviewAnswers     DngConfig
```

Each phase is YAML-serializable, so any of `--snapshot FILE`, `--save PLAN.yaml`, and
`--from-file PLAN.yaml` let you pause and resume. The interview engine is also UI-agnostic:
`engine.run(snapshot, answers_provider)` accepts any callable for the answers source, so the
same decision tree powers both the CLI prompt and the test suite.

## Quickstart

```bash
git clone <repo-url> dng-preflight
cd dng-preflight
uv sync --dev
uv run pre-commit install
```

End-to-end against the included plan fixture:

```bash
uv run dng-preflight generate \
    --from-file tests/fixtures/plans/web_ssh_rdp_smb_okta.yaml \
    --output-dir ./dng-build
ls dng-build/
# RUNBOOK.md         dns-records.md      install.sh          scripted-config.yaml
# dns-records.json   firewall.sh
```

Fresh on a target host:

```bash
sudo uv run dng-preflight inspect --hostname dng.example.com --output snapshot.yaml
uv run dng-preflight plan --snapshot snapshot.yaml --save plan.yaml
uv run dng-preflight validate --plan plan.yaml
uv run dng-preflight generate --from-file plan.yaml --output-dir ./dng-build
```

## CLI

```
dng-preflight inspect    --hostname HOST [--format yaml|json] [--output FILE]
dng-preflight plan       [--hostname HOST] [--snapshot FILE] [--save PLAN.yaml]
                         [--allow-public-admin] [--allow-domain-joined] [--skip-time-check]
dng-preflight validate   --plan PLAN.yaml
                         [--allow-public-admin] [--allow-domain-joined] [--skip-time-check]
dng-preflight generate   --from-file PLAN.yaml [--output-dir ./dng-build]
                         [--allow-public-admin] [--allow-domain-joined] [--skip-time-check]
```

`plan` runs `inspect` first unless `--snapshot` is supplied. `generate` re-runs the hard-stop
rules from build-plan §9 before writing any artifact; pass the matching `--allow-*` /
`--skip-*` flag to bypass a specific overridable rule. Three rules — wildcard-cert required for
RDP/SMB, DNG version floor, LB requires trusted_proxies, hostname must resolve — are
non-overridable and force a re-plan.

## What gets generated

| File | Source | Notes |
|------|--------|-------|
| `scripted-config.yaml`  | [generators/scripted_config.py](src/dng_preflight/generators/scripted_config.py) | DNG 3.3.0+ schema; cert/key bodies are `<<paste contents of …>>` placeholders since DNG embeds PEM inline |
| `install.sh`            | [generators/installer.py](src/dng_preflight/generators/installer.py) | `set -euo pipefail`; apt or dnf based on `/etc/os-release`; refuses to run if hostname doesn't resolve; passes `shellcheck --severity=warning` |
| `RUNBOOK.md`            | [generators/runbook.py](src/dng_preflight/generators/runbook.py) | Step-ordered to break the SAML circular dependency: bring DNG up with placeholder primary_auth → export SP metadata → configure IdP → import IdP metadata → restart → first-login password reset |
| `dns-records.md` + `.json` | [generators/dns_records.py](src/dng_preflight/generators/dns_records.py) | Includes `_acme-challenge` TXT records when TLS strategy is Let's Encrypt DNS-01; covers wildcard, subdomain delegation, seed-app A records |
| `firewall.sh`           | [generators/firewall_rules.py](src/dng_preflight/generators/firewall_rules.py) | `ufw` or `firewalld` depending on detected host firewall; stub-with-guidance otherwise |

## Scope (MVP)

In scope:

- Linux hosts only: Ubuntu 22.04 / 24.04, Debian 12, RHEL/Rocky/Alma 9
- Both DNG variants: web + SSH, and web + SSH + RDP/SMB
- IdPs: Duo SSO, Okta, Microsoft Entra ID, AD FS, generic SAML 2.0
- TLS strategies: existing cert bundle, Let's Encrypt DNS-01, internal CA
- Firewalls: `ufw` and `firewalld`
- DNG version: ≥ 3.3.0 (required for the April 15, 2026 CA-bundle cutoff)
- Single-host deployments

Out of scope (post-MVP): Textual TUI, post-install verification via DNG REST API, Windows/macOS
hosts, Terraform/CloudFormation generation, ACME HTTP-01, nftables-raw or cloud-SG emit, HA /
multi-node, OneLogin. See [MVP_BUILD_PLAN.md](MVP_BUILD_PLAN.md) §4 for the full list.

## Development

```bash
uv run ruff check           # lint
uv run ruff format --check  # format check
uv run ty check src/        # type-check
uv run pytest               # tests (223 currently)
uv run pre-commit run --all-files
```

The `install.sh` shellcheck test skips when `shellcheck` is not on `PATH`. Install it locally
(`brew install shellcheck` / `apt install shellcheck`) to exercise it.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the working agreement and phased-build rules.

## License

MIT — see [LICENSE](LICENSE).
