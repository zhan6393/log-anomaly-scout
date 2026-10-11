# Log Anomaly Scout 🔍

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![No dependencies](https://img.shields.io/badge/core-zero--dependencies-lightgrey.svg)](scout.py)

Find anomalous error-rate windows in application logs — fast, transparent, and
dependency-free. Built from my experience in production support: most incident
triage starts with "which service's error rate just moved, and what is it
saying?"

## What it does

1. **`generate_logs.py`** synthesizes ~2,000 lines of application logs
   (`timestamp level service message`) across 4 fictional services, with
   **3 injected incident windows** (DB connection storm, upstream timeout
   wave, circuit-breaker opening) plus light background noise. A fixed
   random seed makes everything reproducible. The injected windows are saved
   to `logs/ground_truth.json` for evaluation.
2. **`scout.py`** detects the incidents:
   - Buckets logs into **5-minute windows per service** and computes the
     ERROR rate per bucket (buckets with < 5 lines are skipped to avoid
     noisy tiny samples).
   - Builds a **per-service baseline** and flags buckets above
     `max(mean + 3σ, 10%)` with at least 3 errors.
   - Merges consecutive flagged buckets into **events** reporting start/end
     time, peak error rate, top raw error messages, and a "likely cause"
     (most common message template after masking request ids).
   - `--eval` scores window-level **precision / recall / F1** against
     `ground_truth.json`; `--chart` renders per-service error-rate trends
     with thresholds and shaded anomaly windows (needs matplotlib).

## Quickstart

```bash
# 1. Generate synthetic logs + ground truth
python generate_logs.py

# 2. Run the detector
python scout.py logs/app.log

# 3. Evaluate against the injected incidents
python scout.py logs/app.log --eval

# 4. (optional) error-rate trend chart -> charts/app-trend.png
pip install matplotlib
python scout.py logs/app.log --chart
```

## Sample output

Real run of `python scout.py logs/app.log --eval`:

```
================================================================
Log Anomaly Scout — report
================================================================
lines parsed : 2000 (skipped 0 malformed)
services     : api-gateway, auth-svc, order-svc, payment-svc
bucket size  : 5 min (min 5 lines/bucket)
events found : 3

  [api-gateway] baseline mean=0.050 std=0.121 threshold=0.412 over 62 buckets
  [auth-svc] baseline mean=0.024 std=0.055 threshold=0.190 over 61 buckets
  [order-svc] baseline mean=0.026 std=0.102 threshold=0.331 over 57 buckets
  [payment-svc] baseline mean=0.031 std=0.113 threshold=0.369 over 63 buckets

--- Event 1: payment-svc  2026-10-01 01:10 -> 2026-10-01 01:20 ---
peak error rate : 66.7%  (8 errors in window)
likely cause    : Transaction rollback failed req_id=REQ-# reason=db-unavailable
top error messages:
  - Transaction rollback failed req_id=REQ-437524 reason=db-unavailable
  - Connection refused: db-primary:5432 pool exhausted req_id=REQ-356939
  - Transaction rollback failed req_id=REQ-640657 reason=db-unavailable

--- Event 2: api-gateway  2026-10-01 03:45 -> 2026-10-01 03:55 ---
peak error rate : 62.5%  (10 errors in window)
likely cause    : 502 Bad Gateway req_id=REQ-# upstream=orders
top error messages:
  - Upstream timeout after 5000ms req_id=REQ-062140 upstream=orders
  ...

--- Event 3: order-svc  2026-10-01 05:00 -> 2026-10-01 05:10 ---
peak error rate : 55.6%  (8 errors in window)
likely cause    : Circuit breaker OPEN for inventory-client req_id=REQ-#
top error messages:
  - Circuit breaker OPEN for inventory-client req_id=REQ-892540
  ...

----------------------------------------------------------------
Evaluation vs ground truth
precision=1.00  recall=1.00  f1=1.00  (TP=3 FP=0 FN=0)
  hit: db-connection-storm (coverage 67%)
  hit: upstream-timeout-wave (coverage 56%)
  hit: circuit-breaker-open (coverage 83%)
```

All three injected incidents are found, no false positives, on this seed.

## Honest caveats

- **Synthetic data.** The logs, services, hostnames, and incidents are
  entirely fictional. Real log streams are noisier, bursty, and full of
  edge cases this demo never sees.
- **Simple statistics.** A per-service mean+3σ threshold catches big spikes
  but has no notion of seasonality, deploy-correlated changes, or gradual
  degradation. A production version would use a rolling/seasonal baseline
  (e.g. compare against the same window last week) and adaptive thresholds.
- **No root-cause analysis.** "Likely cause" is just the most frequent
  masked message template — it surfaces *what the logs are saying*, not
  *why the system broke*. Real triage still needs traces, deploy history,
  and infra signals.
- **Toy scale.** 2,000 lines fit in memory. A production pipeline would
  stream batches and emit alerts, not print a report.

## Project structure

```
log-anomaly-scout/
├── generate_logs.py   # synthetic log + ground truth generator (seeded)
├── scout.py           # anomaly detector: bucket, baseline, flag, merge, eval
├── requirements.txt   # optional: matplotlib (charting only)
├── README.md
├── LICENSE            # MIT
├── .gitignore         # logs/, charts/, __pycache__/
├── logs/              # generated at runtime (gitignored)
│   ├── app.log
│   └── ground_truth.json
└── charts/            # generated by --chart (gitignored)
```

## Author

Yiming Zhang — [GitHub](https://github.com/zhan6393) · [LinkedIn](https://www.linkedin.com/in/yiming-zhang20000101)
