import sqlite3
from flask import Flask, render_template, request, redirect, url_for
from apscheduler.schedulers.background import BackgroundScheduler

from config import DB_FILE
from database import init_db, get_latest_raw_json, get_historical_records, get_all_event_info, update_event_info
from api import scheduled_fetch_job, refresh_all_records, load_history
from timetable import detect_event_timetable

import subprocess
import sys

app = Flask(__name__)

# Initialize database and load config
init_db()
config = load_history()

# Scheduler setup
scheduler = BackgroundScheduler()
scheduler.start()


def get_normalized_data(teamraidid, fetch_type, rank):
    """Get normalized data for a specific series."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT normalized_time, point 
                FROM normalized_records 
                WHERE teamraidid = ? AND type = ? AND rank = ?
                ORDER BY normalized_time ASC
            """, (teamraidid, fetch_type, rank))
            return cursor.fetchall()
    except Exception as e:
        print(f"Error getting normalized data: {e}")
        return []


def get_all_normalized_data():
    """Get all normalized data for chart display."""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT teamraidid, type, rank, normalized_time, point 
                FROM normalized_records 
                ORDER BY teamraidid, type, rank, normalized_time ASC
            """)
            return cursor.fetchall()
    except Exception as e:
        print(f"Error getting all normalized data: {e}")
        return []


@app.route("/")
def show_dashboard():
    """Reads stored timelines from database and renders them."""
    latest_raw = get_latest_raw_json()
    historical_records = get_historical_records(limit=20)
    
    # Get all normalized data for the chart
    all_data = get_all_normalized_data()
    
    # Group by series
    series_map = {}
    for row in all_data:
        key = f"{row['teamraidid']}_{row['type']}_rank{row['rank']}"
        if key not in series_map:
            series_map[key] = {
                'teamraidid': row['teamraidid'],
                'type': row['type'],
                'rank': row['rank'],
                'data': []
            }
        series_map[key]['data'].append({
            'time': row['normalized_time'],
            'point': row['point']
        })
    
    return render_template("index.html", 
                          records=historical_records, 
                          config=config,
                           series_list=list(series_map.values()),
                           chart_data=list(series_map.values()))


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/fetch/<event_label>/<type>/<rank>")
def fetch_variation(event_label, type, rank):
    """Fetch data for a specific variation from data-map.json."""
    config = load_history()
    teamraidid = config.get("teamraidid", {}).get(event_label, "teamraid084")
    scheduled_fetch_job(teamraidid=teamraidid, event_label=event_label, rank=rank, fetch_type=type)
    return redirect(url_for("show_dashboard"))


@app.route("/admin/refresh")
def admin_refresh():
    """Refreshes all records from data-map.json."""
    refresh_all_records()
    return redirect(url_for("show_dashboard"))


@app.route("/admin/start")
def admin_start():
    """Starts the scheduler and performs initial fetch."""
    log_debug = lambda msg: print(msg, flush=True)
    log_debug("Performing initial fetch on startup...")
    scheduled_fetch_job(teamraidid="teamraid084", rank="300", fetch_type="user")
    scheduled_fetch_job(teamraidid="teamraid084", rank="300", fetch_type="guild")
    
    if not scheduler.running:
        scheduler.start()
    log_debug("Scheduler started successfully.")
    
    return redirect(url_for("show_dashboard"))


import os
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))

import json as _json

@app.route("/admin/settings", methods=["GET", "POST"])
def admin_settings():
    path = os.path.join(os.path.dirname(__file__), "intervals.json")
    if request.method == "POST":
        intervals = {}
        for key in ["Preliminaries_end","Interlude_start","Interlude_end","Finals_1_start","Finals_1_end","Finals_2_start","Finals_2_end","Finals_3_start","Finals_3_end","Finals_4_start","Finals_4_end"]:
            intervals[key] = int(request.form.get(key, 0))
        with open(path, "w") as f:
            _json.dump(intervals, f)
        return redirect(url_for("admin_settings"))
    with open(path) as f:
        intervals = _json.load(f)
    return render_template("admin_settings.html", intervals=intervals)

# inject intervals into nextevent
@app.route("/admin/nextevent", methods=["GET", "POST"])
def admin_nextevent():
    wiki_dir = os.path.join(os.path.dirname(__file__), "wiki_data")
    nums = []
    for f in os.listdir(wiki_dir):
        name, _ = os.path.splitext(f)
        if name.isdigit():
            nums.append(int(name))
    default_number = (max(nums) + 1) if nums else 1
    if request.method == "POST":
        event_number = request.form.get("event_number", default_number)
        teamraidid = f"teamraid{int(event_number):03d}"
        field_map = {
            "Preliminaries_start": "event_start",
            "Preliminaries_end": "preliminary_end",
            "Interlude_start": "interlude_start",
            "Interlude_end": "interlude_end",
            "Finals_1_start": "finals_1_start",
            "Finals_1_end": "finals_1_end",
            "Finals_2_start": "finals_2_start",
            "Finals_2_end": "finals_2_end",
            "Finals_3_start": "finals_3_start",
            "Finals_3_end": "finals_3_end",
            "Finals_4_start": "finals_4_start",
            "Finals_4_end": "finals_4_end",
        }
        kwargs = {}
        for form_key, db_key in field_map.items():
            val = request.form.get(form_key)
            if val:
                dt = datetime.fromisoformat(val).replace(tzinfo=JST)
                kwargs[db_key] = int(dt.timestamp())
        update_event_info(teamraidid, **kwargs)
        return redirect(url_for("admin_events"))
    with open(os.path.join(os.path.dirname(__file__), "intervals.json")) as f:
        intervals = _json.load(f)
    return render_template("admin_nextevent.html", default_number=default_number, intervals=intervals)
@app.route("/admin/events")
def admin_events():
    """Displays the event info management page."""
    events = get_all_event_info()
    
    detected_timetables = {}
    for event in events:
        teamraidid = event["teamraidid"]
        timetable = detect_event_timetable(teamraidid, fetch_type="guild", rank="300")
        if timetable:
            detected_timetables[teamraidid] = timetable
    
    return render_template("admin_events.html", events=events, config=config, detected=detected_timetables)


@app.route("/admin/events/update/<teamraidid>", methods=["POST"])
def update_event_info_route(teamraidid):
    """Updates event info for a specific teamraidid."""
    event_start = request.form.get("event_start", type=int)
    preliminary_end = request.form.get("preliminary_end", type=int)
    interlude_start = request.form.get("interlude_start", type=int)
    interlude_end = request.form.get("interlude_end", type=int)
    finals_1_start = request.form.get("finals_1_start", type=int)
    finals_1_end = request.form.get("finals_1_end", type=int)
    finals_2_start = request.form.get("finals_2_start", type=int)
    finals_2_end = request.form.get("finals_2_end", type=int)
    finals_3_start = request.form.get("finals_3_start", type=int)
    finals_3_end = request.form.get("finals_3_end", type=int)
    finals_4_start = request.form.get("finals_4_start", type=int)
    finals_4_end = request.form.get("finals_4_end", type=int)
    
    update_event_info(
        teamraidid,
        event_start=event_start,
        preliminary_end=preliminary_end,
        interlude_start=interlude_start,
        interlude_end=interlude_end,
        finals_1_start=finals_1_start,
        finals_1_end=finals_1_end,
        finals_2_start=finals_2_start,
        finals_2_end=finals_2_end,
        finals_3_start=finals_3_start,
        finals_3_end=finals_3_end,
        finals_4_start=finals_4_start,
        finals_4_end=finals_4_end,
    )
    
    return redirect(url_for("admin_events"))



@app.route("/admin/wiki_data")
def admin_wiki_data():
    return render_template("admin_wiki_data.html")

@app.route("/admin/wiki_data/load", methods=["POST"])
def admin_wiki_data_load():
    subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "load_wiki_data.py")], check=False)
    return redirect(url_for("admin_wiki_data"))

@app.route("/admin/wiki_data/process", methods=["POST"])
def admin_wiki_data_process():
    subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "process_wiki_data.py")], check=False)
    return redirect(url_for("admin_wiki_data"))

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)