#!/usr/bin/env python3
"""
Smart HK Public Transport Advisor
===================================
Uses 100% free, official APIs:
  - Nominatim (OpenStreetMap) — geocoding
  - KMB Open API             — live bus ETAs (data.etabus.gov.hk)
  - Citybus Open API         — live bus ETAs (rt.data.gov.hk)
  - GMB Open API             — green minibus ETAs (data.etagmb.gov.hk)
  - MTR Open API             — train schedules (rt.data.gov.hk)
  - TDAS API                 — live driving speed (tdas-api.hkemobility.gov.hk)

Install: pip install requests
Run:     python smart_hk_transit.py
"""

import requests
import math
import time
import sys
from datetime import datetime, timezone
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# API Base URLs
# ─────────────────────────────────────────────────────────────────────────────

NOMINATIM   = "https://nominatim.openstreetmap.org/search"
KMB_BASE    = "https://data.etabus.gov.hk/v1/transport/kmb"
CTB_BASE    = "https://rt.data.gov.hk/v2/transport/citybus"
GMB_BASE    = "https://data.etagmb.gov.hk"
MTR_ETA     = "https://rt.data.gov.hk/v1/transport/mtr/getSchedule.php"
TDAS_ROUTE  = "https://tdas-api.hkemobility.gov.hk/tdas/api/route"

HEADERS = {
    "User-Agent": "SmartHKTransitAdvisor/1.0 (educational use)",
    "Accept": "application/json",
}

# ─────────────────────────────────────────────────────────────────────────────
# MTR Station Map  (line → [(code, english_name, lat, lon)])
# ─────────────────────────────────────────────────────────────────────────────

