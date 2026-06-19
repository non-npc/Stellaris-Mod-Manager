from __future__ import annotations

import re

import numpy as np


VERSION_PARTS = re.compile(r"\d+|\*")


def normalize_version(value: str | None) -> list[str]:
    if not value:
        return []
    return VERSION_PARTS.findall(value.lower().lstrip("v"))


def compatibility_label(required: str | None, current: str | None) -> tuple[str, bool | None]:
    required_parts = normalize_version(required)
    current_parts = normalize_version(current)
    if not required_parts or not current_parts:
        return "Unknown", None

    for index, requirement in enumerate(required_parts):
        if requirement == "*":
            return "Compatible", True
        if index >= len(current_parts):
            return "Unknown", None
        if requirement != current_parts[index]:
            return "Incompatible", False
    return "Compatible", True


def compatibility_counts(
    required_versions: list[str], current_version: str
) -> dict[str, int]:
    labels = np.asarray(
        [compatibility_label(required, current_version)[0] for required in required_versions],
        dtype="U12",
    )
    return {
        "compatible": int(np.count_nonzero(labels == "Compatible")),
        "incompatible": int(np.count_nonzero(labels == "Incompatible")),
        "unknown": int(np.count_nonzero(labels == "Unknown")),
    }
