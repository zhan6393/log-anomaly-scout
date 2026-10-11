# Incident Operations Dashboard

![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-dashboard-FF4B4B?style=flat-square&logo=streamlit&logoColor=white)
![pandas](https://img.shields.io/badge/pandas-150458?style=flat-square&logo=pandas&logoColor=white)
![matplotlib](https://img.shields.io/badge/matplotlib-charts-11557c?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)

An incident-operations dashboard over a **synthetic** incident dataset:
SLA attainment, mean time to resolution (MTTR), severity mix, and weekly
volume — the same views an SRE / production-support team watches in
Datadog, PagerDuty, or ServiceNow.

Two frontends share one metrics module (`metrics.py`), so the numbers
always agree:

- **`app.py`** — interactive Streamlit dashboard with team/severity filters
- **`report.py`** — CLI fallback that prints the metrics and saves PNG charts
  (no browser needed)

## Quickstart

```bash
pip install -r requirements.txt

# 1. generate the dataset (300 incidents, seed 42 — reproducible)
python generate_data.py

# 2a. interactive dashboard
streamlit run app.py
# 2b. or CLI report + PNG charts
python report.py
```

## Sample output

```
==============================================
INCIDENT OPERATIONS REPORT (synthetic demo data)
==============================================
Total incidents : 300
SLA attainment  : 87.3%
Avg MTTR        : 67.6 hours
P1 incidents    : 10
SLA breaches    : 38

Incidents by severity:
  P1: 10
  P2: 56
  P3: 108
  P4: 126

Avg MTTR by severity (hours):
  P1: 3.1
  P2: 16.4
  P3: 40.7
  P4: 118.5

SLA attainment by team:
  Network: 84.7%
  Data Engineering: 87.0%
  App Support: 87.2%
  Platform: 90.0%

charts saved to charts/
```

Charts produced by `report.py` (also live in the Streamlit app):

| Chart | File |
|---|---|
| Incidents by severity (P1–P4) | `charts/severity.png` |
| Weekly incident volume | `charts/weekly_volume.png` |
| MTTR trend per week | `charts/mttr_trend.png` |
| SLA attainment by team | `charts/sla_by_team.png` |

## How the data is generated

`generate_data.py` synthesizes ~300 incidents over the trailing 12 weeks
(seed 42):

- **Severity mix:** P1 5% / P2 20% / P3 35% / P4 40%
- **SLA targets:** P1 4h, P2 24h, P3 72h, P4 168h (typical enterprise values)
- **Resolution times:** scaled to the severity's SLA target, with ~12%
  breaching the target — because a dashboard with 100% SLA attainment
  teaches nothing
- **Dimensions:** owning team (Platform, Data Engineering, Network,
  App Support) × category (Database, API, Infrastructure, Deployment,
  Monitoring, Auth)

Every timestamp, title, and team is fictional. The schema mirrors what
real incident exports look like:

```
incident_id,title,severity,team,category,opened_at,resolved_at,sla_target_h
INC-0001,SSO login failures,P4,Platform,Auth,2026-08-22 15:53,2026-08-28 15:11,168
```

## Project structure

```
incident-ops-dashboard/
├── generate_data.py   # synthetic dataset generator -> incidents.csv
├── metrics.py         # shared KPI computations (SLA, MTTR, distributions)
├── app.py             # Streamlit dashboard (filters + charts + data table)
├── report.py          # CLI report + matplotlib PNG fallback
├── incidents.csv      # generated sample data (300 rows)
├── charts/            # PNG output from report.py
└── requirements.txt
```

## Why this exists

Production support lives in these numbers: are we meeting SLA, where is
MTTR drifting, which team is breaching? This demo shows the full loop —
from raw incident rows to the KPIs a support manager actually reads —
with clean, testable metric functions instead of one-off notebook cells.
