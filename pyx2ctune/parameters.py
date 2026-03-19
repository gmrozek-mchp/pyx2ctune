"""Parameter database for motorBench-generated MCAF projects.

Reads parameters.json and provides bidirectional Q-format conversion
between fixed-point counts (as used in firmware) and engineering units.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ParameterInfo:
    """Metadata for a single MCAF parameter."""

    key: str
    define_name: str
    description: str | None
    intended_value: float
    q: int | None
    scale: float | None
    units: str | None

    @property
    def has_scaling(self) -> bool:
        return self.q is not None and self.scale is not None


class ParameterDB:
    """Database of MCAF parameters loaded from motorBench parameters.json.

    Provides conversion between fixed-point counts and engineering units
    using the Q-format and scale factor defined for each parameter.

    Conversion formulas:
        counts_to_engineering: value = (counts / 2^q) * scale
        engineering_to_counts: counts = round(value / scale * 2^q)
    """

    def __init__(self, json_path: str | Path):
        path = Path(json_path)
        with open(path) as f:
            data = json.load(f)

        self.metadata: dict = data.get("metadata", {})
        self._by_key: dict[str, ParameterInfo] = {}
        self._by_define: dict[str, ParameterInfo] = {}

        for entry in data.get("parameters", []):
            info = ParameterInfo(
                key=entry["key"],
                define_name=entry["define_name"],
                description=entry.get("description"),
                intended_value=entry.get("intended_value", 0),
                q=entry.get("q"),
                scale=entry.get("scale"),
                units=entry.get("units"),
            )
            self._by_key[info.key] = info
            self._by_define[info.define_name] = info

    def get_info(self, key: str) -> ParameterInfo:
        """Look up parameter metadata by key (e.g. 'foc.kip') or define name (e.g. 'KIP')."""
        if key in self._by_key:
            return self._by_key[key]
        if key in self._by_define:
            return self._by_define[key]
        raise KeyError(f"Unknown parameter: {key!r}")

    def counts_to_engineering(self, key: str, counts: int) -> float:
        """Convert fixed-point counts to engineering units.

        Args:
            key: Parameter key (e.g. 'foc.kip') or define name (e.g. 'KIP').
            counts: Raw fixed-point integer value from firmware.

        Returns:
            Value in engineering units (e.g. V/A for current loop Kp).
        """
        info = self.get_info(key)
        if not info.has_scaling:
            return float(counts)
        return (counts / (1 << info.q)) * info.scale

    def engineering_to_counts(self, key: str, value: float) -> int:
        """Convert engineering units to fixed-point counts.

        Args:
            key: Parameter key or define name.
            value: Value in engineering units.

        Returns:
            Fixed-point integer counts suitable for writing to firmware.

        Raises:
            ValueError: If the resulting count exceeds int16 range.
        """
        info = self.get_info(key)
        if not info.has_scaling:
            return round(value)
        counts = round(value / info.scale * (1 << info.q))
        if not (-32768 <= counts <= 32767):
            raise ValueError(
                f"Value {value} {info.units or ''} for {key!r} produces counts={counts}, "
                f"which overflows int16 range at Q{info.q}. "
                f"Consider adjusting the shift count."
            )
        return counts

    def list_keys(self) -> list[str]:
        """Return all parameter keys."""
        return list(self._by_key.keys())

    def list_by_prefix(self, prefix: str) -> list[ParameterInfo]:
        """Return all parameters whose key starts with a given prefix."""
        return [info for key, info in self._by_key.items() if key.startswith(prefix)]

    def __repr__(self) -> str:
        version = self.metadata.get("version", "unknown")
        return f"ParameterDB(version={version!r}, parameters={len(self._by_key)})"
