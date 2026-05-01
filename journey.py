"""
journey.py - Journey building, scoring, and real-time ranking.
COMP1110 | Semester 2, 2025-2026 | Group G-01

Provides:
  PREFERENCE_KEYS          - valid preference names
  Journey                  - data class for a candidate route
  build_journeys(...)      - build Journey objects from DFS paths
  rank_journeys(...)       - rank by a single preference
  rank_journeys_multi(...) - rank by multiple weighted preferences

Real-time enhancement (when realtime=True):
  - MTR: live wait times via rt.data.gov.hk
  - Bus/Minibus: live wait times via KMB API + TDAS traffic multiplier
  - Ferry/Tram: fixed boarding buffers
  Falls back gracefully to static times if APIs are unavailable.
"""

from __future__ import annotations
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PREFERENCE_KEYS = ["cheapest", "fastest", "fewest"]

# ── Real-time API helpers (imported from check.py) ────────────────────────────
try:
    from check import (
        haversine,
        nearby_mtr, mtr_eta, eta_minutes,
        nearby_kmb, kmb_stop_eta,
        safe_post, TDAS_ROUTE,
    )
    _RT = True
except ImportError:
    _RT = False


# ── Journey data class ────────────────────────────────────────────────────────

class Journey:
    """Represents a complete candidate route from origin to destination."""

    def __init__(self, segments, network):
        self.segments = segments        # list[Segment]
        self.network  = network
        self.total_cost    = sum(s.cost     for s in segments)
        self.total_time    = sum(s.duration for s in segments)  # static baseline
        self.adjusted_time = self.total_time   # updated by _apply_realtime
        self.num_hops      = _count_hops(segments)

    # Expose adjusted_time as "fastest" metric
    @property
    def time_for_ranking(self):
        return self.adjusted_time

    def summary_dict(self):
        if not self.segments:
            return {}
        stops = [self.network.get_stop_name(self.segments[0].from_stop)]
        for seg in self.segments:
            stops.append(self.network.get_stop_name(seg.to_stop))
        return {
            "total_cost":    self.total_cost,
            "total_time":    self.total_time,
            "adjusted_time": self.adjusted_time,
            "num_hops":      self.num_hops,
            "stops":         stops,
            "modes":         [s.mode for s in self.segments],
            "segments":      self.segments,
        }


def _count_hops(segments) -> int:
    """
    Count effective hops for ranking and display.

    A continuous MTR chain counts as one hop, so consecutive MTR -> MTR
    segments do not increase the hop count.
    """
    if not segments:
        return 0

    hops = 1
    previous_mode = segments[0].mode

    for segment in segments[1:]:
        if not (previous_mode == "MTR" and segment.mode == "MTR"):
            hops += 1
        previous_mode = segment.mode

    return hops


# ── Real-time helpers ─────────────────────────────────────────────────────────

def _live_mtr_wait(stop_id: str, network) -> float:
    """Return soonest MTR departure in minutes (default 3 if unavailable)."""
    if not _RT:
        return 3.0
    s = network.stops.get(stop_id)
    if not s or not s.latitude:
        return 3.0
    nearby = nearby_mtr(s.latitude, s.longitude, radius=800)
    if not nearby:
        return 3.0
    station = nearby[0]
    data = mtr_eta(station["line"], station["code"])
    if not data or data.get("status") == 0:
        return 3.0
    code_data = data.get("data", {}).get(station["code"], {})
    waits = []
    for trains in code_data.values():
        if isinstance(trains, list):
            for t in trains[:1]:
                m = eta_minutes(t.get("time", ""))
                if m is not None and m >= 0:
                    waits.append(m)
    return float(min(waits)) if waits else 3.0


def _live_bus_wait(stop_id: str, network) -> float:
    """Return soonest KMB bus in minutes (default 5 if unavailable)."""
    if not _RT:
        return 5.0
    s = network.stops.get(stop_id)
    if not s or not s.latitude:
        return 5.0
    nearby = nearby_kmb(s.latitude, s.longitude, radius=400)
    if not nearby:
        return 5.0
    bus_stop = nearby[0]
    etas = kmb_stop_eta(bus_stop["stop"])
    waits = []
    for eta in etas:
        m = eta_minutes(eta.get("eta", ""))
        if m is not None and m >= 0:
            waits.append(m)
    return float(min(waits)) if waits else 5.0


