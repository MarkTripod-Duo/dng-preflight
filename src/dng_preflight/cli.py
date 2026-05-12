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


if __name__ == "__main__":  # pragma: no cover
    cli()
