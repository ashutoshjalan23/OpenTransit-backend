"""
file_io.py - File I/O for loading and saving transport network data.

File format (CSV):
  stops.csv   -> id,name,latitude,longitude,lines
  segments.csv -> seg_id,from_stop,to_stop,mode,duration,cost
  journeys.txt -> saved journey results (human-readable)
"""

import csv
import os
from network import Stop, Segment, Network


DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


class DataFormatError(ValueError):
    """Raised when a network CSV file exists but does not match the format."""


def _check_headers(reader, required_fields, filepath):
    if reader.fieldnames is None:
        raise DataFormatError(f"{filepath} is empty or missing a CSV header row.")

    missing = [field for field in required_fields if field not in reader.fieldnames]
    if missing:
        fields = ", ".join(missing)
        raise DataFormatError(f"{filepath} is missing required column(s): {fields}.")


def _required(row, field, row_num, filepath):
    value = row.get(field)
    if value is None or str(value).strip() == "":
        raise DataFormatError(f"{filepath} row {row_num}: missing required field '{field}'.")
    return str(value).strip()


def _optional_float(row, field, row_num, filepath, default=0.0):
    value = row.get(field, "")
    if value is None or str(value).strip() == "":
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise DataFormatError(
            f"{filepath} row {row_num}: field '{field}' must be a number."
        ) from exc


def _non_negative_float(row, field, row_num, filepath):
    value = _required(row, field, row_num, filepath)
    try:
        parsed = float(value)
    except ValueError as exc:
        raise DataFormatError(
            f"{filepath} row {row_num}: field '{field}' must be a number."
        ) from exc
    if parsed < 0:
        raise DataFormatError(
            f"{filepath} row {row_num}: field '{field}' cannot be negative."
        )
    return parsed


def load_stops(filepath):
    """Load stops from CSV. Returns dict {id: Stop}."""
    stops = {}
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        _check_headers(reader, ["id", "name"], filepath)

        for row_num, row in enumerate(reader, start=2):
            sid = _required(row, "id", row_num, filepath)
            if sid in stops:
                raise DataFormatError(f"{filepath} row {row_num}: duplicate stop id '{sid}'.")
            lines = [l.strip() for l in row.get("lines", "").split(";") if l.strip()]
            stop = Stop(
                stop_id=sid,
                name=_required(row, "name", row_num, filepath),
                latitude=_optional_float(row, "latitude", row_num, filepath),
                longitude=_optional_float(row, "longitude", row_num, filepath),
                available_lines=lines,
            )
            stops[sid] = stop

    if not stops:
        raise DataFormatError(f"{filepath} contains no stops.")
    return stops


def load_segments(filepath):
    """Load segments from CSV. Returns list of Segment objects."""
    segments = []
    seen_ids = set()
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        _check_headers(
            reader,
            ["seg_id", "from_stop", "to_stop", "mode", "duration", "cost"],
            filepath,
        )

        for row_num, row in enumerate(reader, start=2):
            seg_id = _required(row, "seg_id", row_num, filepath)
            if seg_id in seen_ids:
                raise DataFormatError(
                    f"{filepath} row {row_num}: duplicate segment id '{seg_id}'."
                )
            seen_ids.add(seg_id)

            seg = Segment(
                seg_id=seg_id,
                from_stop=_required(row, "from_stop", row_num, filepath),
                to_stop=_required(row, "to_stop", row_num, filepath),
                mode=_required(row, "mode", row_num, filepath),
                duration=_non_negative_float(row, "duration", row_num, filepath),
                cost=_non_negative_float(row, "cost", row_num, filepath),
            )
            segments.append(seg)

    if not segments:
        raise DataFormatError(f"{filepath} contains no segments.")
    return segments


def load_network(stops_file=None, segments_file=None):
    """Build a Network from CSV files."""
    if stops_file is None:
        stops_file = os.path.join(DATA_DIR, "stops.csv")
    if segments_file is None:
        segments_file = os.path.join(DATA_DIR, "segments.csv")

    net = Network()

    stops = load_stops(stops_file)
    segments = load_segments(segments_file)

    for seg in segments:
        if seg.from_stop not in stops:
            raise DataFormatError(
                f"{segments_file}: segment '{seg.seg_id}' references unknown "
                f"from_stop '{seg.from_stop}'."
            )
        if seg.to_stop not in stops:
            raise DataFormatError(
                f"{segments_file}: segment '{seg.seg_id}' references unknown "
                f"to_stop '{seg.to_stop}'."
            )

    for stop in stops.values():
        net.add_stop(stop)

    for seg in segments:
        net.add_segment(seg)

    return net


def save_journey_results(journeys, preference, origin, dest, filepath=None):
    """Save ranked journey results to a human-readable text file."""
    if filepath is None:
        filepath = os.path.join(DATA_DIR, "last_results.txt")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"Smart Public Transport Advisor - Journey Results\n")
        f.write(f"{'=' * 55}\n")
        f.write(f"Origin:      {origin}\n")
        f.write(f"Destination: {dest}\n")
        f.write(f"Preference:  {preference}\n")
        f.write(f"Routes found: {len(journeys)}\n")
        f.write(f"{'=' * 55}\n\n")

        for i, j in enumerate(journeys, 1):
            s = j.summary_dict()
            f.write(f"Route #{i}\n")
            if not s:
                f.write("  Empty route: origin and destination are the same.\n")
                f.write(f"{'-' * 55}\n")
                continue
            f.write(f"  Cost:     HK${s['total_cost']:.1f}\n")
            f.write(f"  Time:     {s['total_time']:.0f} min\n")
            f.write(f"  Hops:     {s['num_hops']}\n")
            f.write(f"  Path:     {' -> '.join(s['stops'])}\n")
            f.write(f"  Modes:    {' -> '.join(s['modes'])}\n")
            f.write(f"{'-' * 55}\n")

    return filepath


def save_stops(stops_dict, filepath=None):
    """Save stops to CSV."""
    if filepath is None:
        filepath = os.path.join(DATA_DIR, "stops.csv")

    with open(filepath, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "name", "latitude", "longitude", "lines"])
        for s in sorted(stops_dict.values(), key=lambda x: x.id):
            writer.writerow([
                s.id, s.name, s.latitude, s.longitude,
                ";".join(s.available_lines)
            ])


def save_segments(segments_list, filepath=None):
    """Save segments to CSV."""
    if filepath is None:
        filepath = os.path.join(DATA_DIR, "segments.csv")

    with open(filepath, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["seg_id", "from_stop", "to_stop", "mode", "duration", "cost"])
        for seg in segments_list:
            writer.writerow([
                seg.seg_id, seg.from_stop, seg.to_stop,
                seg.mode, seg.duration, seg.cost
            ])
