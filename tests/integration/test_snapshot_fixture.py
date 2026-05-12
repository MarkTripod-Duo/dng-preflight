"""Integration: load the committed Ubuntu fixture and round-trip it through YAML."""

from __future__ import annotations

from pathlib import Path

import yaml

from dng_preflight.models.snapshot import (
    DockerInfo,
    EnvironmentSnapshot,
    FirewallKind,
)

_FIXTURE = Path(__file__).parent.parent / "fixtures" / "snapshots" / "ubuntu-2404-clean.yaml"


def test_fixture_parses_into_snapshot():
    data = yaml.safe_load(_FIXTURE.read_text())
    snap = EnvironmentSnapshot.model_validate(data)
    assert snap.system.distro == "ubuntu"
    assert snap.system.distro_version == "24.04"
    assert isinstance(snap.docker, DockerInfo)
    assert snap.docker.engine_version.startswith("27.")
    assert snap.firewall.kind == FirewallKind.UFW


def test_fixture_yaml_roundtrip_is_lossless():
    data = yaml.safe_load(_FIXTURE.read_text())
    snap = EnvironmentSnapshot.model_validate(data)
    redumped = yaml.safe_dump(snap.model_dump(mode="json"), sort_keys=False)
    rehydrated = EnvironmentSnapshot.model_validate(yaml.safe_load(redumped))
    assert rehydrated == snap
