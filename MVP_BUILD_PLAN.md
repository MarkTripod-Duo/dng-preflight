# DNG Preflight — MVP Build Plan

> Working brief for Claude Code. This document is the source of truth for the MVP scope and architectural decisions. Open questions are explicitly listed at the bottom; everything else is locked.

---

## 1. Project overview

**Working name:** `dng-preflight`

Interactive pre-installation and configuration tool for **Cisco Duo Network Gateway (DNG)**. The tool auto-detects host environment characteristics, asks the user only the questions discovery cannot answer, and generates a tailored deployment artifact set: a scripted-config YAML, an OS-aware installer shell script, a Markdown runbook ordered to resolve SAML's circular dependency, a DNS record set, and a firewall rules script scoped to the detected firewall.

**Target users:** security engineers deploying DNG into a DMZ for the first time, or replicating an existing deployment across environments.

**Target release:** open source, MIT or Apache-2.0 (decide before v1.0).

---

## 2. Why this exists

DNG documentation is accurate but scattered, and real-world failures cluster at integration boundaries — DNS resolution, SAML metadata exchange, TLS chain construction, host placement (DMZ vs. internal vs. domain-joined), and timing/order-of-operations between IdP and DNG bring-up. A discovery-driven preflight tool replaces a static checklist and catches misconfigurations before `docker compose up`, when they are cheap to fix.

---

## 3. Tech stack (locked decisions)

These are not open questions. Claude Code should not propose alternatives unless a concrete blocker emerges.

- **Python:** 3.12+, strict typing throughout
- **Packaging:** `uv`
- **Data models:** `pydantic` v2, strict mode, no implicit coercion
- **Async HTTP:** `httpx` (async client)
- **DNS:** `dnspython` (async resolver)
- **Process/port enumeration:** `psutil`
- **X.509 inspection:** `cryptography`
- **Templating:** `jinja2`
- **Interactive prompts (MVP):** `questionary`. Textual TUI is post-MVP.
- **Testing:** `pytest`, `pytest-asyncio`, `syrupy` for snapshot tests
- **Lint/format:** `ruff` (line length 100)
- **Typing:** `ty` (Astral). Pre-1.0 — config schema and rule set are still evolving; pin a working version if a regression lands.
- **CI:** GitHub Actions — lint, type-check, test on every push

---

## 4. Scope: MVP

**In scope:**
- Linux hosts only: Ubuntu 22.04 / 24.04, Debian 12, RHEL/Rocky/Alma 9
- Both DNG deployment variants: web + SSH; web + SSH + RDP/SMB (different compose YAML, extra DNS container for RDP/SMB)
- IdP choices: Duo SSO, Okta, Microsoft Entra ID, AD FS, Generic SAML
- TLS strategies: existing cert bundle, Let's Encrypt with DNS-01, internal CA
- Firewall emit: firewalld and ufw
- DNG version pin: **≥ 3.3.0** (required for the April 15, 2026 legacy-CA-bundle cutoff)
- Single-host deployments

**Explicitly out of scope for MVP:**
- Textual TUI (use `questionary` for now)
- Post-install verification via DNG REST API
- Logging integrations (Chronicle, Splunk, syslog) — emit prose guidance only, no config
- Windows or macOS host installers
- AWS CloudFormation or Terraform generation
- Backup / restore workflows
- HA / paired or multi-node deployments
- OneLogin as IdP (post-MVP)
- ACME HTTP-01 (DNS-01 only in MVP)
- nftables raw, iptables raw, cloud security group emit

---

## 5. Architecture: three-phase pipeline

```
discovery (read-only)  →  interview (only what discovery couldn't answer)  →  generation (artifact set)
       │                          │                                                    │
       ▼                          ▼                                                    ▼
EnvironmentSnapshot       InterviewAnswers                                          DngConfig
                                                                                  (snapshot + answers)
```

Each phase consumes a single pydantic model and produces a single pydantic model. All three are YAML-serializable to support `--save-state`, `--from-file`, and snapshot-based test fixtures.

---

## 6. Module layout

