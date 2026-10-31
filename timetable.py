"""Timetable detection from event data.

Uses gap detection to identify phase transitions:
- 7-hour gaps in data collection mark phase boundaries
- Flat period in guild points identifies the interlude
- Data points are assigned to phases and min/max timestamps are used as start/end
"""
import sqlite3
import traceback

from config import DB_FILE
from database import log_debug

# Highest ranks for accurate timetable detection
HIGHEST_GUILD_RANK = "300"
HIGHEST_USER_RANK = "2000"

# Minimum gap duration to consider as phase transition (2 hours)
GAP_THRESHOLD = 7200

# Minimum flat period duration to identify interlude (1 hour)
FLAT_THRESHOLD = 3600


def detect_event_timetable(teamraidid, fetch_type="guild", rank=None):
    """Detects the event timetable by analyzing gaps in the time-series data.
    
    Phase transitions are marked by gaps in data collection.
    The interlude is identified by a flat period in guild points.
    Data points are assigned to phases; min/max timestamps per phase are used as start/end.
    """
    if rank is None:
        rank = HIGHEST_GUILD_RANK if fetch_type == "guild" else HIGHEST_USER_RANK
    
    log_debug(f"=== detect_event_timetable STARTED === (teamraidid={teamraidid}, type={fetch_type}, rank={rank})")
    
    try:
        # Always use guild data for detection (has clear interlude signal via flat points)
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT updatetime, point 
                FROM event_records 
                WHERE teamraidid = ? AND type = 'guild' AND rank = ?
                ORDER BY updatetime ASC
            """, (teamraidid, HIGHEST_GUILD_RANK))
            records = cursor.fetchall()
        
        if not records:
            log_debug("No guild records found for timetable detection.")
            return None
        
        timestamps = [r[0] for r in records]
        points = [r[1] for r in records]
        
        # Find gaps > 2 hours (phase transitions)
        gaps = []
        for i in range(len(timestamps) - 1):
            gap = timestamps[i + 1] - timestamps[i]
            if gap > GAP_THRESHOLD:
                gaps.append((timestamps[i], timestamps[i + 1]))
        
        log_debug(f"Found {len(gaps)} phase-transition gaps: {gaps}")
        
        # Find interlude: flat period in guild data after first gap
        interlude_start = None
        interlude_end = None
        
        if len(gaps) >= 1:
            first_gap_end = gaps[0][1]
            # Find first index after the gap
            start_idx = None
            for i, ts in enumerate(timestamps):
                if ts >= first_gap_end:
                    start_idx = i
                    break
            
            if start_idx is not None:
                # Scan for flat period (points not changing)
                flat_start_ts = None
                flat_end_ts = None
                for i in range(start_idx, len(points) - 1):
                    if points[i] == points[i + 1]:
                        if flat_start_ts is None:
                            flat_start_ts = timestamps[i]
                        flat_end_ts = timestamps[i + 1]
                    else:
                        if flat_start_ts is not None and (flat_end_ts - flat_start_ts) >= FLAT_THRESHOLD:
                            interlude_start = flat_start_ts
                            interlude_end = timestamps[i]  # point where rising starts
                            break
                        flat_start_ts = None
                        flat_end_ts = None
        
        log_debug(f"Interlude: {interlude_start} -> {interlude_end}")
        
        # Define phase boundary timestamps from gaps
        prelim_end = gaps[0][0] if len(gaps) >= 1 else timestamps[-1]
        finals_1_end = gaps[1][0] if len(gaps) >= 2 else None
        finals_2_end = gaps[2][0] if len(gaps) >= 3 else None
        finals_3_end = gaps[3][0] if len(gaps) >= 4 else None
        
        # Assign each data point to a phase
        phase_points = {
            'preliminaries': [],
            'interlude': [],
            'finals_1': [],
            'finals_2': [],
            'finals_3': [],
            'finals_4': [],
        }
        
        for ts, point in records:
            if ts <= prelim_end:
                phase_points['preliminaries'].append(ts)
            elif interlude_start is not None and ts <= interlude_end:
                phase_points['interlude'].append(ts)
            elif finals_1_end is not None and ts <= finals_1_end:
                phase_points['finals_1'].append(ts)
            elif finals_2_end is not None and ts <= finals_2_end:
                phase_points['finals_2'].append(ts)
            elif finals_3_end is not None and ts <= finals_3_end:
                phase_points['finals_3'].append(ts)
            else:
                phase_points['finals_4'].append(ts)
        
        # Build timetable using min/max of assigned points per phase
        timetable = {
            "teamraidid": teamraidid,
            "event_start": timestamps[0],
            "preliminary_end": None,
            "preliminary_totals_start": None,
            "preliminary_totals_end": None,
            "interlude_start": None,
            "interlude_end": None,
            "finals_1_start": None,
            "finals_1_end": None,
            "finals_2_start": None,
            "finals_2_end": None,
            "finals_3_start": None,
            "finals_3_end": None,
            "finals_4_start": None,
            "finals_4_end": None,
            "final_rally_start": None,
            "final_rally_end": timestamps[-1],
        }
        
        # Map phase keys to timetable field names
        phase_field_map = [
            ('preliminaries', 'preliminary_end'),  # only end; start is event_start
            ('interlude', 'interlude_start', 'interlude_end'),
            ('finals_1', 'finals_1_start', 'finals_1_end'),
            ('finals_2', 'finals_2_start', 'finals_2_end'),
            ('finals_3', 'finals_3_start', 'finals_3_end'),
            ('finals_4', 'finals_4_start', 'finals_4_end'),
        ]
        
        for phase_key, *fields in phase_field_map:
            pts = phase_points.get(phase_key, [])
            if pts:
                if len(fields) == 1:
                    # Only end field (preliminaries)
                    timetable[fields[0]] = max(pts)
                else:
                    # Start and end fields
                    timetable[fields[0]] = min(pts)
                    timetable[fields[1]] = max(pts)
        
        log_debug(f"Detected timetable: {timetable}")
        return timetable
        
    except Exception as e:
        log_debug(f"Error detecting timetable: {e}")
        traceback.print_exc()
        return None
    finally:
        log_debug("=== detect_event_timetable FINISHED ===")