def _traffic_multiplier(from_id: str, to_id: str, network) -> float:
    """
    Use TDAS live speed to scale bus/minibus travel duration.
    Baseline 30 km/h → multiplier 1.0.
    Heavy traffic → multiplier > 1 (takes longer).
    """
    if not _RT:
        return 1.0
    fs = network.stops.get(from_id)
    ts = network.stops.get(to_id)
    if not fs or not ts or not fs.latitude or not ts.latitude:
        return 1.0
    result = safe_post(TDAS_ROUTE, {
        "start":    {"lat": fs.latitude,  "long": fs.longitude},
        "end":      {"lat": ts.latitude,  "long": ts.longitude},
        "departIn": 0, "lang": "en", "type": "ST",
    })
    if not result:
        return 1.0
    try:
        speed = float(str(result.get("jSpeed", "30")).split()[0])
        # clamp multiplier to reasonable range
        return max(0.5, min(3.0, 30.0 / speed)) if speed > 0 else 1.0
    except Exception:
        return 1.0


# ── Core functions ────────────────────────────────────────────────────────────

def build_journeys(paths: list, network, realtime: bool = False) -> list:
    """
    Build Journey objects from DFS paths.

    Parameters
    ----------
    paths    : list of paths, each path is a list of Segment objects.
    network  : Network instance.
    realtime : if True, query live APIs to compute adjusted_time for each
               journey using live wait times and current traffic conditions.
    """
    journeys = []
    for path in paths:
        j = Journey(path, network)
        if realtime and _RT:
            adj = 0.0
            for seg in path:
                ride = seg.duration
                if seg.mode == "MTR":
                    wait = _live_mtr_wait(seg.from_stop, network)
                    adj += ride + wait
                elif seg.mode in ("Bus", "Minibus"):
                    wait = _live_bus_wait(seg.from_stop, network)
                    mult = _traffic_multiplier(seg.from_stop, seg.to_stop, network)
                    adj += (ride * mult) + wait
                elif seg.mode == "Ferry":
                    adj += ride + 5.0   # ~5 min boarding buffer
                elif seg.mode == "Tram":
                    adj += ride + 2.0   # frequent, short wait
                else:
                    adj += ride
            j.adjusted_time = round(adj, 1)
        journeys.append(j)
    return journeys


def rank_journeys(journeys: list, preference: str) -> list:
    """Sort journeys by a single preference (cheapest / fastest / fewest).

    Returns Journey objects sorted by the chosen preference.
    """
    if preference not in PREFERENCE_KEYS:
        valid = ", ".join(PREFERENCE_KEYS)
        raise ValueError(f"Unknown preference mode '{preference}'. Use one of: {valid}.")

    key_fn = {
        "cheapest": lambda j: j.total_cost,
        "fastest":  lambda j: j.adjusted_time,
        "fewest":   lambda j: j.num_hops,
    }[preference]
    return sorted(journeys, key=key_fn)


def rank_journeys_multi(journeys: list, preferences: list):
    """
    Rank journeys by multiple weighted preferences.

    Returns
    -------
    (ranked_journeys, scores, breakdowns)
      - ranked_journeys : sorted best-first, as Journey objects
      - scores          : composite score per journey (lower = better)
      - breakdowns      : per-journey dict with raw / normalised / weighted values
    """
    if not preferences:
        raise ValueError("At least one preference mode is required.")

    invalid = [p for p in preferences if p not in PREFERENCE_KEYS]
    if invalid:
        valid = ", ".join(PREFERENCE_KEYS)
        bad = ", ".join(invalid)
        raise ValueError(f"Unknown preference mode(s): {bad}. Use one of: {valid}.")

    if not journeys:
        return [], [], []

    raw = {
        "cheapest": [j.total_cost    for j in journeys],
        "fastest":  [j.adjusted_time for j in journeys],
        "fewest":   [j.num_hops      for j in journeys],
    }

    def _normalise(vals):
        mn, mx = min(vals), max(vals)
        if mx == mn:
            return [0.0] * len(vals)
        return [(v - mn) / (mx - mn) for v in vals]

    normed = {p: _normalise(raw[p]) for p in preferences}
    w = 1.0 / len(preferences)

    scores, bds = [], []
    for i, j in enumerate(journeys):
        score = sum(normed[p][i] * w for p in preferences)
        scores.append(score)
        bds.append({
            p: {
                "raw":        raw[p][i],
                "normalised": normed[p][i],
                "weighted":   normed[p][i] * w,
            }
            for p in preferences
        })

    paired = sorted(zip(scores, journeys, bds), key=lambda x: x[0])
    return ([x[1] for x in paired], 
            [x[0] for x in paired], 
            [x[2] for x in paired])
