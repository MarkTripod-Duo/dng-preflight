# Contributing to dng-preflight

## Setup

```bash
uv sync --dev
uv run pre-commit install
```

`uv` will create a `.venv/` and install all dependencies pinned by `uv.lock`. The pre-commit hook
runs ruff (lint + format) and `ty check src/` on every commit.

## Guardrails

Four commands gate every change, locally and in CI:

```bash
uv run ruff check
uv run ruff format --check
uv run ty check src/
uv run pytest
```

All four must exit 0 before opening a PR.

## Working agreement

See Section 14 of [MVP_BUILD_PLAN.md](MVP_BUILD_PLAN.md). Highlights:

- **Phases ship in order.** 0 → 1 → 2 → 3. Don't skip ahead. Each phase has acceptance criteria
  that must pass before the next phase opens.
- **No new top-level dependencies without flagging** in the PR description.
- **Every public function gets a docstring and a unit test before merge.**
- **No side effects at import time.** Probe and generator modules must be importable without
  network or subprocess calls.
- **When in doubt about DNG behavior**, fetch the relevant doc from Section 12 of the build plan
  rather than guessing.

## Type checker

The project uses `ty` (Astral) instead of `mypy`. `ty` is pre-1.0; the config schema and rule set
are evolving. If you hit a `ty` regression, pin a working version in `pyproject.toml` and open an
issue noting which version broke.

## License

By contributing you agree your contributions are licensed under the MIT License (see
[LICENSE](LICENSE)).
