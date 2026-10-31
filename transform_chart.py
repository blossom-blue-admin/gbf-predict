#!/usr/bin/env python3
"""Transform wiki_data chartDataX/chartDataY into identified xy pairs."""
import argparse
import re
import sys


def parse_series(body):
    """Return dict type -> {rank: [values]} from a chartData body."""
    out = {}
    for m in re.finditer(r"\|(crew|indiv)=\{\{#switch: \{\{\{2\}\}\}(.*?)\}\}", body, re.S):
        typ = m.group(1)
        block = m.group(2)
        ranks = {}
        for rm in re.finditer(r"\|(\w+)=([0-9][0-9,]*)", block):
            rank = rm.group(1)
            vals = [v.strip() for v in rm.group(2).split(",") if v.strip()]
            ranks[rank] = vals
        out[typ] = ranks
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--file", required=True)
    p.add_argument("--sep", default=",")
    args = p.parse_args()

    text = open(args.file).read()
    mx = re.search(r"chartDataX=(.*?)(?=\|\s*chartDataY=)", text, re.S)
    my = re.search(r"chartDataY=(.*)", text, re.S)
    x_body = mx.group(1) if mx else ""
    y_body = my.group(1) if my else ""

    xs = parse_series(x_body)
    ys = parse_series(y_body)

    for typ in xs:
        for rank in xs[typ]:
            xvals = xs[typ][rank]
            yvals = ys.get(typ, {}).get(rank, [])
            if len(xvals) != len(yvals):
                print(f"# skip {typ}/{rank}: len {len(xvals)} vs {len(yvals)}", file=sys.stderr)
                continue
            for x, y in zip(xvals, yvals):
                print(args.sep.join([typ, rank, x, y]))


if __name__ == "__main__":
    main()