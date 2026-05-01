"""
Lightweight Python backend for the Open Transit website.

Run:
    python backend_api.py

The server exposes a small JSON API over the existing CSV dataset and
Python journey engine:
    GET  /health
    GET  /network
    GET  /eta?stopId=S01
    POST /plan
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import journey as journey_logic
from check import eta_minutes, kmb_stop_eta, mtr_eta, nearby_kmb, nearby_mtr
from file_io import load_network


HOST = os.environ.get("HK_TRANSIT_BACKEND_HOST", "127.0.0.1")
PORT = int(os.environ.get("HK_TRANSIT_BACKEND_PORT", "8000"))
MAX_DEPTH = 8
RESULT_LIMIT = 5

NETWORK = load_network()


def serialise_stop(stop):
    return {
        "id": stop.id,
        "name": stop.name,
        "lat": stop.latitude,
        "lon": stop.longitude,
        "lines": list(stop.available_lines),
    }


def serialise_segment(segment):
    return {
        "segId": segment.seg_id,
        "fromStop": segment.from_stop,
        "toStop": segment.to_stop,
        "mode": segment.mode,
        "duration": segment.duration,
        "cost": segment.cost,
    }


def stops_for_segments(segments):
    if not segments:
        return []
    stop_ids = [segments[0].from_stop, *[segment.to_stop for segment in segments]]
    return [serialise_stop(NETWORK.stops[stop_id]) for stop_id in stop_ids if stop_id in NETWORK.stops]


def serialise_journey(journey):
    return {
        "segments": [serialise_segment(segment) for segment in journey.segments],
        "stops": stops_for_segments(journey.segments),
        "totalCost": round(journey.total_cost, 1),
        "totalTime": round(journey.total_time, 1),
        "adjustedTime": round(journey.adjusted_time, 1),
        "numHops": journey.num_hops,
    }


def format_minutes(minutes):
    if minutes is None:
        return None
    if minutes <= 0:
        return "Arriving"
    return f"{int(minutes)} min"


def normalise_name(value):
    return "".join(ch.lower() for ch in value if ch.isalnum())


def pick_mtr_station(stop):
    nearby = nearby_mtr(stop.latitude, stop.longitude, radius=900)
    if not nearby:
        return None

    stop_name = normalise_name(stop.name)
    for candidate in nearby:
        if normalise_name(candidate["name"]) == stop_name:
            return candidate

    return nearby[0]


def parse_mtr_entries(stop):
    station = pick_mtr_station(stop)
    if not station:
        return []

    data = mtr_eta(station["line"], station["code"])
    if not data or data.get("status") == 0:
        return []

    data_key = f'{station["line"]}-{station["code"]}'
    station_data = data.get("data", {}).get(data_key)
    if station_data is None:
        station_data = data.get("data", {}).get(station["code"], {})

    entries = []
    for direction, trains in station_data.items():
        if not isinstance(trains, list):
            continue

        times = []
        for train in trains:
            minutes = None
            ttnt = train.get("ttnt")
            if ttnt not in (None, "", "-"):
                try:
                    minutes = max(0, int(round(float(ttnt))))
                except (TypeError, ValueError):
                    minutes = None
            if minutes is None:
                minutes = eta_minutes(train.get("time", ""))

            label = format_minutes(minutes)
            if label is not None:
                times.append(label)
            if len(times) == 3:
                break

        if times:
            entries.append({
                "mode": "MTR",
                "label": f'MTR {station["line"]} {direction.upper()}',
                "times": times,
            })

    return entries


def parse_kmb_entries(stop):
    nearby = nearby_kmb(stop.latitude, stop.longitude, radius=400)
    if not nearby:
        return []

    eta_rows = kmb_stop_eta(nearby[0]["stop"])
    grouped = {}

    for row in eta_rows:
        minutes = eta_minutes(row.get("eta", ""))
        if minutes is None:
            continue

        route = row.get("route", "Bus")
        destination = row.get("dest_en") or row.get("dest_tc") or "upcoming service"
        service_type = row.get("service_type")
        label = f"KMB {route} to {destination}"
        if service_type not in (None, "", "1"):
            label = f"{label} (svc {service_type})"

        grouped.setdefault(label, [])
        if len(grouped[label]) < 3:
            grouped[label].append(minutes)

    entries = []
    for label, minutes in grouped.items():
        entries.append({
            "mode": "Bus",
            "label": label,
            "times": [value for value in (format_minutes(minute) for minute in minutes) if value],
            "nextMinute": minutes[0],
        })

    entries.sort(key=lambda item: item["nextMinute"])
    return [
        {
            "mode": entry["mode"],
            "label": entry["label"],
            "times": entry["times"],
        }
        for entry in entries[:3]
        if entry["times"]
    ]


def build_eta_payload(stop_id):
    stop = NETWORK.stops.get(stop_id)
    if stop is None:
        return None

    entries = []
    if "MTR" in stop.available_lines:
        entries.extend(parse_mtr_entries(stop))
    if "Bus" in stop.available_lines or "Minibus" in stop.available_lines:
        entries.extend(parse_kmb_entries(stop))

    return {
        "stopId": stop_id,
        "timestamp": datetime.now().strftime("%H:%M"),
        "entries": entries,
    }


def apply_realtime_adjustments(journeys):
    mtr_stop_ids = sorted({
        segment.from_stop
        for journey in journeys
        for segment in journey.segments
        if segment.mode == "MTR"
    })
    bus_stop_ids = sorted({
        segment.from_stop
        for journey in journeys
        for segment in journey.segments
        if segment.mode in ("Bus", "Minibus")
    })
    traffic_keys = sorted({
        (segment.from_stop, segment.to_stop)
        for journey in journeys
        for segment in journey.segments
        if segment.mode in ("Bus", "Minibus")
    })

    with ThreadPoolExecutor(max_workers=12) as executor:
        mtr_waits = dict(zip(
            mtr_stop_ids,
            executor.map(lambda stop_id: journey_logic._live_mtr_wait(stop_id, NETWORK), mtr_stop_ids),
        ))
        bus_waits = dict(zip(
            bus_stop_ids,
            executor.map(lambda stop_id: journey_logic._live_bus_wait(stop_id, NETWORK), bus_stop_ids),
        ))
        traffic_multipliers = dict(zip(
            traffic_keys,
            executor.map(
                lambda key: journey_logic._traffic_multiplier(key[0], key[1], NETWORK),
                traffic_keys,
            ),
        ))

    for journey in journeys:
        adjusted = 0.0
        for segment in journey.segments:
            ride_time = float(segment.duration)

            if segment.mode == "MTR":
                adjusted += ride_time + mtr_waits[segment.from_stop]
                continue

            if segment.mode in ("Bus", "Minibus"):
                segment_key = (segment.from_stop, segment.to_stop)
                adjusted += (ride_time * traffic_multipliers[segment_key]) + bus_waits[segment.from_stop]
                continue

            if segment.mode == "Ferry":
                adjusted += ride_time + 5.0
                continue

            if segment.mode == "Tram":
                adjusted += ride_time + 2.0
                continue

            adjusted += ride_time

        journey.adjusted_time = round(adjusted, 1)


def build_plan_payload(origin_id, dest_id, preference, realtime):
    paths = NETWORK.find_all_paths(origin_id, dest_id, max_depth=MAX_DEPTH)
    journeys = journey_logic.build_journeys(paths, NETWORK, realtime=False)

    if realtime:
        apply_realtime_adjustments(journeys)

    ranked = journey_logic.rank_journeys(journeys, preference)[:RESULT_LIMIT]

    return {
        "total": len(paths),
        "shown": len(ranked),
        "realtime": realtime,
        "routes": [serialise_journey(journey) for journey in ranked],
    }


class TransitRequestHandler(BaseHTTPRequestHandler):
    server_version = "HKTransitBackend/1.0"

    def log_message(self, fmt, *args):
        return

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_common_headers()
        self.end_headers()

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            query = parse_qs(parsed.query)

            if path == "/health":
                self.send_json(200, {"ok": True})
                return

            if path == "/network":
                self.send_json(200, {
                    "stops": [serialise_stop(stop) for stop in NETWORK.stops.values()],
                    "segments": [serialise_segment(segment) for segment in NETWORK.segments.values()],
                })
                return

            if path == "/eta":
                stop_id = first_query_value(query, "stopId", "stop_id")
                if not stop_id:
                    self.send_json(400, {"error": "Missing stopId"})
                    return

                payload = build_eta_payload(stop_id)
                if payload is None:
                    self.send_json(404, {"error": "Unknown stop"})
                    return

                self.send_json(200, payload)
                return

            self.send_json(404, {"error": "Not found"})
        except Exception as exc:
            self.send_json(500, {"error": f"Unexpected server error: {exc}"})

    def do_POST(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            if path != "/plan":
                self.send_json(404, {"error": "Not found"})
                return

            body = self.read_json_body()
            origin_id = body.get("originId")
            dest_id = body.get("destId")
            preference = body.get("preference")
            realtime = bool(body.get("realtime"))

            if not origin_id or not dest_id or preference not in journey_logic.PREFERENCE_KEYS:
                self.send_json(400, {"error": "Invalid journey request"})
                return
            if origin_id == dest_id:
                self.send_json(400, {"error": "Origin and destination must differ"})
                return
            if origin_id not in NETWORK.stops or dest_id not in NETWORK.stops:
                self.send_json(400, {"error": "Unknown stop"})
                return

            payload = build_plan_payload(origin_id, dest_id, preference, realtime)
            self.send_json(200, payload)
        except json.JSONDecodeError:
            self.send_json(400, {"error": "Malformed JSON body"})
        except Exception as exc:
            self.send_json(500, {"error": f"Unexpected server error: {exc}"})

    def send_common_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Cache-Control", "no-store")

    def send_json(self, status_code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_common_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length) if length else b"{}"
        return json.loads(raw_body.decode("utf-8"))


def first_query_value(query, *names):
    for name in names:
        values = query.get(name)
        if values:
            return values[0]
    return None


def serve():
    server = ThreadingHTTPServer((HOST, PORT), TransitRequestHandler)
    print(f"Open Transit backend listening on http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    serve()
