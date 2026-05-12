"""DngConfig — the single input every generator consumes.

Built from an `EnvironmentSnapshot` and `InterviewAnswers` via `build_config()`.
Generators must NOT read the snapshot or answers directly; they receive only
this aggregate so derived fields stay computed in exactly one place.
"""

from pydantic import BaseModel, ConfigDict

from dng_preflight.models.answers import InterviewAnswers
from dng_preflight.models.snapshot import EnvironmentSnapshot

DNG_MIN_VERSION = "3.3.0"
"""April-15-2026 legacy-CA-bundle cutoff: any version older than this is dead
for the MVP. Pinned in the build plan §4."""


class DngConfig(BaseModel):
    """Aggregate config consumed by every generator.

    Holds the raw snapshot + answers plus a few derived fields that multiple
    generators need. New derived fields belong here, not duplicated across
    generators.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshot: EnvironmentSnapshot
    answers: InterviewAnswers
    requires_extra_dns_container: bool
    dng_version_minimum: str


def build_config(snapshot: EnvironmentSnapshot, answers: InterviewAnswers) -> DngConfig:
    """Derive a `DngConfig` from a discovery snapshot and interview answers.

    Today this just sets `requires_extra_dns_container` (true for the
    RDP/SMB compose variant, per DNG 1.6.0+) and pins the DNG version floor.
    """
    return DngConfig(
        snapshot=snapshot,
        answers=answers,
        requires_extra_dns_container=answers.deployment_scope == "web_ssh_rdp_smb",
        dng_version_minimum=DNG_MIN_VERSION,
    )