```
dng-preflight/
├── pyproject.toml
├── README.md
├── LICENSE
├── CONTRIBUTING.md
├── MVP_BUILD_PLAN.md            # this file
├── src/
│   └── dng_preflight/
│       ├── __init__.py
│       ├── cli.py                # entrypoint, typer or click
│       ├── models/
│       │   ├── snapshot.py       # EnvironmentSnapshot + sub-models
│       │   ├── answers.py        # InterviewAnswers
│       │   └── config.py         # DngConfig (derived)
│       ├── discovery/
│       │   ├── aggregator.py     # asyncio.gather across probes
│       │   ├── system.py
│       │   ├── docker.py
│       │   ├── network.py
│       │   ├── dns.py
│       │   ├── tls.py
│       │   ├── time_sync.py
│       │   ├── firewall.py
│       │   └── duo_reachability.py
│       ├── interview/
│       │   ├── engine.py         # decision tree, no UI
│       │   ├── questions.py      # Question models with applies_when()
│       │   └── prompt.py         # questionary adapter
│       ├── generators/
│       │   ├── scripted_config.py
│       │   ├── installer.py
│       │   ├── runbook.py
│       │   ├── dns_records.py
│       │   └── firewall_rules.py
│       ├── validation/
│       │   └── hard_stops.py     # enforced at generate-time
│       └── templates/
│           ├── scripted-config.yaml.j2
│           ├── installer.sh.j2
│           ├── runbook.md.j2
│           ├── dns-records.md.j2
│           └── firewall-{ufw,firewalld}.sh.j2
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│       ├── snapshots/            # captured EnvironmentSnapshot YAMLs
│       └── plans/                # full plan YAMLs for E2E tests
└── docs/
```

---

## 7. Core data models

Define these first; everything else depends on them.

**`EnvironmentSnapshot`** — output of discovery. Sub-models: `SystemInfo`, `DockerInfo`, `NetworkInfo`, `DnsResolution`, `TlsObservation`, `TimeSyncState`, `FirewallState`, `DuoReachability`. Every field documented. Use `NotDetected` sentinel (a frozen pydantic model) rather than `None` so missing-tool cases are explicit.

**`InterviewAnswers`** — output of interview. Fields:
- `deployment_scope: Literal["web_ssh", "web_ssh_rdp_smb"]`
- `idp: Literal["duo_sso", "okta", "entra_id", "adfs", "generic_saml"]`
- `public_hostname: str`
- `tls_strategy: TlsStrategy` (discriminated union: `ExistingBundle | LetsEncryptDns01 | InternalCa`)
- `wildcard_cert: bool` (auto-required if scope includes RDP/SMB)
- `load_balancer: LoadBalancerConfig | None` (includes `trusted_proxies: list[IPv4Network | IPv6Network]`)
- `internal_dns: Literal["split_horizon", "internal_only", "none"]`
- `seed_apps: SeedApps` (counts and stubs for web / ssh / rdp)

**`DngConfig`** — derived. Built from `(EnvironmentSnapshot, InterviewAnswers)` via a single `build_config()` function. This is the only input to generators; generators must not see snapshot or answers directly.

---

## 8. Phased build

### Phase 0 — Project scaffolding
- `uv init`, populate `pyproject.toml` with all locked deps
- Ruff + mypy configs (strict)
- Pre-commit hooks (ruff, mypy, end-of-file fixer)
- GitHub Actions workflow: lint + type-check + test
- README skeleton, CONTRIBUTING.md, LICENSE
- One trivial test to verify CI

**Acceptance:** `uv run pytest`, `uv run ruff check`, `uv run ty check src/` all clean on a fresh clone.

### Phase 1 — Discovery
Each probe is an async function returning a typed sub-model. `aggregator.collect()` runs all probes via `asyncio.gather(return_exceptions=False)` with a hard 30-second total budget and 10-second per-probe timeout.

Probes (MVP):
- `system` — OS, distro, version, kernel, arch, RAM, CPU count, SELinux/AppArmor mode, domain-join status (`realm list`, `/etc/krb5.conf` presence)
- `docker` — Engine version, Compose plugin version, daemon reachable, current user in `docker` group
- `network` — listening ports 80/443/8443 (via `psutil.net_connections`), interface IPs, default route, egress public IP via fallback chain (`api.ipify.org`, `ifconfig.me`, `icanhazip.com`)
- `dns` — for the planned hostname: A/AAAA from 1.1.1.1, 8.8.8.8, 9.9.9.9 (authoritative-style query), reverse PTR, `/etc/resolv.conf` nameservers
- `tls` — does 443 answer on the host? If so, dump cert chain via `cryptography`: CN, SAN list, NotBefore, NotAfter, issuer chain, key algorithm
- `time_sync` — chronyd or ntpd state, offset from `pool.ntp.org`, sync source
- `firewall` — detect active firewall: try `firewall-cmd --state`, then `ufw status`, then check `iptables -L` non-empty; emit `FirewallKind` enum
- `duo_reachability` — async HEAD requests to `api-*.duosecurity.com` (use the official endpoint list)

