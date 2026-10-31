"""API operations for fetching data from gbf.pub."""
import requests
import traceback

from config import API_BASE_URL
from database import log_debug, save_raw_response, save_event_records, save_normalized_records, get_all_event_info, update_event_info
from timetable import detect_event_timetable
from cache import get_cached_response, save_cached_response

def fetch_data(teamraidid, fetch_type, rank):
    """Fetches data from the API and saves it to the database.
    
    Uses local cache to prevent repeated API calls during development.
    """
    log_debug(f"=== fetch_data STARTED === (teamraidid={teamraidid}, rank={rank}, type={fetch_type})")
    
    # Check cache first
    cached_data = get_cached_response(teamraidid, fetch_type, rank)
    if cached_data:
        log_debug("Using cached response")
        response_text = cached_data.get("raw_text", "")
        data_list = cached_data.get("data", [])
    else:
        params = {
            "teamraidid": teamraidid,
            "type": fetch_type,
            "rank": rank
        }
        
        try:
            log_debug(f"Fetching URL: {API_BASE_URL} with params: {params}")
            response = requests.get(API_BASE_URL, params=params, timeout=10)
            # Dump raw response to file for troubleshooting
            with open("debug_response.txt", "w") as f:
                f.write(f"URL: {response.url}\n")
                f.write(f"Status: {response.status_code}\n")
                f.write(f"Headers: {dict(response.headers)}\n")
                f.write("---BODY---\n")
                f.write(response.text)
            log_debug(f"Response status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    log_debug(f"Parsed JSON keys: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
                    
                    # API returns: {"message":"","type":"success","data":[{"point":...,"updatetime":...,"rank":...}, ...]}
                    data_list = data.get("data", [])
                    response_text = response.text
                    
                    # Save to cache
                    save_cached_response(teamraidid, fetch_type, rank, {
                        "raw_text": response_text,
                        "data": data_list
                    })
                except Exception as json_err:
                    log_debug(f"JSON parsing error: {json_err}")
                    traceback.print_exc()
                    return False, 0
            else:
                log_debug(f"Failed connection attempt. Status: {response.status_code}")
                return False, 0
        except requests.exceptions.ConnectionError as ce:
            log_debug(f"Connection error: {ce}")
            traceback.print_exc()
            return False, 0
        except requests.exceptions.Timeout as te:
            log_debug(f"Timeout error: {te}")
            traceback.print_exc()
            return False, 0
        except Exception as e:
            log_debug(f"Scheduler Exception caught: {str(e)}")
            traceback.print_exc()
            return False, 0
    
    # Process the data (from cache or fresh API response)
    if data_list:
        # Get the latest entry (last in the array)
        latest = data_list[-1]
        points = latest.get("point", 0)
        log_debug(f"Extracted points (latest entry): {points}")
        
        # Save raw response to database
        save_raw_response(teamraidid, fetch_type, rank, response_text)
        log_debug("Raw response saved successfully.")
        
        # Save individual records to event_records table
        save_event_records(teamraidid, fetch_type, rank, data_list)
        log_debug(f"Saved {len(data_list)} records to event_records table.")
        
        # Save normalized records (time relative to event_start)
        save_normalized_records(teamraidid, fetch_type, rank, data_list)
        log_debug(f"Saved {len(data_list)} records to normalized_records table.")
        
        # Generate event timetable if it does not exist
        _ensure_event_timetable(teamraidid)
        
        return True, points
    else:
        log_debug("No data entries found in response.")
        return False, 0

def _ensure_event_timetable(teamraidid):
    """Ensures event timetable exists for a teamraidid by detecting from data."""
    log_debug(f"=== _ensure_event_timetable STARTED === (teamraidid={teamraidid})")
    try:
        # Check if event_info already exists
        existing_events = get_all_event_info()
        existing_teamraidids = {e["teamraidid"] for e in existing_events}
        
        if teamraidid in existing_teamraidids:
            log_debug(f"Event info already exists for {teamraidid}, skipping timetable generation.")
            return
        
        # Detect timetable from guild data
        timetable = detect_event_timetable(teamraidid, fetch_type="guild", rank="300")
        if timetable:
            # Save detected timetable to event_info
            update_event_info(
                teamraidid,
                event_start=timetable.get("event_start"),
                preliminary_end=timetable.get("preliminary_end"),
                interlude_start=timetable.get("interlude_start"),
                interlude_end=timetable.get("interlude_end"),
                finals_1_start=timetable.get("finals_1_start"),
                finals_1_end=timetable.get("finals_1_end"),
                finals_2_start=timetable.get("finals_2_start"),
                finals_2_end=timetable.get("finals_2_end"),
                finals_3_start=timetable.get("finals_3_start"),
                finals_3_end=timetable.get("finals_3_end"),
                finals_4_start=timetable.get("finals_4_start"),
                finals_4_end=timetable.get("finals_4_end"),
            )
            log_debug(f"Event timetable generated and saved for {teamraidid}.")
        else:
            log_debug(f"Could not detect timetable for {teamraidid}.")
    except Exception as e:
        log_debug(f"Error ensuring event timetable: {e}")
        traceback.print_exc()
    finally:
        log_debug("=== _ensure_event_timetable FINISHED ===")

def scheduled_fetch_job(teamraidid="teamraid084", event_label="84 (Light advantage)", rank="300", fetch_type="user"):
    """Wrapper function for scheduled fetch job."""
    return fetch_data(teamraidid, fetch_type, rank)

def refresh_all_records():
    """Fetches data for all combinations of teamraidid, type, and rank from data-map.json."""
    log_debug("=== refresh_all_records STARTED ===")
    from config import DATA_MAP_FILE
    import json
    import os
    
    config = load_history()
    
    if not config:
        log_debug("ERROR: No config loaded, cannot refresh all records.")
        return
    
    teamraidid_map = config.get("teamraidid", {})
    type_map = config.get("type", {})
    
    total_combinations = 0
    success_count = 0
    
    for event_label, teamraidid in teamraidid_map.items():
        for type_label, ranks in type_map.items():
            for rank_label, rank_value in ranks.items():
                total_combinations += 1
                log_debug(f"Fetching: teamraidid={teamraidid}, type={type_label}, rank={rank_value} ({event_label})")
                try:
                    success, _ = fetch_data(teamraidid, type_label, rank_value)
                    if success:
                        success_count += 1
                except Exception as e:
                    log_debug(f"Error fetching {teamraidid}/{type_label}/{rank_value}: {e}")
                    traceback.print_exc()
    
    log_debug(f"=== refresh_all_records FINISHED === (success: {success_count}/{total_combinations})")

def load_history():
    """Loads the variations defined in data-map.json."""
    from config import DATA_MAP_FILE
    import json
    import os
    
    log_debug("Loading history from data-map.json...")
    if not os.path.exists(DATA_MAP_FILE):
        log_debug(f"ERROR: {DATA_MAP_FILE} not found.")
        return {}
    
    try:
        with open(DATA_MAP_FILE, "r") as f:
            config = json.load(f)
        log_debug(f"Loaded config: {json.dumps(config, indent=2)}")
        return config
    except Exception as e:
        log_debug(f"Error loading {DATA_MAP_FILE}: {e}")
        traceback.print_exc()
        return {}