MTR_LINES = {
    "AEL": [
        ("HOK", "Hong Kong",          22.2850, 114.1584),
        ("KOW", "Kowloon",            22.3047, 114.1617),
        ("TSY", "Tsing Yi",           22.3588, 114.1073),
        ("AIR", "Airport",            22.3159, 113.9365),
        ("AWE", "AsiaWorld-Expo",     22.3218, 113.9417),
    ],
    "TCL": [
        ("HOK", "Hong Kong",          22.2850, 114.1584),
        ("KOW", "Kowloon",            22.3047, 114.1617),
        ("OLY", "Olympic",            22.3178, 114.1601),
        ("NAC", "Nam Cheong",         22.3272, 114.1511),
        ("LAK", "Lai King",           22.3480, 114.1246),
        ("TSY", "Tsing Yi",           22.3588, 114.1073),
        ("SUN", "Sunny Bay",          22.3324, 114.0285),
        ("TUC", "Tung Chung",         22.2883, 113.9426),
    ],
    "TWL": [
        ("TSW", "Tsuen Wan",          22.3680, 114.1118),
        ("TWH", "Tai Wo Hau",         22.3706, 114.1253),
        ("KWH", "Kwai Hing",          22.3628, 114.1313),
        ("KWF", "Kwai Fong",          22.3567, 114.1313),
        ("LAK", "Lai King",           22.3480, 114.1246),
        ("MEF", "Mei Foo",            22.3384, 114.1381),
        ("LCK", "Lai Chi Kok",        22.3370, 114.1479),
        ("CSW", "Cheung Sha Wan",     22.3357, 114.1551),
        ("SSP", "Sham Shui Po",       22.3308, 114.1622),
        ("PRE", "Prince Edward",      22.3247, 114.1682),
        ("MOK", "Mong Kok",           22.3193, 114.1699),
        ("YMT", "Yau Ma Tei",         22.3128, 114.1700),
        ("JOR", "Jordan",             22.3047, 114.1718),
        ("TST", "Tsim Sha Tsui",      22.2975, 114.1722),
        ("ADM", "Admiralty",          22.2791, 114.1650),
        ("CEN", "Central",            22.2818, 114.1574),
    ],
    "ISL": [
        ("KET", "Kennedy Town",       22.2813, 114.1284),
        ("HKU", "HKU",               22.2839, 114.1357),
        ("SYP", "Sai Ying Pun",       22.2856, 114.1436),
        ("SHW", "Sheung Wan",         22.2866, 114.1513),
        ("CEN", "Central",            22.2818, 114.1574),
        ("ADM", "Admiralty",          22.2791, 114.1650),
        ("WAC", "Wan Chai",           22.2776, 114.1731),
        ("CAB", "Causeway Bay",       22.2805, 114.1836),
        ("TIH", "Tin Hau",            22.2819, 114.1921),
        ("FOH", "Fortress Hill",      22.2874, 114.1942),
        ("NOP", "North Point",        22.2905, 114.1996),
        ("QUB", "Quarry Bay",         22.2882, 114.2093),
        ("TAK", "Tai Koo",            22.2843, 114.2163),
        ("SWH", "Sai Wan Ho",         22.2812, 114.2220),
        ("SKW", "Shau Kei Wan",       22.2793, 114.2289),
        ("HFC", "Heng Fa Chuen",      22.2768, 114.2394),
        ("CHW", "Chai Wan",           22.2703, 114.2374),
    ],
    "KTL": [
        ("WHA", "Whampoa",            22.3046, 114.1922),
        ("HUH", "Hung Hom",           22.3025, 114.1823),
        ("TKW", "To Kwa Wan",         22.3131, 114.1876),
        ("SKM", "Shek Kip Mei",       22.3316, 114.1689),
        ("KOT", "Kowloon Tong",       22.3367, 114.1761),
        ("LOF", "Lok Fu",             22.3386, 114.1866),
        ("WTS", "Wong Tai Sin",       22.3420, 114.1947),
        ("DIH", "Diamond Hill",       22.3399, 114.2017),
        ("CHS", "Choi Hung",          22.3352, 114.2099),
        ("KOB", "Kowloon Bay",        22.3234, 114.2140),
        ("NTK", "Ngau Tau Kok",       22.3157, 114.2189),
        ("KWT", "Kwun Tong",          22.3121, 114.2263),
        ("LAT", "Lam Tin",            22.3069, 114.2327),
        ("YAT", "Yau Tong",           22.2990, 114.2373),
        ("TIK", "Tiu Keng Leng",      22.3040, 114.2534),
    ],
    "EAL": [
        ("HUH", "Hung Hom",           22.3025, 114.1823),
        ("MKK", "Mong Kok East",      22.3222, 114.1726),
        ("KOT", "Kowloon Tong",       22.3367, 114.1761),
        ("TAW", "Tai Wai",            22.3726, 114.1784),
        ("SHT", "Sha Tin",            22.3823, 114.1877),
        ("FO",  "Fo Tan",             22.3952, 114.1983),
        ("RAC", "Racecourse",         22.4022, 114.2022),
        ("UNI", "University",         22.4136, 114.2104),
        ("TAP", "Tai Po Market",      22.4446, 114.1703),
        ("TWO", "Tai Wo",             22.4505, 114.1620),
        ("FAN", "Fanling",            22.4921, 114.1387),
        ("SHS", "Sheung Shui",        22.5014, 114.1279),
        ("LOW", "Lo Wu",              22.5278, 114.1118),
        ("LMC", "Lok Ma Chau",        22.5100, 114.0743),
    ],
    "TML": [
        ("TUM", "Tuen Mun",           22.3952, 113.9734),
        ("SIH", "Siu Hong",           22.4099, 113.9782),
        ("TIS", "Tin Shui Wai",       22.4470, 113.9947),
        ("LOP", "Long Ping",          22.4484, 114.0275),
        ("YUL", "Yuen Long",          22.4449, 114.0360),
        ("KSK", "Kam Sheung Road",    22.4334, 114.0673),
        ("WKS", "Wu Kai Sha",         22.4290, 114.2441),
        ("MOS", "Ma On Shan",         22.4234, 114.2318),
    ],
    "SIL": [
        ("ADM", "Admiralty",          22.2791, 114.1650),
        ("OCP", "Ocean Park",         22.2488, 114.1748),
        ("WCH", "Wong Chuk Hang",     22.2466, 114.1688),
        ("LET", "Lei Tung",           22.2426, 114.1555),
        ("SOK", "South Horizons",     22.2432, 114.1489),
    ],
}

# Build a flat lookup: (line, code) → (name, lat, lon)
ALL_MTR_STATIONS: list = []
for _line, _stations in MTR_LINES.items():
    for _code, _name, _lat, _lon in _stations:
        ALL_MTR_STATIONS.append({
            "line": _line, "code": _code,
            "name": _name, "lat": _lat, "lon": _lon,
        })


# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Straight-line distance in metres between two WGS-84 points."""
    R = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def walk_minutes(metres: float) -> int:
    """Estimate walking time at 80 m/min."""
    return max(1, round(metres / 80))


def eta_minutes(eta_str: str) -> Optional[int]:
    """Parse ISO-8601 ETA string → minutes from now (None if invalid/past)."""
    if not eta_str:
        return None
    try:
        # Handle both +08:00 and Z suffixes
        ts = eta_str.replace("Z", "+00:00")
        eta_dt = datetime.fromisoformat(ts)
        now = datetime.now(timezone.utc).astimezone(eta_dt.tzinfo)
        mins = (eta_dt - now).total_seconds() / 60
        return round(mins) if mins >= -1 else None
    except Exception:
        return None


def fmt_mins(m: Optional[int]) -> str:
    if m is None:
        return "—"
    if m <= 0:
        return "Arriving"
    return f"{m} min"


