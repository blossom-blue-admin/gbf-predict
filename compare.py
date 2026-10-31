import sqlite3
import math
from database import DB_FILE


def get_series(teamraidid, fetch_type, rank):
    tid = str(teamraidid).replace("teamraid", "")
    wtype = "crew" if fetch_type == "guild" else "indiv"
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT event_time, points FROM wiki_data WHERE teamraidid=? AND type=? AND rank=? ORDER BY event_time",
            (tid, wtype, rank),
        ).fetchall()
    return [(r["event_time"], r["points"]) for r in rows]


def series_similarity(a, b):
    mapb = {t: p for t, p in b}
    times = [t for t, _ in a if t in mapb]
    if len(times) < 3:
        return float("inf")
    va = [dict(a)[t] for t in times]
    vb = [mapb[t] for t in times]
    ma = sum(va)/len(va); mb = sum(vb)/len(vb)
    sa = math.sqrt(sum((x-ma)**2 for x in va)/len(va)) or 1
    sb = math.sqrt(sum((x-mb)**2 for x in vb)/len(vb)) or 1
    za = [(x-ma)/sa for x in va]
    zb = [(x-mb)/sb for x in vb]
    se = sum((x-y)**2 for x,y in zip(za,zb))
    return math.sqrt(se/len(times))


def best_fit_partial(target_trid, fetch_type, rank):
    target = get_series(target_trid, fetch_type, rank)
    if not target:
        return None
    with sqlite3.connect(DB_FILE) as conn:
        conn.row_factory = sqlite3.Row
        trids = [r[0] for r in conn.execute(
            "SELECT DISTINCT teamraidid FROM normalized_records WHERE type=? AND rank=?",
            (fetch_type, rank),
        ).fetchall()]
    best = None
    best_score = float("inf")
    for trid in trids:
        if trid == target_trid:
            continue
        cand = get_series(trid, fetch_type, rank)
        score = series_similarity(target, cand)
        if score < best_score:
            best_score = score
            best = trid
    return {"best_fit": best, "score": best_score}