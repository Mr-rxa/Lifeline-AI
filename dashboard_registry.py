import time
import queue
import threading
from utils import haversine

_sessions = {}  # session_id -> {lat: float, lon: float, last_seen: float, q: Queue}
_lock = threading.RLock()

def _cleanup_stale_locked(max_age_s=60):
    """Internal helper: Remove sessions that haven't sent a heartbeat within max_age_s.
    Assumes _lock is already held.
    """
    now = time.time()
    stale = [sid for sid, data in _sessions.items() if (now - data['last_seen']) > max_age_s]
    for sid in stale:
        del _sessions[sid]

def cleanup_stale(max_age_s=60):
    """Remove sessions that haven't sent a heartbeat within max_age_s."""
    with _lock:
        _cleanup_stale_locked(max_age_s)

def register(session_id, lat=None, lon=None):
    """Register or update a dashboard session."""
    if not session_id:
        return
    with _lock:
        if session_id not in _sessions:
            _sessions[session_id] = {
                'lat': float(lat) if lat is not None else 28.6139,
                'lon': float(lon) if lon is not None else 77.2090,
                'last_seen': time.time(),
                'q': queue.Queue()
            }
        else:
            if lat is not None:
                _sessions[session_id]['lat'] = float(lat)
            if lon is not None:
                _sessions[session_id]['lon'] = float(lon)
            _sessions[session_id]['last_seen'] = time.time()

def heartbeat(session_id):
    """Update last_seen timestamp for session."""
    with _lock:
        if session_id in _sessions:
            _sessions[session_id]['last_seen'] = time.time()

def unregister(session_id):
    """Explicitly remove a session."""
    with _lock:
        _sessions.pop(session_id, None)

def find_nearest(lat, lon):
    """Return session_id of nearest active dashboard, or None."""
    with _lock:
        _cleanup_stale_locked()
        if not _sessions:
            return None
        min_dist = float('inf')
        nearest_sid = None
        for sid, data in _sessions.items():
            dist = haversine(float(lat), float(lon), data['lat'], data['lon'])
            if dist < min_dist:
                min_dist = dist
                nearest_sid = sid
        return nearest_sid

def find_within_radius(lat, lon, radius_km=5.0):
    """Return list of session_ids within radius_km."""
    with _lock:
        _cleanup_stale_locked()
        results = []
        for sid, data in _sessions.items():
            dist = haversine(float(lat), float(lon), data['lat'], data['lon'])
            if dist <= radius_km:
                results.append(sid)
        return results

def push(session_id, event_dict):
    """Push an event payload to a session's SSE queue."""
    with _lock:
        if session_id in _sessions:
            try:
                _sessions[session_id]['q'].put_nowait(event_dict)
                return True
            except queue.Full:
                pass
    return False

def get_queue(session_id):
    """Get the queue for a session. Creates one if not present."""
    with _lock:
        if session_id not in _sessions:
            _sessions[session_id] = {
                'lat': 28.6139,
                'lon': 77.2090,
                'last_seen': time.time(),
                'q': queue.Queue()
            }
        else:
            _sessions[session_id]['last_seen'] = time.time()
        return _sessions[session_id]['q']

def count():
    """Return count of active sessions."""
    with _lock:
        _cleanup_stale_locked()
        return len(_sessions)

def all_sessions():
    """Return summary list of all active sessions."""
    with _lock:
        _cleanup_stale_locked()
        return [
            {
                'session_id': sid,
                'lat': data['lat'],
                'lon': data['lon'],
                'last_seen': data['last_seen']
            }
            for sid, data in _sessions.items()
        ]