def safe_get(url: str, params: dict = None, timeout: int = 10) -> Optional[dict]:
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def safe_post(url: str, payload: dict, timeout: int = 10) -> Optional[dict]:
    try:
        h = {**HEADERS, "Content-Type": "application/json"}
        r = requests.post(url, json=payload, headers=h, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def divider(char="─", width=62):
    print(char * width)


def header(title: str):
    print()
    divider()
    print(f"  {title}")
    divider()


# ─────────────────────────────────────────────────────────────────────────────
# Built-in HK Location Database
# Covers MTR stations, districts, universities, landmarks, hospitals, malls.
# Used first — Nominatim is only called as a fallback for unknown places.
# ─────────────────────────────────────────────────────────────────────────────

HK_LOCATIONS: dict[str, tuple[float, float]] = {
    # ── MTR Stations ──────────────────────────────────────────────────────────
    "admiralty":            (22.2791, 114.1650),
    "airport":              (22.3159, 113.9365),
    "asiaworld-expo":       (22.3218, 113.9417),
    "causeway bay":         (22.2805, 114.1836),
    "central":              (22.2818, 114.1574),
    "chai wan":             (22.2703, 114.2374),
    "cheung sha wan":       (22.3357, 114.1551),
    "choi hung":            (22.3352, 114.2099),
    "diamond hill":         (22.3399, 114.2017),
    "fanling":              (22.4921, 114.1387),
    "fo tan":               (22.3952, 114.1983),
    "fortress hill":        (22.2874, 114.1942),
    "heng fa chuen":        (22.2768, 114.2394),
    "hku":                  (22.2839, 114.1357),
    "hong kong":            (22.2850, 114.1584),
    "hong kong station":    (22.2850, 114.1584),
    "hung hom":             (22.3025, 114.1823),
    "jordan":               (22.3047, 114.1718),
    "kam sheung road":      (22.4334, 114.0673),
    "kennedy town":         (22.2813, 114.1284),
    "kowloon":              (22.3047, 114.1617),
    "kowloon bay":          (22.3234, 114.2140),
    "kowloon tong":         (22.3367, 114.1761),
    "kwai fong":            (22.3567, 114.1313),
    "kwai hing":            (22.3628, 114.1313),
    "kwun tong":            (22.3121, 114.2263),
    "lai chi kok":          (22.3370, 114.1479),
    "lai king":             (22.3480, 114.1246),
    "lam tin":              (22.3069, 114.2327),
    "lei tung":             (22.2426, 114.1555),
    "lo wu":                (22.5278, 114.1118),
    "lok fu":               (22.3386, 114.1866),
    "lok ma chau":          (22.5100, 114.0743),
    "long ping":            (22.4484, 114.0275),
    "ma on shan":           (22.4234, 114.2318),
    "mei foo":              (22.3384, 114.1381),
    "mong kok":             (22.3193, 114.1699),
    "mong kok east":        (22.3222, 114.1726),
    "nam cheong":           (22.3272, 114.1511),
    "ngau tau kok":         (22.3157, 114.2189),
    "north point":          (22.2905, 114.1996),
    "ocean park":           (22.2488, 114.1748),
    "olympic":              (22.3178, 114.1601),
    "prince edward":        (22.3247, 114.1682),
    "quarry bay":           (22.2882, 114.2093),
    "racecourse":           (22.4022, 114.2022),
    "sai wan ho":           (22.2812, 114.2220),
    "sai ying pun":         (22.2856, 114.1436),
    "sha tin":              (22.3823, 114.1877),
    "shau kei wan":         (22.2793, 114.2289),
    "shek kip mei":         (22.3316, 114.1689),
    "sheung shui":          (22.5014, 114.1279),
    "sheung wan":           (22.2866, 114.1513),
    "siu hong":             (22.4099, 113.9782),
    "south horizons":       (22.2432, 114.1489),
    "sunny bay":            (22.3324, 114.0285),
    "tai koo":              (22.2843, 114.2163),
    "tai po market":        (22.4446, 114.1703),
    "tai wai":              (22.3726, 114.1784),
    "tai wo":               (22.4505, 114.1620),
    "tin hau":              (22.2819, 114.1921),
    "tin shui wai":         (22.4470, 113.9947),
    "tiu keng leng":        (22.3040, 114.2534),
    "to kwa wan":           (22.3131, 114.1876),
    "tsim sha tsui":        (22.2975, 114.1722),
    "tst":                  (22.2975, 114.1722),
    "tsing yi":             (22.3588, 114.1073),
    "tsuen wan":            (22.3680, 114.1118),
    "tuen mun":             (22.3952, 113.9734),
    "tung chung":           (22.2883, 113.9426),
    "university":           (22.4136, 114.2104),
    "wan chai":             (22.2776, 114.1731),
    "whampoa":              (22.3046, 114.1922),
    "wong chuk hang":       (22.2466, 114.1688),
    "wong tai sin":         (22.3420, 114.1947),
    "wu kai sha":           (22.4290, 114.2441),
    "yau ma tei":           (22.3128, 114.1700),
    "yau tong":             (22.2990, 114.2373),
    "yuen long":            (22.4449, 114.0360),
    # ── Districts & Neighbourhoods ─────────────────────────────────────────────
    "aberdeen":             (22.2490, 114.1579),
    "ap lei chau":          (22.2424, 114.1529),
    "cheung chau":          (22.2100, 114.0233),
    "clear water bay":      (22.2760, 114.3040),
    "clearwater bay":       (22.2760, 114.3040),
    "discovery bay":        (22.3168, 114.0387),
    "happy valley":         (22.2693, 114.1843),
    "jordan road":          (22.3062, 114.1700),
    "kowloon city":         (22.3282, 114.1917),
    "kwun tong district":   (22.3130, 114.2260),
    "lantau":               (22.2556, 113.9440),
    "lamma island":         (22.2076, 114.1229),
    "ma wan":               (22.3557, 114.0600),
    "mid-levels":           (22.2812, 114.1502),
    "midlevels":            (22.2812, 114.1502),
    "new territories":      (22.4208, 114.1347),
    "outlying islands":     (22.2556, 113.9440),
    "peng chau":            (22.2869, 114.0398),
    "repulse bay":          (22.2369, 114.1970),
    "sai kung":             (22.3817, 114.2718),
    "sham shui po":         (22.3308, 114.1622),
    "shatin":               (22.3823, 114.1877),
    "shek o":               (22.2296, 114.2500),
    "soho":                 (22.2814, 114.1531),
    "stanley":              (22.2188, 114.2138),
    "tai po":               (22.4506, 114.1647),
    "tai tam":              (22.2479, 114.2245),
    "the peak":             (22.2759, 114.1455),
    "victoria peak":        (22.2759, 114.1455),
    "tuen mun town":        (22.3952, 113.9734),
    "tung lung chau":       (22.2442, 114.2989),
    "yuen long district":   (22.4449, 114.0360),
    # ── Universities & Schools ─────────────────────────────────────────────────
    "chinese university":           (22.4194, 114.2069),
    "cuhk":                         (22.4194, 114.2069),
    "city university":              (22.3361, 114.1713),
    "cityu":                        (22.3361, 114.1713),
    "hong kong university":         (22.2839, 114.1357),
    "hku university":               (22.2839, 114.1357),
    "hkust":                        (22.3359, 114.2637),
    "hong kong university of science and technology": (22.3359, 114.2637),
    "polyu":                        (22.3036, 114.1793),
    "polytechnic university":       (22.3036, 114.1793),
    "lingnan university":           (22.4352, 114.0392),
    "baptist university":           (22.3367, 114.1758),
    "hkbu":                         (22.3367, 114.1758),
    "education university":         (22.5369, 114.1706),
    "eduhk":                        (22.5369, 114.1706),
    # ── Hospitals ─────────────────────────────────────────────────────────────
    "queen mary hospital":          (22.2703, 114.1313),
    "queen elizabeth hospital":     (22.3107, 114.1742),
    "princess margaret hospital":   (22.3466, 114.1319),
    "prince of wales hospital":     (22.3806, 114.2003),
    "pamela youde nethersole":      (22.2807, 114.2267),
    "tuen mun hospital":            (22.4057, 113.9762),
    "united christian hospital":    (22.3229, 114.2297),
    "caritas medical centre":       (22.3397, 114.1525),
    "kwong wah hospital":           (22.3145, 114.1682),
    # ── Shopping Malls & Landmarks ────────────────────────────────────────────
    "ifc":                          (22.2856, 114.1583),
    "ifc mall":                     (22.2856, 114.1583),
    "pacific place":                (22.2779, 114.1642),
    "times square":                 (22.2791, 114.1827),
    "langham place":                (22.3161, 114.1693),
    "elements":                     (22.3043, 114.1605),
    "harbour city":                 (22.2987, 114.1693),
    "festival walk":                (22.3365, 114.1769),
    "new town plaza":               (22.3810, 114.1870),
    "citygate outlets":             (22.2889, 113.9430),
    "mega box":                     (22.3218, 114.2131),
    "apm":                          (22.3125, 114.2260),
    "star ferry":                   (22.2936, 114.1677),
    "star ferry pier":              (22.2936, 114.1677),
    "golden bauhinia square":       (22.2817, 114.1736),
    "hong kong park":               (22.2768, 114.1601),
    "hong kong disneyland":         (22.3130, 114.0460),
    "disneyland":                   (22.3130, 114.0460),
    "ocean park":                   (22.2488, 114.1748),
    "sky100":                       (22.3033, 114.1605),
    "victoria harbour":             (22.2948, 114.1702),
    "temple street":                (22.3095, 114.1701),
    "ladies market":                (22.3219, 114.1700),
    "mongkok":                      (22.3193, 114.1699),
    "sogo":                         (22.2810, 114.1833),
    "kai tak":                      (22.3299, 114.1994),
    "kai tak cruise terminal":      (22.3091, 114.2074),
    # ── Transport Hubs ────────────────────────────────────────────────────────
    "hkia":                         (22.3159, 113.9365),
    "hong kong international airport": (22.3159, 113.9365),
    "hung hom station":             (22.3025, 114.1823),
    "west kowloon":                 (22.3039, 114.1600),
    "west kowloon terminus":        (22.3039, 114.1600),
    "macau ferry terminal":         (22.2895, 114.1570),
    "china ferry terminal":         (22.3009, 114.1670),
}


def geocode(place: str) -> Optional[tuple[float, float]]:
    """
    Resolve a HK place name to (lat, lon).
    1. Checks the built-in HK_LOCATIONS table (instant, no network).
    2. Falls back to Nominatim with multiple strategies.
    """
    key = place.strip().lower()

    # 1 — exact match
    if key in HK_LOCATIONS:
        return HK_LOCATIONS[key]

    # 2 — partial / substring match (longest match wins)
    matches = [(k, v) for k, v in HK_LOCATIONS.items() if k in key or key in k]
    if matches:
        best = max(matches, key=lambda x: len(x[0]))
        return best[1]

    # 3 — Nominatim fallback for unknown places
    HK_LON = (113.8, 114.5)
    HK_LAT = (22.1,  22.6)
    hk_suffix = not any(t in key for t in ["hong kong", " hk", ", hk"])
    query_hk  = f"{place}, Hong Kong" if hk_suffix else place

    for params in [
        {"q": query_hk, "format": "json", "limit": 5, "countrycodes": "hk"},
        {"q": query_hk, "format": "json", "limit": 5},
        {"q": place,    "format": "json", "limit": 5},
    ]:
        data = safe_get(NOMINATIM, params)
        if not data:
            continue
        for r in data:
            lat, lon = float(r["lat"]), float(r["lon"])
            if HK_LAT[0] <= lat <= HK_LAT[1] and HK_LON[0] <= lon <= HK_LON[1]:
                return lat, lon

    return None


# ─────────────────────────────────────────────────────────────────────────────
# MTR
# ─────────────────────────────────────────────────────────────────────────────

def nearby_mtr(lat: float, lon: float, radius: int = 700) -> list:
    results = []
    seen = set()
    for s in ALL_MTR_STATIONS:
        d = haversine(lat, lon, s["lat"], s["lon"])
        if d <= radius:
            key = (s["line"], s["code"])
            if key not in seen:
                seen.add(key)
                results.append({**s, "dist": round(d)})
    return sorted(results, key=lambda x: x["dist"])


def mtr_eta(line: str, station_code: str) -> Optional[dict]:
    return safe_get(MTR_ETA, {"line": line, "sta": station_code})


def show_mtr(origin: tuple, dest: tuple):
    header("🚇  MTR (Mass Transit Railway)")

    near_o = nearby_mtr(*origin)
    near_d = nearby_mtr(*dest)

    if not near_o:
        print("  No MTR station within 700 m of origin.")
        return
    if not near_d:
        print("  No MTR station within 700 m of destination.")
        return

    # Find line(s) connecting origin → destination
    lines_o = {s["line"] for s in near_o}
    lines_d = {s["line"] for s in near_d}
    shared  = lines_o & lines_d

    if shared:
        print(f"  ✅ Direct MTR line(s) available: {', '.join(sorted(shared))}")
    else:
        print(f"  ↕️  May require interchange. Board near origin, transfer for destination.")

    # Show ETAs at closest origin station
    board = near_o[0]
    alight_options = [s for s in near_d[:3]]

    print(f"\n  Board at : {board['name']} ({board['line']}) — {board['dist']} m walk "
          f"(~{walk_minutes(board['dist'])} min)")

    # Alight suggestions
    for s in alight_options[:2]:
        print(f"  Alight at: {s['name']} ({s['line']}) — {s['dist']} m from destination")

    # Live ETA
    data = mtr_eta(board["line"], board["code"])
    if not data or data.get("status") == 0:
        print("\n  ⚠️  Live ETA unavailable for this station.")
        return

    station_data = data.get("data", {}).get(board["code"], {})
    print(f"\n  Live trains from {board['name']} ({board['line']}):")

    for direction, trains in station_data.items():
        if not isinstance(trains, list):
            continue
        times = [fmt_mins(eta_minutes(t.get("time", ""))) for t in trains[:3]]
        times = [t for t in times if t != "—"]
        if times:
            print(f"    → {direction:<20} {' | '.join(times)}")


# ─────────────────────────────────────────────────────────────────────────────
# KMB
# ─────────────────────────────────────────────────────────────────────────────

_kmb_stop_cache: list = []

def load_kmb_stops() -> list:
    global _kmb_stop_cache
    if _kmb_stop_cache:
        return _kmb_stop_cache
    data = safe_get(f"{KMB_BASE}/stop", timeout=20)
    if data:
        _kmb_stop_cache = data.get("data", [])
    return _kmb_stop_cache


def nearby_kmb(lat: float, lon: float, radius: int = 400) -> list:
    stops = load_kmb_stops()
    result = []
    for s in stops:
        try:
            d = haversine(lat, lon, float(s["lat"]), float(s["long"]))
            if d <= radius:
                result.append({**s, "dist": round(d)})
        except Exception:
            continue
    return sorted(result, key=lambda x: x["dist"])[:6]


def kmb_stop_eta(stop_id: str) -> list:
    data = safe_get(f"{KMB_BASE}/stop-eta/{stop_id}")
    return data.get("data", []) if data else []


def show_kmb(origin: tuple, dest: tuple):
    header("🚌  KMB (Kowloon Motor Bus)")

    stops_o = nearby_kmb(*origin)
    stops_d = nearby_kmb(*dest, radius=500)

    if not stops_o:
        print("  No KMB stops within 400 m of origin.")
        return

    dest_stop_ids = {s["stop"] for s in stops_d}

    found_any = False
    for stop in stops_o[:4]:
        etas = kmb_stop_eta(stop["stop"])
        if not etas:
            continue

        # Group by route, keep soonest 3 ETAs
        routes: dict[str, list] = {}
        for eta in etas:
            m = eta_minutes(eta.get("eta", ""))
            if m is None:
                continue
            r = eta.get("route", "?")
            routes.setdefault(r, []).append(m)

        if not routes:
            continue

        found_any = True
        walk = walk_minutes(stop["dist"])
        print(f"\n  📍 Stop: {stop.get('name_en', stop['stop'])}  ({stop['dist']} m, ~{walk} min walk)")

        for route, mins_list in sorted(routes.items()):
            times = " | ".join(f"{m} min" for m in sorted(mins_list)[:3])
            print(f"    Route {route:<6} → {times}")

    if not found_any:
        print("  No live KMB ETA data at nearby stops right now.")


# ─────────────────────────────────────────────────────────────────────────────
# Citybus (CTB)
# ─────────────────────────────────────────────────────────────────────────────

_ctb_stop_cache: list = []

def load_ctb_stops() -> list:
    global _ctb_stop_cache
    if _ctb_stop_cache:
        return _ctb_stop_cache
    data = safe_get(f"{CTB_BASE}/stop", timeout=20)
    if data:
        _ctb_stop_cache = data.get("data", [])
    return _ctb_stop_cache


def nearby_ctb(lat: float, lon: float, radius: int = 400) -> list:
    stops = load_ctb_stops()
    result = []
    for s in stops:
        try:
            d = haversine(lat, lon, float(s["lat"]), float(s["long"]))
            if d <= radius:
                result.append({**s, "dist": round(d)})
        except Exception:
            continue
    return sorted(result, key=lambda x: x["dist"])[:6]


def ctb_stop_routes(stop_id: str) -> list:
    """Get all routes serving a CTB stop."""
    data = safe_get(f"{CTB_BASE}/route-stop/CTB/{stop_id}")
    return data.get("data", []) if data else []


def ctb_eta(stop_id: str, route: str) -> list:
    data = safe_get(f"{CTB_BASE}/eta/CTB/{stop_id}/{route}")
    return data.get("data", []) if data else []


def show_ctb(origin: tuple, dest: tuple):
    header("🚌  Citybus (CTB)")

    stops_o = nearby_ctb(*origin)
    if not stops_o:
        print("  No Citybus stops within 400 m of origin.")
        return

    found_any = False
    for stop in stops_o[:4]:
        routes_at_stop = ctb_stop_routes(stop["stop"])
        if not routes_at_stop:
            continue

        route_etas: dict[str, list] = {}
        for r in routes_at_stop[:10]:          # cap API calls per stop
            route_no = r.get("route", "")
            etas = ctb_eta(stop["stop"], route_no)
            for eta in etas:
                m = eta_minutes(eta.get("eta", ""))
                if m is not None:
                    route_etas.setdefault(route_no, []).append(m)
            time.sleep(0.05)                   # polite rate limiting

        if not route_etas:
            continue

        found_any = True
        walk = walk_minutes(stop["dist"])
        print(f"\n  📍 Stop: {stop.get('name_en', stop['stop'])}  ({stop['dist']} m, ~{walk} min walk)")

        for route, mins_list in sorted(route_etas.items()):
            times = " | ".join(f"{m} min" for m in sorted(mins_list)[:3])
            print(f"    Route {route:<6} → {times}")

    if not found_any:
        print("  No live Citybus ETA data at nearby stops right now.")


# ─────────────────────────────────────────────────────────────────────────────
# Green Minibus (GMB)
# ─────────────────────────────────────────────────────────────────────────────

def gmb_nearby_stops(lat: float, lon: float) -> list:
    """
    GMB stop list isn't easily paginated, so we use the region-route approach:
    query nearby stops via the stop search endpoint (undocumented but works).
    """
    data = safe_get(f"{GMB_BASE}/stop", timeout=15)
    if not data:
        return []
    stops = data.get("data", {}).get("stops", []) or []
    result = []
    for s in stops:
        try:
            d = haversine(lat, lon, float(s["coordinates"]["wgs84"]["latitude"]),
                          float(s["coordinates"]["wgs84"]["longitude"]))
            if d <= 400:
                result.append({**s, "dist": round(d)})
        except Exception:
            continue
    return sorted(result, key=lambda x: x["dist"])[:4]


def gmb_stop_eta(stop_id: int) -> list:
    data = safe_get(f"{GMB_BASE}/eta/stop/{stop_id}", timeout=10)
    if not data:
        return []
    return data.get("data", {}).get("routes", [])


def show_gmb(origin: tuple):
    header("🚐  Green Minibus (GMB)")
    stops = gmb_nearby_stops(*origin)
    if not stops:
        print("  No GMB stops within 400 m (or data unavailable).")
        return

    found_any = False
    for stop in stops:
        etas = gmb_stop_eta(stop.get("stop_id", 0))
        if not etas:
            continue
        found_any = True
        walk = walk_minutes(stop["dist"])
        name = stop.get("name_en") or stop.get("stop_id", "?")
        print(f"\n  📍 Stop: {name}  ({stop['dist']} m, ~{walk} min walk)")
        for route_data in etas[:5]:
            route_seq = route_data.get("route_seq", "?")
            for eta_item in route_data.get("eta", [])[:3]:
                m = eta_minutes(eta_item.get("timestamp", ""))
                if m is not None:
                    print(f"    Route Seq {route_seq} → {m} min")

    if not found_any:
        print("  No live GMB data nearby right now.")


# ─────────────────────────────────────────────────────────────────────────────
# Driving (TDAS) — for comparison
# ─────────────────────────────────────────────────────────────────────────────

def show_driving(origin: tuple, dest: tuple):
    header("🚗  Driving (live traffic via TDAS — for comparison)")

    result = safe_post(TDAS_ROUTE, {
        "start":     {"lat": origin[0], "long": origin[1]},
        "end":       {"lat": dest[0],   "long": dest[1]},
        "departIn":  0,
        "lang":      "en",
        "type":      "ST",
    })

    if not result:
        print("  TDAS data unavailable.")
        return

    speed = result.get("jSpeed", "N/A")
    eta   = result.get("eta",    "N/A")
    dist  = result.get("distU",  "N/A")
    cht   = "✅" if result.get("cht") else "—"
    wht   = "✅" if result.get("wht") else "—"
    eht   = "✅" if result.get("eht") else "—"

    print(f"  Current avg speed : {speed} km/h")
    print(f"  Estimated ETA     : {eta}")
    print(f"  Distance          : {dist}")
    print(f"  Tunnel usage      → Cross-Harbour: {cht}  Western: {wht}  Eastern: {eht}")

    alts = result.get("ar", [])
    if alts:
        print("\n  Alternative tunnel routes:")
        for a in alts:
            print(f"    via {a.get('name', '?')}: {a.get('eta', '?')} ({a.get('distU', '?')})")


# ─────────────────────────────────────────────────────────────────────────────
# Smart Recommendation Engine
# ─────────────────────────────────────────────────────────────────────────────

def recommend(origin: tuple, dest: tuple, dist_km: float):
    header("💡  Smart Recommendation")

    near_mtr_o = nearby_mtr(*origin, radius=700)
    near_mtr_d = nearby_mtr(*dest,   radius=700)

    lines_o = {s["line"] for s in near_mtr_o}
    lines_d = {s["line"] for s in near_mtr_d}
    direct_mtr = lines_o & lines_d

    driving_data = safe_post(TDAS_ROUTE, {
        "start":    {"lat": origin[0], "long": origin[1]},
        "end":      {"lat": dest[0],   "long": dest[1]},
        "departIn": 0, "lang": "en", "type": "ST",
    })

    rec = []

    # Walking?
    if dist_km < 0.85:
        rec.append(("🚶 WALK", f"Only {dist_km:.1f} km — fastest option, ~{round(dist_km*1000/80)} min."))

    # Direct MTR?
    if direct_mtr and near_mtr_o and near_mtr_d:
        board  = near_mtr_o[0]
        alight = near_mtr_d[0]
        walk_to   = walk_minutes(board["dist"])
        walk_from = walk_minutes(alight["dist"])
        rec.append((
            f"🚇 MTR ({', '.join(sorted(direct_mtr))})",
            f"Walk {board['dist']} m to {board['name']} (~{walk_to} min), "
            f"ride MTR, alight at {alight['name']} ({walk_from} min walk to dest)."
        ))
    elif near_mtr_o and near_mtr_d:
        rec.append((
            "🚇 MTR (with interchange)",
            f"Board at {near_mtr_o[0]['name']} ({near_mtr_o[0]['line']}), "
            f"transfer to reach {near_mtr_d[0]['name']} side."
        ))

    # Bus?
    if dist_km > 1.5:
        rec.append(("🚌 Bus (KMB/CTB)", "Check ETAs above — pick the bus with the soonest departure to your area."))

    # Driving?
    if driving_data:
        speed = driving_data.get("jSpeed", 0)
        eta   = driving_data.get("eta", "?")
        try:
            spd = float(str(speed).split()[0])
        except Exception:
            spd = 30
        if spd < 15:
            rec.append(("🚗 Drive", f"⚠️  Heavy traffic ({speed} km/h). Avoid driving, ETA {eta}."))
        elif spd < 25:
            rec.append(("🚗 Drive", f"🟡 Slow traffic ({speed} km/h). Consider transit, ETA {eta}."))
        else:
            rec.append(("🚗 Drive", f"🟢 Traffic OK ({speed} km/h), ETA {eta}."))

    if not rec:
        rec.append(("🚌 Bus", "Check bus ETAs above for the best option."))

    print()
    for i, (mode, detail) in enumerate(rec, 1):
        marker = "★" if i == 1 else f"{i}."
        print(f"  {marker}  {mode}")
        print(f"      {detail}")
        print()


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print()
    print("=" * 62)
    print("   🚦  Smart HK Public Transport Advisor")
    print("=" * 62)
    print("   APIs: KMB · Citybus · MTR · GMB · TDAS · Nominatim")
    print("=" * 62)

    # ── Input ────────────────────────────────────────────────────────────────
    try:
        origin_input = input("\n  Origin      : ").strip()
        dest_input   = input("  Destination : ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\n  Bye!")
        sys.exit(0)

    if not origin_input or not dest_input:
        print("  ❌ Please provide both origin and destination.")
        sys.exit(1)

    # ── Geocode ──────────────────────────────────────────────────────────────
    print("\n  ⏳ Geocoding locations …")
    origin = geocode(origin_input)
    dest   = geocode(dest_input)

    if not origin:
        print(f"  ❌ Could not find: '{origin_input}'. Try a more specific name.")
        sys.exit(1)
    if not dest:
        print(f"  ❌ Could not find: '{dest_input}'. Try a more specific name.")
        sys.exit(1)

    dist_km = haversine(*origin, *dest) / 1000

    print(f"\n  ✅ From : {origin_input:<30}  ({origin[0]:.4f}, {origin[1]:.4f})")
    print(f"  ✅ To   : {dest_input:<30}  ({dest[0]:.4f}, {dest[1]:.4f})")
    print(f"  📏 Straight-line distance : {dist_km:.2f} km")
    print(f"  🕐 Query time             : {datetime.now().strftime('%H:%M:%S, %d %b %Y')}")

    # ── Pre-load stop databases ───────────────────────────────────────────────
    print("\n  ⏳ Loading bus stop databases …")
    kmb_stops = load_kmb_stops()
    ctb_stops = load_ctb_stops()
    print(f"     KMB: {len(kmb_stops):,} stops loaded")
    print(f"     CTB: {len(ctb_stops):,} stops loaded")

    # ── Transit sections ──────────────────────────────────────────────────────
    show_mtr(origin, dest)
    show_kmb(origin, dest)
    show_ctb(origin, dest)
    show_gmb(origin)
    show_driving(origin, dest)
    recommend(origin, dest, dist_km)

    print("=" * 62)
    print("  Data sources: data.etabus.gov.hk · rt.data.gov.hk")
    print("                data.etagmb.gov.hk · tdas-api.hkemobility.gov.hk")
    print("                nominatim.openstreetmap.org")
    print("=" * 62)
    print()


if __name__ == "__main__":
    main()