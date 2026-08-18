#!/usr/bin/env python3
"""Snapshot headline metrics after every pipeline run and flag drift.

Built specifically because of a real incident: when November data was added
to the clickstream project, the cart-tracking gap moved from 53.6% to 32.97%
-- a 20-point swing in the finding's own story, not just a number getting
bigger with more data. Nothing caught it. It sat undetected in the README and
docs/INSIGHTS.md until someone asked directly. This script exists so that
next time, the pipeline itself notices.

Each metric is a single SQL query returning one scalar. Every run appends a
timestamped row to <catalog>.ops.metrics_history (creating the ops schema if
needed) and compares the new value against the immediately preceding snapshot
for that same metric, flagging anything past --threshold (default 10%).

Usage:
    python3 scripts/metrics_snapshot.py metrics_config.json
    python3 scripts/metrics_snapshot.py metrics_config.json --threshold 15
"""
import os, sys, json, argparse, urllib.request, urllib.error, time
from datetime import datetime, timezone

HOST = os.environ["DATABRICKS_HOST"].rstrip("/")
TOKEN = os.environ["DATABRICKS_TOKEN"]
WAREHOUSE_ID = os.environ["DBX_WAREHOUSE_ID"]


def api(method, path, body=None):
    req = urllib.request.Request(
        f"{HOST}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
    )
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read() or b"{}")


def run_sql(statement, timeout_s=120):
    res = api("POST", "/api/2.0/sql/statements", {
        "warehouse_id": WAREHOUSE_ID, "statement": statement, "wait_timeout": "50s",
    })
    stmt_id = res["statement_id"]
    waited = 0
    while res["status"]["state"] in ("PENDING", "RUNNING") and waited < timeout_s:
        time.sleep(2); waited += 2
        res = api("GET", f"/api/2.0/sql/statements/{stmt_id}")
    if res["status"]["state"] != "SUCCEEDED":
        raise RuntimeError(f"Query failed: {json.dumps(res.get('status', {}))[:400]}")
    return res.get("result", {}).get("data_array", [])


def scalar(sql):
    rows = run_sql(sql)
    if not rows or rows[0][0] is None:
        return None
    return float(rows[0][0])


def ensure_history_table(catalog):
    run_sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.ops")
    run_sql(f"""
        CREATE TABLE IF NOT EXISTS {catalog}.ops.metrics_history (
          metric_name STRING,
          value DOUBLE,
          snapshot_ts TIMESTAMP,
          run_id STRING
        ) USING DELTA
        COMMENT 'One row per metric per pipeline run. Powers metrics_snapshot.py drift detection -- built after the cart-tracking-gap finding changed by 20 points between the October and November loads with nothing to flag it.'
    """)


def record_snapshot(catalog, metrics, run_id):
    values = {}
    for name, sql in metrics.items():
        try:
            v = scalar(sql)
        except Exception as e:
            print(f"  [{name}] query failed: {e}", file=sys.stderr)
            v = None
        values[name] = v

    rows_sql = ",\n".join(
        f"('{name}', {v if v is not None else 'NULL'}, current_timestamp(), '{run_id}')"
        for name, v in values.items()
    )
    run_sql(f"""
        INSERT INTO {catalog}.ops.metrics_history (metric_name, value, snapshot_ts, run_id)
        VALUES {rows_sql}
    """)
    return values


def previous_values(catalog, metric_names, before_run_id):
    names_sql = ", ".join(f"'{n}'" for n in metric_names)
    rows = run_sql(f"""
        SELECT metric_name, value
        FROM (
          SELECT metric_name, value,
                 ROW_NUMBER() OVER (PARTITION BY metric_name ORDER BY snapshot_ts DESC) AS rn
          FROM {catalog}.ops.metrics_history
          WHERE metric_name IN ({names_sql}) AND run_id <> '{before_run_id}'
        )
        WHERE rn = 1
    """)
    return {r[0]: (float(r[1]) if r[1] is not None else None) for r in rows}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("config", help="Path to a JSON file: {\"catalog\": \"...\", \"metrics\": {\"name\": \"SELECT ...\"}}")
    p.add_argument("--threshold", type=float, default=10.0, help="Percent change that triggers a flag (default 10)")
    args = p.parse_args()

    cfg = json.load(open(args.config))
    catalog = cfg["catalog"]
    metrics = cfg["metrics"]

    ensure_history_table(catalog)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    prev = previous_values(catalog, list(metrics.keys()), before_run_id=run_id)
    current = record_snapshot(catalog, metrics, run_id)

    print(f"\n{'Metric':<32} {'Previous':>16} {'Current':>16} {'Change':>10}  Flag")
    print("-" * 90)
    any_flag = False
    for name in metrics:
        cur = current.get(name)
        old = prev.get(name)
        if cur is None:
            print(f"{name:<32} {'—':>16} {'ERROR':>16} {'—':>10}")
            continue
        if old is None:
            print(f"{name:<32} {'(no prior)':>16} {cur:>16,.2f} {'—':>10}  baseline")
            continue
        pct_change = ((cur - old) / old * 100) if old != 0 else (float("inf") if cur != 0 else 0)
        flagged = abs(pct_change) >= args.threshold
        any_flag = any_flag or flagged
        flag_str = f"** {pct_change:+.1f}% **" if flagged else f"{pct_change:+.1f}%"
        print(f"{name:<32} {old:>16,.2f} {cur:>16,.2f} {flag_str:>10}")

    print()
    if any_flag:
        print(f"DRIFT DETECTED: one or more metrics moved >= {args.threshold}% since the last run.")
        print("Check whether README/docs need updating before they're read or shared.")
        sys.exit(1)
    else:
        print("No metric moved beyond the threshold. Docs should still be accurate.")


if __name__ == "__main__":
    main()
