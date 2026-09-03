"""Splits aus Strava-Streams (distance, time, watts)."""
from __future__ import annotations

from garmin_sync.splits import Split


def compute_splits_from_streams(streams: dict, split_distance_m: float = 5000.0) -> list[Split]:
    if "distance" not in streams or "time" not in streams:
        return []
    dist = streams["distance"]["data"]
    times = streams["time"]["data"]
    watts = streams.get("watts", {}).get("data") if streams.get("watts") else None
    n = min(len(dist), len(times))
    if n < 2:
        return []

    splits: list[Split] = []
    boundary = split_distance_m
    last_boundary_t = 0.0
    bucket: list[float] = []
    idx = 1

    for i in range(1, n):
        d_prev, d_cur = float(dist[i - 1]), float(dist[i])
        t_prev, t_cur = float(times[i - 1]), float(times[i])
        if watts is not None and i < len(watts) and watts[i] is not None:
            bucket.append(float(watts[i]))

        while d_cur >= boundary and d_prev < boundary:
            if d_cur == d_prev:
                t_at = t_cur
            else:
                frac = (boundary - d_prev) / (d_cur - d_prev)
                t_at = t_prev + frac * (t_cur - t_prev)
            duration = t_at - last_boundary_t
            avg_p = sum(bucket) / len(bucket) if bucket else None
            splits.append(Split(idx, duration, avg_p))
            idx += 1
            last_boundary_t = t_at
            bucket = []
            boundary += split_distance_m
            d_prev = boundary - 1e-9

    return splits
