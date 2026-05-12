"""Render `install.sh` from a `DngConfig`.

The script is idempotent, uses `set -euo pipefail`, detects the distro to
pick `apt` vs `dnf`, and refuses to proceed if the public hostname doesn't
resolve. Output passes `shellcheck` with zero warnings on default settings.
"""

from __future__ import annotations

from dng_preflight.models.config import DngConfig
from dng_preflight.templates import env


def generate(config: DngConfig) -> str:
    """Render the installer shell script and return it as a string."""
    template = env().get_template("installer.sh.j2")
    return template.render(config=config)
