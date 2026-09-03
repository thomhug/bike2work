"""Compute fixed-distance splits from a FIT file."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fitparse import FitFile


@dataclass
class Split:
    index: int
    duration_s: float
    avg_power_w: float | None


def compute_splits(fit_path: Path, split_distance_m: float = 5000.0) -> list[Split]:
    """Walk record messages, cut at every split_distance_m boundary.

    Linearly interpolates timestamp at the exact boundary distance.
    Power is averaged over records that fall inside each split.
    """
    fit = FitFile(str(fit_path))
    points: list[tuple[float, float, float | None]] = []  # (t_seconds, distance_m, power)
    t0: float | None = None
    for msg in fit.get_messages("record"):
        d = msg.get_value("distance")
        ts = msg.get_value("timestamp")
        if d is None or ts is None:
            continue
        t = ts.timestamp()
        if t0 is None:
            t0 = t
        p = msg.get_value("power")
        points.append((t - t0, float(d), float(p) if p is not None else None))

    if len(points) < 2:
        return []

    splits: list[Split] = []
    boundary = split_distance_m
    last_boundary_t = 0.0
    bucket_powers: list[float] = []
    split_idx = 1

    for i in range(1, len(points)):
        t_prev, d_prev, _ = points[i - 1]
        t_cur, d_cur, p_cur = points[i]
        if p_cur is not None:
            bucket_powers.append(p_cur)

        while d_cur >= boundary and d_prev < boundary:
            # interpolate time at boundary
            if d_cur == d_prev:
                t_at = t_cur
            else:
                frac = (boundary - d_prev) / (d_cur - d_prev)
                t_at = t_prev + frac * (t_cur - t_prev)
            duration = t_at - last_boundary_t
            avg_p = sum(bucket_powers) / len(bucket_powers) if bucket_powers else None
            splits.append(Split(split_idx, duration, avg_p))
            split_idx += 1
            last_boundary_t = t_at
            bucket_powers = []
            boundary += split_distance_m
            d_prev = boundary - 1e-9  # advance prev so loop exits if multi-split jump

    return splits