Constraints:
- All probes are read-only. No state mutation.
- Missing tools produce `NotDetected`, never raise.
- Snapshot must round-trip through YAML (write, read back, equality check) in a test.

CLI: `dng-preflight inspect --hostname dng.example.com [--json | --yaml] [--output FILE]`

**Acceptance:**
- Each probe has unit tests with mocked subprocess and network calls
- One integration fixture: a real `EnvironmentSnapshot` from a clean Ubuntu 24.04 + Docker host, committed to `tests/fixtures/snapshots/ubuntu-2404-clean.yaml`
- Round-trip serialization test passes
- `dng-preflight inspect` completes within 30 seconds on a healthy host

### Phase 2 — Interview engine
Stateless decision tree. Input: `EnvironmentSnapshot`. Output: `InterviewAnswers`.

Each question is a `Question` pydantic model with:
- `id: str`
- `prompt: str`
- `kind: Literal["select", "text", "confirm", "multi"]`
- `choices: list[Choice] | None`
- `default_from(snapshot, prior) -> Any | None`
- `applies_when(snapshot, prior) -> bool`
- `validate(answer, snapshot, prior) -> None` (raises `ValidationError`)

Question order (must be preserved):
1. Deployment scope → gates the YAML compose file choice
2. Primary IdP
3. Public hostname for DNG (default from `dns.collect` if an A record was found)
4. TLS strategy (with sub-prompts per strategy)
5. Wildcard cert (auto-required if scope includes RDP/SMB; question skipped, value forced)
6. Load balancer in front (and `trusted_proxies` CIDR list if yes)
7. Internal DNS topology
8. Seed apps (number and stubs for web / SSH relay / RDP relay)

The engine module must be runnable without the prompt UI — `engine.run(snapshot, answers_provider)` where `answers_provider` is an injectable callable. This is how Claude Code will test it.

CLI: `dng-preflight plan --hostname dng.example.com [--snapshot FILE] [--save PLAN.yaml]`

**Acceptance:**
- Decision tree covered by parameterized tests across all IdP × scope × TLS strategy combinations that matter
- Hard validation rules (Section 9) enforced
- Plan YAML round-trips through serialization

### Phase 3 — Generators
Each generator consumes `DngConfig` only and produces one artifact. No generator may call discovery or interview code.

MVP generators:
- `scripted_config.py` → `scripted-config.yaml` conforming to DNG 3.3.0+ schema
- `installer.py` → `install.sh`, idempotent, `set -euo pipefail`, OS-aware (detects distro and uses correct package manager)
- `runbook.py` → `RUNBOOK.md`, ordered to resolve the SAML circular dependency: (a) bring up DNG containers, (b) export SP metadata, (c) configure IdP with SP metadata, (d) import IdP metadata into DNG, (e) first-login password reset via shell access
- `dns_records.py` → `dns-records.md` (human-readable, with TTL recommendations) and `dns-records.json` (machine-readable); includes `_acme-challenge` TXT records if TLS strategy is Let's Encrypt DNS-01
- `firewall_rules.py` → `firewall.sh` with `ufw` or `firewall-cmd` commands scoped to the detected firewall

All templates live in `src/dng_preflight/templates/` as Jinja2 files. Filters and globals registered in a single `templates/__init__.py`.

CLI: `dng-preflight generate --from-file plan.yaml [--output-dir ./dng-build]`

**Acceptance:**
- Generated `scripted-config.yaml` re-parses with PyYAML and contains all required top-level keys for the chosen scope
- `install.sh` passes `shellcheck` with zero warnings on default settings
- Snapshot tests with `syrupy`: same `DngConfig` always produces byte-identical output
- E2E test: `inspect → plan-from-fixture → generate` produces the expected set of files in `--output-dir`

---

## 9. Hard validation rules (block, do not warn)

