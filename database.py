"""Database operations for the GW Tracker app."""
import sqlite3
import traceback
import json
import os
from itertools import groupby

from config import DB_FILE

def log_debug(msg):
    """Write debug messages to a log file."""
    with open("debug_log.txt", "a") as f:
        from datetime import datetime
        f.write(f"{datetime.now()} - {msg}\n")
    print(msg, flush=True)

def init_db():
    """Creates local SQLite tables to store raw data and records."""
    log_debug("Initializing database...")
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            
            # Table for raw API responses
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS raw_responses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    teamraidid TEXT,
                    type TEXT,
                    rank TEXT,
                    raw_json TEXT
                )
            ''')
            
            # Table for individual records with unique combined key
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS event_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    teamraidid TEXT,
                    type TEXT,
                    rank TEXT,
                    updatetime INTEGER,
                    point INTEGER,
                    UNIQUE(teamraidid, type, rank, updatetime)
                )
            ''')
            
            # Table for event timing information
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS event_info (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    teamraidid TEXT UNIQUE,
                    event_start INTEGER,
                    preliminary_end INTEGER,
                    interlude_start INTEGER,
                    interlude_end INTEGER,
                    finals_1_start INTEGER,
                    finals_1_end INTEGER,
                    finals_2_start INTEGER,
                    finals_2_end INTEGER,
                    finals_3_start INTEGER,
                    finals_3_end INTEGER,
                    finals_4_start INTEGER,
                    finals_4_end INTEGER,
                    preliminary_duration INTEGER,
                    interlude_duration INTEGER,
                    finals_1_duration INTEGER,
                    finals_2_duration INTEGER,
                    finals_3_duration INTEGER,
                    finals_4_duration INTEGER
                )
            ''')
            
            # Table for wiki chart data xy pairs
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS wiki_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    teamraidid TEXT,
                    type TEXT,
                    rank TEXT,
                    event_time INTEGER,
                    points INTEGER,
                    UNIQUE(teamraidid, type, rank, event_time)
                )
            ''')

            # Migrate legacy column names
            try:
                cols = [r[1] for r in cursor.execute("PRAGMA table_info(wiki_data)").fetchall()]
                if "x" in cols and "event_time" not in cols:
                    cursor.execute("ALTER TABLE wiki_data RENAME COLUMN x TO event_time")
                if "y" in cols and "points" not in cols:
                    cursor.execute("ALTER TABLE wiki_data RENAME COLUMN y TO points")
            except Exception:
                pass

            # Table for point accumulation calculations
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS point_accumulation (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    teamraidid TEXT,
                    type TEXT,
                    rank TEXT,
                    phase INTEGER,
                    event_time INTEGER,
                    points INTEGER,
                    phase_points INTEGER,
                    point_increase INTEGER,
                    phase_percentage REAL,
                    total_percentage REAL,
                    phase_time_percentage REAL,
                    event_time_percentage REAL,
                    UNIQUE(teamraidid, type, rank, event_time)
                )
            ''')
            
            conn.commit()
            log_debug("Database initialized successfully.")

    except Exception as e:
        log_debug(f"Database init error: {e}")
        traceback.print_exc()

def save_raw_response(teamraidid, fetch_type, rank, raw_json):
    """Saves a raw API response to the database."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO raw_responses (teamraidid, type, rank, raw_json) VALUES (?, ?, ?, ?)",
                (teamraidid, fetch_type, rank, raw_json)
            )
            conn.commit()
        return True
    except Exception as e:
        log_debug(f"Error saving raw response: {e}")
        traceback.print_exc()
        return False

def save_event_records(teamraidid, fetch_type, rank, data_list):
    """Saves individual event records to the database."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            for entry in data_list:
                updatetime = entry.get("updatetime", 0)
                point = entry.get("point", 0)
                cursor.execute(
                    "INSERT OR IGNORE INTO event_records (teamraidid, type, rank, updatetime, point) VALUES (?, ?, ?, ?, ?)",
                    (teamraidid, fetch_type, rank, updatetime, point)
                )
            conn.commit()
        return True
    except Exception as e:
        log_debug(f"Error saving event records: {e}")
        traceback.print_exc()
        return False


def save_normalized_records(teamraidid, fetch_type, rank, data_list):
    """Saves normalized records (time relative to event_start) to the database."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            
            # Get event_start for this teamraidid
            cursor.execute("SELECT event_start FROM event_info WHERE teamraidid = ?", (teamraidid,))
            row = cursor.fetchone()
            event_start = row[0] if row else None
            
            if not data_list:
                return True
            
            # Find the first data point's normalized time
            first_updatetime = data_list[0].get("updatetime", 0)
            first_normalized = first_updatetime - event_start if event_start else first_updatetime
            
            # Add a 0-point 20 minutes before the first data point
            zero_time = first_normalized - 1200
            cursor.execute(
                "INSERT OR IGNORE INTO normalized_records (teamraidid, type, rank, normalized_time, point) VALUES (?, ?, ?, ?, 0)",
                (teamraidid, fetch_type, rank, zero_time)
            )
            
            for entry in data_list:
                updatetime = entry.get("updatetime", 0)
                point = entry.get("point", 0)
                normalized_time = updatetime - event_start if event_start else updatetime
                cursor.execute(
                    "INSERT OR IGNORE INTO normalized_records (teamraidid, type, rank, normalized_time, point) VALUES (?, ?, ?, ?, ?)",
                    (teamraidid, fetch_type, rank, normalized_time, point)
                )
            conn.commit()
        return True
    except Exception as e:
        log_debug(f"Error saving normalized records: {e}")
        traceback.print_exc()
        return False

def get_event_records(teamraidid, fetch_type, rank):
    """Retrieves event records for a specific teamraidid, type, and rank."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT updatetime, point 
                FROM event_records 
                WHERE teamraidid = ? AND type = ? AND rank = ?
                ORDER BY updatetime ASC
            """, (teamraidid, fetch_type, rank))
            return cursor.fetchall()
    except Exception as e:
        log_debug(f"Error getting event records: {e}")
        traceback.print_exc()
        return []

def get_latest_raw_json():
    """Retrieves the most recent raw JSON response."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT raw_json FROM raw_responses ORDER BY timestamp DESC LIMIT 1")
            result = cursor.fetchone()
            return result["raw_json"] if result else None
    except Exception as e:
        log_debug(f"Error getting latest raw JSON: {e}")
        traceback.print_exc()
        return None

def get_historical_records(limit=20):
    """Retrieves the most recent historical records."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT teamraidid, type, rank, updatetime, point 
                FROM event_records 
                ORDER BY updatetime DESC 
                LIMIT ?
            """, (limit,))
            return cursor.fetchall()
    except Exception as e:
        log_debug(f"Error getting historical records: {e}")
        traceback.print_exc()
        return []

def update_event_info(teamraidid, **kwargs):
    """Updates or inserts event info for a specific teamraidid."""
    log_debug(f"=== update_event_info STARTED === (teamraidid={teamraidid})")
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            
            # Check if record exists
            cursor.execute("SELECT id FROM event_info WHERE teamraidid = ?", (teamraidid,))
            existing = cursor.fetchone()
            
            # Build the SQL based on provided fields
            fields = {"teamraidid": teamraidid}
            for key, value in kwargs.items():
                if value is not None:
                    fields[key] = value
            
            # Calculate durations if start and end times are provided
            # Note: preliminary_duration uses event_start and preliminary_end
            duration_fields = {
                "preliminary_duration": ("event_start", "preliminary_end"),
                "interlude_duration": ("interlude_start", "interlude_end"),
                "finals_1_duration": ("finals_1_start", "finals_1_end"),
                "finals_2_duration": ("finals_2_start", "finals_2_end"),
                "finals_3_duration": ("finals_3_start", "finals_3_end"),
                "finals_4_duration": ("finals_4_start", "finals_4_end"),
            }
            
            for duration_field, (start_field, end_field) in duration_fields.items():
                start = kwargs.get(start_field)
                end = kwargs.get(end_field)
                if start is not None and end is not None:
                    fields[duration_field] = end - start
            
            if existing:
                # Update existing record (don't update teamraidid)
                fields.pop("teamraidid", None)
                set_clause = ", ".join([f"{k} = ?" for k in fields.keys()])
                values = list(fields.values())
                values.append(teamraidid)
                cursor.execute(f"UPDATE event_info SET {set_clause} WHERE teamraidid = ?", values)
            else:
                # Insert new record
                columns = ", ".join(fields.keys())
                placeholders = ", ".join(["?" for _ in fields.keys()])
                values = list(fields.values())
                cursor.execute(f"INSERT INTO event_info ({columns}) VALUES ({placeholders})", values)
            
            conn.commit()
        log_debug("Event info updated successfully.")
    except Exception as e:
        log_debug(f"Error updating event info: {e}")
        traceback.print_exc()
    finally:
        log_debug("=== update_event_info FINISHED ===")

def save_wiki_data(teamraidid, rows):
    """Saves wiki chart xy pairs. rows: list of (type, rank, x, y)."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            for typ, rank, x, y in rows:
                cursor.execute(
                    "INSERT OR IGNORE INTO wiki_data (teamraidid, type, rank, event_time, points) VALUES (?, ?, ?, ?, ?)",
                    (teamraidid, typ, rank, int(x), int(y)),
                )
            conn.commit()
        return True
    except Exception as e:
        log_debug(f"Error saving wiki data: {e}")
        traceback.print_exc()
        return False


def get_wiki_data(teamraidid=None):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if teamraidid:
                cursor.execute("SELECT * FROM wiki_data WHERE teamraidid=? ORDER BY type,rank,event_time", (teamraidid,))
            else:
                cursor.execute("SELECT * FROM wiki_data ORDER BY teamraidid,type,rank,event_time")
            return cursor.fetchall()
    except Exception as e:
        log_debug(f"Error getting wiki data: {e}")
        traceback.print_exc()
        return []



def get_all_event_info():
    """Retrieves all event info records."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM event_info ORDER BY teamraidid")
            return cursor.fetchall()
    except Exception as e:
        log_debug(f"Error getting event info: {e}")
        traceback.print_exc()
        return []




def _phase_for_event_time(et, intervals):
    checks = [
        ("Preliminaries_end", 1),
        ("Interlude_end", 2),
        ("Finals_1_end", 3),
        ("Finals_2_end", 4),
        ("Finals_3_end", 5),
        ("Finals_4_end", 6),
    ]
    for key, num in checks:
        if et <= intervals.get(key, float("inf")):
            return num
    return 6


def create_point_accumulations():
    try:
        with open(os.path.join(os.path.dirname(__file__), "intervals.json")) as f:
            intervals = json.load(f)
    except Exception:
        intervals = {}

    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM point_accumulation")
            
            rows = cursor.execute(
                """SELECT teamraidid, type, rank, event_time, points 
                   FROM wiki_data 
                   ORDER BY teamraidid, type, rank, event_time"""
            ).fetchall()
            
            # Group rows by tracking keys
            groups = {}
            for trid, typ, rank, et, pts in rows:
                groups.setdefault((trid, typ, rank), []).append((et, pts))
                
            for (trid, typ, rank), series in groups.items():
                log_debug(f"trid={trid}, typ={typ}, rank={rank}")
                if not series:
                    continue
                
                phase_time_bounds = {
                    1: (intervals.get("Preliminaries_start", 0), intervals.get("Preliminaries_end", 104340)),
                    2: (intervals.get("Interlude_start", 129600), intervals.get("Interlude_end", 215999)),
                    3: (intervals.get("Finals_1_start", 216000), intervals.get("Finals_1_end", 277140)),
                    4: (intervals.get("Finals_2_start", 302400), intervals.get("Finals_2_end", 363540)),
                    5: (intervals.get("Finals_3_start", 388800), intervals.get("Finals_3_end", 449940)),
                    6: (intervals.get("Finals_4_start", 475200), intervals.get("Finals_4_end", 536340)),
                }

                # Global scale values
                series_total = series[-1][-1] or 1
                log_debug(f"series_total {series_total}")
                
                global_max_time = intervals.get("Finals_4_end", 536340) or 1
                
                phase_groups = groupby(series, key=lambda x: _phase_for_event_time(x[0], intervals))
                prev_pts = 0

                for phase, phase_entries in phase_groups:
                    phase_list = list(phase_entries)  
                    
                    # 1. Determine baseline/starting points prior to this phase
                    first_et_of_phase = phase_list[0][0]
                    prior_entries = [p for et, p in series if et < first_et_of_phase]
                    phase_baseline_points = prior_entries[-1] if prior_entries else 0
                    
                    # 2. Extract maximum points inside this specific phase data window
                    max_phase_points = max(p for _, p in phase_list)
                    phase_denominator = (max_phase_points - phase_baseline_points) if (max_phase_points - phase_baseline_points) > 0 else 1
                    
                    # 3. Pull fixed time boundaries for this phase
                    p_start, p_end = phase_time_bounds.get(phase, (0, 1))
                    phase_duration = (p_end - p_start) if (p_end - p_start) > 0 else 1

                    # 4. Process and insert each point inside the phase boundary
                    for et, pts in phase_list:
                        phase_points = pts - phase_baseline_points
                        
                        # Calculate progress inside the fixed window bounds
                        # Clips at 0.0 or 1.0 if any stray log ticks fall right outside standard bounds
                        elapsed_phase_time = max(0, et - p_start)
                        phase_time_pct = min(1.0, elapsed_phase_time / phase_duration)
                        point_increase = pts - prev_pts
                        prev_pts = pts
                        
                        cursor.execute(
                            """INSERT OR REPLACE INTO point_accumulation
                            (teamraidid, type, rank, phase, event_time, points,
                             phase_points, point_increase, phase_percentage,
                             total_percentage, phase_time_percentage, event_time_percentage)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                trid, typ, rank, phase, et, pts,
                                phase_points, 
                                point_increase,  
                                phase_points / phase_denominator, 
                                pts / series_total,
                                phase_time_pct,              
                                min(1.0, et / global_max_time) 
                            ),
                        )

            conn.commit()
        return True
    except Exception as e:
        log_debug(f"Error creating point accumulations: {e}")
        traceback.print_exc()
        return False
