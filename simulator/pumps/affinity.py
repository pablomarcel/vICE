from __future__ import annotations

"""Centrifugal-pump affinity-law helpers."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AffinityScale:
    """Scale factor between a reference pump speed and a target pump speed."""

    reference_speed_rpm: float
    target_speed_rpm: float

    @property
    def ratio(self) -> float:
        if self.reference_speed_rpm <= 0.0:
            raise ValueError("reference_speed_rpm must be positive")
        return float(self.target_speed_rpm) / float(self.reference_speed_rpm)

    def flow_to_reference(self, flow_at_target: float) -> float:
        r = self.ratio
        if r <= 0.0:
            raise ValueError("target_speed_rpm must be positive")
        return float(flow_at_target) / r

    def flow_from_reference(self, flow_at_reference: float) -> float:
        return float(flow_at_reference) * self.ratio

    def head_from_reference(self, head_at_reference: float) -> float:
        r = self.ratio
        return float(head_at_reference) * r * r

    def power_from_reference(self, power_at_reference: float) -> float:
        r = self.ratio
        return float(power_at_reference) * r * r * r
