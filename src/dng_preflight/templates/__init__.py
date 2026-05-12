"""Jinja2 environment shared by every generator.

One environment, one shipped set of templates, one place to register filters
and globals. Generators import `env()` and call `env().get_template(name)`.

Filters
-------
- `pem_block`   — render a multi-line PEM string as a YAML `|` literal body
                  with consistent indentation
- `yaml_str`    — quote a value for safe YAML scalar emission
- `or_default`  — `(value, fallback)` — returns fallback if value is falsy
"""

from __future__ import annotations

from collections.abc import Iterable

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape

_PACKAGE = "dng_preflight"
_TEMPLATE_DIR = "templates"


def _pem_block(content: str, *, indent: int = 4) -> str:
    """Indent each line of `content` by `indent` spaces.

    Used for the `cert: |` and `key: |` inline-PEM blocks in scripted-config.
    The leading `|` is supplied by the template; this filter only handles the
    body.
    """
    pad = " " * indent
    return "\n".join(pad + line if line else pad for line in content.splitlines())


def _yaml_str(value: object) -> str:
    """Single-quote a value for YAML, escaping embedded single quotes.

    For predictable output across generators; we don't rely on PyYAML's
    serializer because we want byte-stable templates.
    """
    s = "" if value is None else str(value)
    return "'" + s.replace("'", "''") + "'"


def _or_default(value: object, fallback: object) -> object:
    return value if value else fallback


def _join_lines(items: Iterable[str]) -> str:
    return "\n".join(items)


def env() -> Environment:
    """Build the project Jinja2 environment.

    StrictUndefined surfaces missing-variable typos as template errors rather
    than silently emitting empty strings.
    """
    e = Environment(
        loader=PackageLoader(_PACKAGE, _TEMPLATE_DIR),
        autoescape=select_autoescape(default_for_string=False, default=False),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    e.filters["pem_block"] = _pem_block
    e.filters["yaml_str"] = _yaml_str
    e.filters["or_default"] = _or_default
    e.filters["join_lines"] = _join_lines
    return e


__all__ = ["env"]
