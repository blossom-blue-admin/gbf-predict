"""Local cache for API responses to prevent repeated API calls during development."""
import os
import json
import time

CACHE_DIR = "api_cache"
CACHE_EXPIRY = 48 * 60 * 60  # 48 hours in seconds

def _ensure_cache_dir():
    """Ensures the cache directory exists."""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)

def _get_cache_key(teamraidid, fetch_type, rank):
    """Generates a cache key for the given parameters."""
    return f"{teamraidid}_{fetch_type}_{rank}.json"

def _get_cache_path(teamraidid, fetch_type, rank):
    """Gets the cache file path for the given parameters."""
    _ensure_cache_dir()
    return os.path.join(CACHE_DIR, _get_cache_key(teamraidid, fetch_type, rank))

def get_cached_response(teamraidid, fetch_type, rank):
    """Retrieves a cached API response if it exists and is not expired."""
    cache_path = _get_cache_path(teamraidid, fetch_type, rank)
    
    if not os.path.exists(cache_path):
        return None
    
    try:
        with open(cache_path, "r") as f:
            cached = json.load(f)
        
        # Check if cache is expired
        if time.time() - cached.get("timestamp", 0) > CACHE_EXPIRY:
            log_debug(f"Cache expired for {teamraidid}/{fetch_type}/{rank}")
            os.remove(cache_path)
            return None
        
        log_debug(f"Cache hit for {teamraidid}/{fetch_type}/{rank}")
        return cached.get("data")
    except Exception as e:
        log_debug(f"Error reading cache: {e}")
        return None

def save_cached_response(teamraidid, fetch_type, rank, data):
    """Saves an API response to the cache."""
    cache_path = _get_cache_path(teamraidid, fetch_type, rank)
    
    try:
        _ensure_cache_dir()
        cached = {
            "timestamp": time.time(),
            "teamraidid": teamraidid,
            "type": fetch_type,
            "rank": rank,
            "data": data
        }
        with open(cache_path, "w") as f:
            json.dump(cached, f)
        log_debug(f"Cached response for {teamraidid}/{fetch_type}/{rank}")
    except Exception as e:
        log_debug(f"Error saving cache: {e}")

def clear_cache():
    """Clears all cached responses."""
    _ensure_cache_dir()
    try:
        for filename in os.listdir(CACHE_DIR):
            if filename.endswith(".json"):
                os.remove(os.path.join(CACHE_DIR, filename))
        log_debug("Cache cleared")
    except Exception as e:
        log_debug(f"Error clearing cache: {e}")

def log_debug(msg):
    """Write debug messages to a log file."""
    with open("debug_log.txt", "a") as f:
        from datetime import datetime
        f.write(f"{datetime.now()} - {msg}\n")
    print(msg, flush=True)