"""
network.py - Transport network data model and DFS route finder.

Core entities:
  Stop    - A named point in the network (station/stop)
  Segment - A direct connection between two stops (one transport mode)
  Network - The graph structure + DFS path enumeration
"""


class Stop:
    """A named point where passengers can board, alight, or transfer."""

    def __init__(self, stop_id, name, latitude=0.0, longitude=0.0, available_lines=None):
        self.id = stop_id
        self.name = name
        self.latitude = latitude
        self.longitude = longitude
        self.available_lines = available_lines or []

    def __repr__(self):
        return f"Stop({self.id}, {self.name})"


class Segment:
    """A direct connection between exactly two stops."""

    def __init__(self, seg_id, from_stop, to_stop, mode, duration, cost):
        self.seg_id = seg_id
        self.from_stop = from_stop   # stop id
        self.to_stop = to_stop       # stop id
        self.mode = mode             # e.g. "MTR", "Bus", "Minibus", "Ferry", "Tram"
        self.duration = duration     # minutes
        self.cost = cost             # HKD

    def __repr__(self):
        return f"Segment({self.seg_id}: {self.from_stop}->{self.to_stop} [{self.mode}])"


class Network:
    """
    Graph-based transport network.
    Uses adjacency list representation and DFS to enumerate all simple paths.
    """

    def __init__(self):
        self.stops = {}       # id -> Stop
        self.segments = {}    # seg_id -> Segment
        self.adj = {}         # from_stop_id -> [Segment, ...]

    # ---- building the graph ----

    def add_stop(self, stop):
        self.stops[stop.id] = stop
        if stop.id not in self.adj:
            self.adj[stop.id] = []

    def add_segment(self, segment):
        self.segments[segment.seg_id] = segment
        if segment.from_stop not in self.adj:
            self.adj[segment.from_stop] = []
        self.adj[segment.from_stop].append(segment)

    def get_stop_name(self, stop_id):
        if stop_id in self.stops:
            return self.stops[stop_id].name
        return str(stop_id)

    def get_stop_id_by_name(self, name):
        """Case-insensitive lookup by stop name. Returns id or None."""
        name_lower = name.strip().lower()
        for sid, stop in self.stops.items():
            if stop.name.lower() == name_lower:
                return sid
        return None

    def resolve_stop_id(self, value):
        """
        Resolve common user input to a stop ID.

        Accepts exact IDs in any case (S01, s01), numeric shortcuts (1, 01),
        and the common typo where the zero is typed as the letter O (so1).
        Exact stop names are also accepted case-insensitively.
        """
        if value is None:
            return None

        raw = str(value).strip()
        if not raw:
            return None

        compact = "".join(ch for ch in raw.upper() if ch.isalnum())
        for sid in self.stops:
            if sid.upper() == compact:
                return sid

        name_match = self.get_stop_id_by_name(raw)
        if name_match:
            return name_match

        token = compact
        if token.startswith("S"):
            suffix = token[1:].replace("O", "0")
        else:
            suffix = token.replace("O", "0")

        if suffix and suffix.isdigit():
            number = int(suffix)
            for candidate in (f"S{number:02d}", f"S{number}", f"S{number:03d}"):
                for sid in self.stops:
                    if sid.upper() == candidate:
                        return sid

        return None

    def list_stop_names(self):
        """Return sorted list of (id, name) tuples."""
        return sorted([(s.id, s.name) for s in self.stops.values()], key=lambda x: x[0])

    # ---- DFS path finder ----

    def find_all_paths(self, origin_id, dest_id, max_depth=6):
        """
        DFS: enumerate ALL simple paths from origin to destination.

        Returns a list of paths, where each path is a list of Segment objects.
        max_depth caps the search to avoid extremely long paths.

        Algorithm (Depth-First Search):
          1. Start at origin, mark it visited.
          2. For each outgoing segment whose to_stop is not visited:
             a. If to_stop == destination, record the current path.
             b. Otherwise, recurse deeper (if depth < max_depth).
          3. Backtrack: unmark the current node so other paths can use it.

        This guarantees ALL candidate routes are generated, enabling the
        scoring module to transparently compare every option.
        """
        all_paths = []
        visited = set()

        def _dfs(current, path):
            if current == dest_id:
                all_paths.append(list(path))
                return
            if len(path) >= max_depth:
                return

            visited.add(current)
            for seg in self.adj.get(current, []):
                if seg.to_stop not in visited:
                    path.append(seg)
                    _dfs(seg.to_stop, path)
                    path.pop()
            visited.remove(current)

        _dfs(origin_id, [])
        return all_paths

    def find_paths_with_stats(self, origin_id, dest_id, max_depth=6):
        """
        Same as find_all_paths but also computes journey statistics:
        - total duration (minutes)
        - total cost (HKD)
        - number of segments (transfers + 1)

        Returns a list of dicts:
            {
                'segments': [Segment, ...],
                'duration': int,   # total minutes
                'cost': float,     # total HKD
                'transfers': int   # number of vehicle changes
            }
        """
        raw_paths = self.find_all_paths(origin_id, dest_id, max_depth)
        enriched = []
        for segments in raw_paths:
            duration = sum(seg.duration for seg in segments)
            cost = sum(seg.cost for seg in segments)
            transfers = len(segments) - 1
            enriched.append({
                'segments': segments,
                'duration': duration,
                'cost': cost,
                'transfers': transfers
            })
        return enriched
