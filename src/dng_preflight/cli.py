"""Command-line entrypoint for dng-preflight."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import click
import yaml

from dng_preflight import __version__
from dng_preflight.discovery.aggregator import collect
from dng_preflight.generators import generate_all
from dng_preflight.interview.engine import run as run_interview
from dng_preflight.interview.prompt import questionary_provider
from dng_preflight.models.config import DngConfig, build_config
from dng_preflight.models.snapshot import EnvironmentSnapshot
from dng_preflight.validation.hard_stops import validate_plan


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="dng-preflight")
def cli() -> None:
    """DNG Preflight — discovery, planning, and generation for Cisco DNG."""


@cli.command("inspect")
@click.option(
    "--hostname",
    required=True,
    help="Planned public hostname for the DNG (e.g. dng.example.com).",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["yaml", "json"], case_sensitive=False),
    default="yaml",
    show_default=True,
    help="Serialization format for the snapshot.",
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, writable=True, path_type=Path),
    default=None,
    help="Write the snapshot to FILE instead of stdout.",
)
def inspect_cmd(hostname: str, fmt: str, output_path: Path | None) -> None:
    """Run discovery probes and emit an EnvironmentSnapshot."""
    snapshot = asyncio.run(collect(hostname))
    payload = snapshot.model_dump(mode="json")
    if fmt.lower() == "yaml":
        text = yaml.safe_dump(payload, sort_keys=False, default_flow_style=False)
    else:
        text = json.dumps(payload, indent=2) + "\n"
    if output_path is not None:
        output_path.write_text(text)
        click.echo(f"snapshot written to {output_path}", err=True)
    else:
        sys.stdout.write(text)


def _collect_overrides(
    allow_public_admin: bool, allow_domain_joined: bool, skip_time_check: bool
) -> frozenset[str]:
    flags: set[str] = set()
    if allow_public_admin:
        flags.add("--allow-public-admin")
    if allow_domain_joined:
        flags.add("--allow-domain-joined")
    if skip_time_check:
        flags.add("--skip-time-check")
    return frozenset(flags)


def _report_violations_and_exit(config: DngConfig, overrides: frozenset[str]) -> None:
    violations = validate_plan(config, overrides=overrides)
    if not violations:
        return
    for v in violations:
        suffix = f" (override: {v.override_flag})" if v.override_flag else ""
        click.echo(f"HARD-STOP {v.rule}: {v.message}{suffix}", err=True)
    sys.exit(2)


@cli.command("plan")
@click.option(
    "--hostname",
    default=None,
    help="Planned public hostname (required unless --snapshot is supplied).",
)
@click.option(
    "--snapshot",
    "snapshot_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Load snapshot from FILE instead of running discovery.",
)
@click.option(
    "--save",
    "save_path",
    type=click.Path(dir_okay=False, writable=True, path_type=Path),
    default=None,
    help="Write the plan to PLAN.yaml.",
)
@click.option("--allow-public-admin", is_flag=True, help="Override the public-admin hard stop.")
@click.option("--allow-domain-joined", is_flag=True, help="Override the domain-joined hard stop.")
@click.option("--skip-time-check", is_flag=True, help="Override the NTP-offset hard stop.")
def plan_cmd(
    hostname: str | None,
    snapshot_path: Path | None,
    save_path: Path | None,
    allow_public_admin: bool,
    allow_domain_joined: bool,
    skip_time_check: bool,
) -> None:
    """Run the interview and produce a DngConfig plan."""
    if snapshot_path is not None:
        snapshot = EnvironmentSnapshot.model_validate(yaml.safe_load(snapshot_path.read_text()))
    elif hostname is not None:
        snapshot = asyncio.run(collect(hostname))
    else:
        raise click.UsageError("--hostname is required unless --snapshot is supplied")

    answers = run_interview(snapshot, questionary_provider)
    config = build_config(snapshot, answers)

    overrides = _collect_overrides(allow_public_admin, allow_domain_joined, skip_time_check)
    _report_violations_and_exit(config, overrides)

    payload = yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False)
    if save_path is not None:
        save_path.write_text(payload)
        click.echo(f"plan written to {save_path}", err=True)
    else:
        sys.stdout.write(payload)


@cli.command("validate")
@click.option(
    "--plan",
    "plan_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to a saved PLAN.yaml.",
)
@click.option("--allow-public-admin", is_flag=True, help="Override the public-admin hard stop.")
@click.option("--allow-domain-joined", is_flag=True, help="Override the domain-joined hard stop.")
@click.option("--skip-time-check", is_flag=True, help="Override the NTP-offset hard stop.")
def validate_cmd(
    plan_path: Path,
    allow_public_admin: bool,
    allow_domain_joined: bool,
    skip_time_check: bool,
) -> None:
    """Run hard-stop rules against a saved plan without generating anything."""
    config = DngConfig.model_validate(yaml.safe_load(plan_path.read_text()))
    overrides = _collect_overrides(allow_public_admin, allow_domain_joined, skip_time_check)
    _report_violations_and_exit(config, overrides)
    click.echo("OK: no hard-stop violations", err=True)


@cli.command("generate")
@click.option(
    "--from-file",
    "plan_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to a saved PLAN.yaml.",
)
@click.option(
    "--output-dir",
    "output_dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("./dng-build"),
    show_default=True,
    help="Directory to write generated artifacts into.",
)
@click.option("--allow-public-admin", is_flag=True, help="Override the public-admin hard stop.")
@click.option("--allow-domain-joined", is_flag=True, help="Override the domain-joined hard stop.")
@click.option("--skip-time-check", is_flag=True, help="Override the NTP-offset hard stop.")
def generate_cmd(
    plan_path: Path,
    output_dir: Path,
    allow_public_admin: bool,
    allow_domain_joined: bool,
    skip_time_check: bool,
) -> None:
    """Generate every deployable artifact from a saved plan."""
    config = DngConfig.model_validate(yaml.safe_load(plan_path.read_text()))
    overrides = _collect_overrides(allow_public_admin, allow_domain_joined, skip_time_check)
    _report_violations_and_exit(config, overrides)
    written = generate_all(config, output_dir)
    click.echo(f"wrote {len(written)} artifact(s) to {output_dir}:", err=True)
    for path in written:
        click.echo(f"  - {path.name}", err=True)


if __name__ == "__main__":  # pragma: no cover
    cli()
