#!/usr/bin/env python3
"""
scout.py — detect anomalous error-rate windows in application logs.

Method (deliberately simple and transparent):
  1. Bucket log lines into 5-minute windows per service.
  2. Compute the ERROR rate per bucket (buckets with < 5 lines are skipped
     to avoid noisy tiny samples).
  3. Flag a bucket as anomalous when its error rate exceeds
     max(mean + 3*sigma, floor=0.10), where mean/sigma are computed over that
     service's own buckets (per-service baseline).
  4. Merge consecutive flagged buckets on the same service into one event.

Core logic has zero dependencies. `--chart` is optional (needs matplotlib).

Usage:
    python scout.py logs/app.log             # print report
    python scout.py logs/app.log --eval       # + precision/recall vs ground truth
    python scout.py logs/app.log --chart      # + save PNG trend chart to charts/
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\s+(INFO|WARN|ERROR|DEBUG)\s+(\S+)\s+(.*)$"
)
BUCKET_MINUTES = 5
MIN_BUCKET_LINES = 5
Z_THRESHOLD = 3.0
RATE_FLOOR = 0.10


def bucket_start(ts: datetime) -> datetime:
    floored = ts.replace(second=0, microsecond=0)
    return floored - timedelta(minutes=floored.minute % BUCKET_MINUTES)


def parse(path: Path):
    """Parse log file into list of (timestamp, level, service, message)."""
    entries, skipped = [], 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            m = LINE_RE.match(line)
            if not m:
                skipped += 1
                continue
            ts = datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S")
            entries.append((ts, m.group(2), m.group(3), m.group(4)))
    return entries, skipped


def bucketize(entries):
    """Return {service: {bucket: [levels/messages]}}."""
    buckets = defaultdict(lambda: defaultdict(list))
    for ts, level, service, msg in entries:
        buckets[service][bucket_start(ts)].append((level, msg))
    return buckets


def mask_template(msg: str) -> str:
    """Mask run-specific ids so we can group by message template."""
    msg = re.sub(r"REQ-\d+", "REQ-#", msg)      # request ids
    msg = re.sub(r":(\d{2,5})\b", ":#", msg)    # ports
    msg = re.sub(r"\b\d{4,}\b", "#", msg)       # long numeric runs (latencies, counts)
    return msg


def detect(buckets):
    """Return (events, baselines).

    events: list of dicts with service, start, end, peak_rate, top_messages, likely_cause
    baselines: {service: {mean, std, threshold, n_buckets}}
    """
    events, baselines = [], {}
    for service, bmap in buckets.items():
        # skip low-volume buckets
        stats = []
        for b, rows in bmap.items():
            if len(rows) < MIN_BUCKET_LINES:
                continue
            errs = sum(1 for level, _ in rows if level == "ERROR")
            stats.append((b, errs / len(rows), errs))
        if not stats:
            continue
        rates = [r for _, r, _ in stats]
        mean = sum(rates) / len(rates)
        var = sum((r - mean) ** 2 for r in rates) / len(rates)
        std = math.sqrt(var)
        threshold = max(mean + Z_THRESHOLD * std, RATE_FLOOR)
        baselines[service] = {
            "mean": mean,
            "std": std,
            "threshold": threshold,
            "n_buckets": len(rates),
        }

        # a bucket needs enough volume AND enough errors to count as anomalous
        flagged = sorted(b for b, r, e in stats if r >= threshold and e >= 3)
        # merge strictly consecutive buckets
        runs, current = [], []
        for b in flagged:
            if current and b - current[-1] != timedelta(minutes=BUCKET_MINUTES):
                runs.append(current)
                current = []
            current.append(b)
        if current:
            runs.append(current)

        for run in runs:
            rows = []
            for b in run:
                rows.extend(bmap[b])
            errs = [(l, m) for l, m in rows if l == "ERROR"]
            peak = max(sum(1 for l, _ in bmap[b] if l == "ERROR") / len(bmap[b]) for b in run)
            top_msgs = [msg for msg, _ in Counter(m for _, m in errs).most_common(3)]
            likely = Counter(mask_template(m) for _, m in errs).most_common(1)
            events.append(
                {
                    "service": service,
                    "start": run[0],
                    "end": run[-1] + timedelta(minutes=BUCKET_MINUTES),
                    "peak_rate": peak,
                    "n_errors": len(errs),
                    "top_messages": top_msgs,
                    "likely_cause": likely[0][0] if likely else "",
                }
            )
    events.sort(key=lambda e: (e["start"], e["service"]))
    return events, baselines


def evaluate(events, ground_truth):
    """Window-level precision/recall against ground truth.

    A ground-truth window counts as detected if some event on the same service
    covers >= 50% of the window's duration. Each event can match at most one window.
    """
    truths = [
        {
            "service": g["service"],
            "start": datetime.strptime(g["start"], "%Y-%m-%dT%H:%M:%S"),
            "end": datetime.strptime(g["end"], "%Y-%m-%dT%H:%M:%S"),
            "label": g["label"],
        }
        for g in ground_truth
    ]
    used_events = set()
    hits = []
    for t in truths:
        best, best_cover = None, 0.0
        for i, e in enumerate(events):
            if i in used_events or e["service"] != t["service"]:
                continue
            overlap = max(
                timedelta(0),
                min(e["end"], t["end"]) - max(e["start"], t["start"]),
            ).total_seconds()
            cover = overlap / (t["end"] - t["start"]).total_seconds()
            if cover > best_cover:
                best, best_cover = i, cover
        if best_cover >= 0.5:
            used_events.add(best)
            hits.append((t["label"], best_cover))
    tp = len(hits)
    fp = len(events) - tp
    fn = len(truths) - tp
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "hits": hits,
    }


def fmt(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%d %H:%M")


def print_report(events, baselines, entries_count, skipped, eval_result=None):
    print("=" * 64)
    print("Log Anomaly Scout — report")
    print("=" * 64)
    print(f"lines parsed : {entries_count} (skipped {skipped} malformed)")
    print(f"services     : {', '.join(sorted(baselines))}")
    print(f"bucket size  : {BUCKET_MINUTES} min (min {MIN_BUCKET_LINES} lines/bucket)")
    print(f"events found : {len(events)}")
    print()
    for svc, b in sorted(baselines.items()):
        print(
            f"  [{svc}] baseline mean={b['mean']:.3f} std={b['std']:.3f} "
            f"threshold={b['threshold']:.3f} over {b['n_buckets']} buckets"
        )
    if not events:
        print("\nNo anomalies detected.")
    for i, e in enumerate(events, 1):
        print()
        print(f"--- Event {i}: {e['service']}  {fmt(e['start'])} -> {fmt(e['end'])} ---")
        print(f"peak error rate : {e['peak_rate']:.1%}  ({e['n_errors']} errors in window)")
        print(f"likely cause    : {e['likely_cause']}")
        print("top error messages:")
        for m in e["top_messages"]:
            print(f"  - {m}")
    if eval_result is not None:
        ev = eval_result
        print()
        print("-" * 64)
        print("Evaluation vs ground truth")
        print(
            f"precision={ev['precision']:.2f}  recall={ev['recall']:.2f}  "
            f"f1={ev['f1']:.2f}  (TP={ev['tp']} FP={ev['fp']} FN={ev['fn']})"
        )
        for label, cover in ev["hits"]:
            print(f"  hit: {label} (coverage {cover:.0%})")
    print()


def make_chart(events, baselines, buckets, log_path: Path):
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed — skipping chart (pip install matplotlib).")
        return
    services = sorted(buckets)
    n = len(services)
    fig, axes = plt.subplots(n, 1, figsize=(10, 2.8 * n), sharex=True)
    if n == 1:
        axes = [axes]
    for ax, svc in zip(axes, services):
        xs = sorted(buckets[svc])
        xs = [b for b in xs if len(buckets[svc][b]) >= MIN_BUCKET_LINES]
        rates = [sum(1 for l, _ in buckets[svc][b] if l == "ERROR") / len(buckets[svc][b]) for b in xs]
        ax.plot(xs, rates, marker="o", ms=3, label="error rate")
        thr = baselines[svc]["threshold"]
        ax.axhline(thr, color="red", ls="--", lw=1, label=f"threshold ({thr:.0%})")
        for e in events:
            if e["service"] == svc:
                ax.axvspan(e["start"], e["end"], color="red", alpha=0.15)
        ax.set_title(svc)
        ax.set_ylabel("error rate")
        ax.legend(loc="upper right", fontsize=8)
    fig.suptitle(f"Error-rate trends — {log_path.name}")
    fig.autofmt_xdate(rotation=20)
    out = Path(__file__).resolve().parent / "charts"
    out.mkdir(exist_ok=True)
    png = out / f"{log_path.stem}-trend.png"
    fig.tight_layout()
    fig.savefig(png, dpi=120)
    print(f"Chart saved -> {png}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Detect anomalous error-rate windows in app logs.")
    ap.add_argument("logfile", help="path to the log file")
    ap.add_argument("--eval", action="store_true", help="score against logs/ground_truth.json")
    ap.add_argument("--chart", action="store_true", help="save error-rate trend PNG (needs matplotlib)")
    args = ap.parse_args()

    log_path = Path(args.logfile)
    entries, skipped = parse(log_path)
    buckets = bucketize(entries)
    events, baselines = detect(buckets)

    eval_result = None
    if args.eval:
        gt_path = log_path.parent / "ground_truth.json"
        ground_truth = json.loads(gt_path.read_text(encoding="utf-8"))
        eval_result = evaluate(events, ground_truth)

    print_report(events, baselines, len(entries), skipped, eval_result)

    if args.chart:
        make_chart(events, baselines, buckets, log_path)


if __name__ == "__main__":
    main()