Enforced in `validation/hard_stops.py`, invoked before any generator runs. Each rule has an `--override-<rule>` escape hatch that surfaces a loud warning in the generated runbook.

1. **8443 must be private.** If the detected egress IP equals the bound IP for the planned DNG host and no firewall rule scopes 8443 to a private CIDR, refuse to generate. Override: `--allow-public-admin`.
2. **Not domain-joined.** Host must not be domain-joined. Detected via `realm list` or `/etc/krb5.conf` content with realm entries. Override: `--allow-domain-joined`.
3. **Wildcard required for RDP/SMB.** If scope includes RDP/SMB and TLS strategy is single-hostname (non-wildcard) — hard stop. No override; resolve by changing TLS strategy or scope.
4. **Time offset.** If chronyd/ntpd offset from `pool.ntp.org` is > 30 seconds — block. SAML signatures will fail otherwise. Override: `--skip-time-check`.
5. **DNG version pin.** Generated compose must reference DNG ≥ 3.3.0. Non-negotiable for MVP.
6. **Load balancer requires trusted_proxies.** If `load_balancer` is set, `trusted_proxies` list must be non-empty. No override.
7. **Public hostname must resolve.** If authoritative resolvers (1.1.1.1, 8.8.8.8) do not return an A or AAAA for `public_hostname`, the runbook must include DNS setup as **Step 0**, and `install.sh` must refuse to proceed until resolution succeeds. No override.

---

## 10. CLI surface

```
dng-preflight inspect    [--hostname HOST] [--json | --yaml] [--output FILE]
dng-preflight plan       [--hostname HOST] [--snapshot FILE] [--save PLAN.yaml]
dng-preflight generate   --from-file PLAN.yaml [--output-dir DIR]
dng-preflight validate   --plan PLAN.yaml                # run hard stops without generating
```

`plan` runs `inspect` first unless `--snapshot` is supplied. `generate` accepts `PLAN.yaml` from `plan --save`.

---

## 11. Testing strategy

- **Unit:** per probe, per question, per generator, per validation rule. Mock `subprocess`, `httpx`, `dns.asyncresolver`, and `socket` at module boundaries.
- **Integration:** fixtures in `tests/fixtures/snapshots/` representing realistic host states (clean Ubuntu, RHEL with SELinux enforcing, host with port 80 occupied, etc.). Drive interview engine against each fixture with canned answer providers.
- **Snapshot:** generator outputs via `syrupy`. Regenerate intentionally only.
- **E2E:** one full pipeline test per fixture, validating output file set and content shape.

**Coverage targets:** ≥85% line, ≥75% branch on `src/dng_preflight/` excluding `cli.py`.

---

## 12. Reference material

Consult these during build. They are authoritative.

- DNG product docs: https://duo.com/docs/dng
- DNG scripted configuration (YAML schema): https://duo.com/docs/dng-scripted-config
- DNG release notes (version history, CA bundle cutoff): https://duo.com/docs/dng-notes
- DNG Administration API (post-MVP reference): https://duo.com/docs/dng-api

Key facts to encode in templates and validation:
- DNG ≥ 3.3.0 required for continued operation after April 15, 2026
- RDP/SMB deployment uses a distinct compose YAML with an extra DNS container (added in DNG 1.6.0)
- DNG admin console on 8443 must not be internet-facing
- DNG host must not be on the internal network and must not be domain-joined
- A SAML 2.0 IdP is mandatory; Duo SSO can wrap on-prem AD as the underlying authentication source
- Universal Prompt is current; iframe Duo Prompt is end-of-life
- Initial first-login password reset requires shell access to the Docker host

---

## 13. Open questions to resolve before v1.0

- License: MIT or Apache-2.0
- GitHub org/repo name (separate from `swgoh-utils`)
- Should `inspect` ship as a public standalone subcommand, or only as an internal step of `plan`?
- Telemetry: opt-in or none at all? **Default position: none.**

---

## 14. Working agreement for Claude Code

- Build phases in order: 0 → 1 → 2 → 3. Do not skip ahead.
- At each phase boundary, ensure acceptance criteria pass before starting the next phase.
- Do not introduce new top-level dependencies without flagging in a PR description.
- Every public function gets a docstring and a unit test before merge.
- All probe and generator modules must be importable without side effects (no network or subprocess calls at import time).
- When in doubt about DNG behavior, fetch the relevant doc URL from Section 12 rather than guessing.
