# ARGOS Mind modules
from __future__ import annotations

__all__ = ["NetGhost"]


def __getattr__(name: str):
    if name == "NetGhost":
        from src.skills.net_scanner.skill import NetGhost  # noqa: PLC0415
        return NetGhost
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
