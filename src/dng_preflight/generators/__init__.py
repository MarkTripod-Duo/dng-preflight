"""Generators turn a `DngConfig` into deployable artifacts.

`generate_all(config, output_dir)` is the single entry-point used by the CLI
and the E2E test. Individual generators are pure functions
`generate(config) -> str` so callers can render one artifact without writing
to disk.
"""

from __future__ import annotations

from pathlib import Path

from dng_preflight.generators import (
    dns_records,
    firewall_rules,
    installer,
    runbook,
    scripted_config,
)
from dng_preflight.models.config import DngConfig

ARTIFACT_NAMES: tuple[str, ...] = (
    "scripted-config.yaml",
    "install.sh",
    "RUNBOOK.md",
    "dns-records.md",
    "dns-records.json",
    "firewall.sh",
)


def generate_all(config: DngConfig, output_dir: Path) -> list[Path]:
    """Render every artifact and write it to `output_dir`.

    Creates the directory if it doesn't exist. Returns the list of written
    paths in the canonical order (matches `ARTIFACT_NAMES`). Shell scripts
    are chmodded 0o755 so the operator can run them directly.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    payloads = (
        ("scripted-config.yaml", scripted_config.generate(config)),
        ("install.sh", installer.generate(config)),
        ("RUNBOOK.md", runbook.generate(config)),
        ("dns-records.md", dns_records.generate_md(config)),
        ("dns-records.json", dns_records.generate_json(config)),
        ("firewall.sh", firewall_rules.generate(config)),
    )
    written: list[Path] = []
    for name, content in payloads:
        path = output_dir / name
        path.write_text(content)
        if path.suffix == ".sh":
            path.chmod(0o755)
        written.append(path)
    return written


__all__ = [
    "ARTIFACT_NAMES",
    "dns_records",
    "firewall_rules",
    "generate_all",
    "installer",
    "runbook",
    "scripted_config",
]
