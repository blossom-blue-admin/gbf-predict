#!/usr/bin/env python3
"""Load wiki_data/*.txt chart data into the database."""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import init_db, save_wiki_data
from transform_chart import parse_series
import re


def main():
    init_db()
    for path in sorted(glob.glob(os.path.join("wiki_data", "*.txt"))):
        teamraidid = os.path.splitext(os.path.basename(path))[0]
        text = open(path).read()
        mx = re.search(r"chartDataX=(.*?)(?=\|\s*chartDataY=)", text, re.S)
        my = re.search(r"chartDataY=(.*)", text, re.S)
        xs = parse_series(mx.group(1) if mx else "")
        ys = parse_series(my.group(1) if my else "")
        rows = []
        for typ in xs:
            for rank in xs[typ]:
                for x, y in zip(xs[typ][rank], ys.get(typ, {}).get(rank, [])):
                    rows.append((typ, rank, x, y))
        save_wiki_data(teamraidid, rows)
        print(f"{teamraidid}: {len(rows)} rows")


if __name__ == "__main__":
    main()