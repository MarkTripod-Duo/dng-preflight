"""Read-only host probes that populate an `EnvironmentSnapshot`.

All probe modules expose a single async entrypoint and must be importable
without side effects — no subprocess, network, or filesystem reads at import.
"""
