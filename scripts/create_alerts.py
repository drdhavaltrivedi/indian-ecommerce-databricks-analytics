#!/usr/bin/env python3
"""SQL alerts for the Indian e-commerce pipeline. No schedule, no
recipients by default -- both are one click in the UI once someone decides
to turn them on.
"""
import os, sys, json, urllib.request, urllib.error

HOST = os.environ["DATABRICKS_HOST"].rstrip("/")
TOKEN = os.environ["DATABRICKS_TOKEN"]
WAREHOUSE_ID = os.environ["DBX_WAREHOUSE_ID"]

ALERTS = [
    {
        "name": "[indian_ecommerce] Gold tables are stale (>36h)",
        "query_name": "[indian_ecommerce] gold freshness",
        "sql": """
SELECT DATEDIFF(HOUR, MAX(month), CURRENT_TIMESTAMP()) AS hours_since_latest_month
FROM indian_ecommerce.gold.revenue_trends
""".strip(),
        "column": "hours_since_latest_month",
        "op": "GREATER_THAN",
        "threshold": 36.0,
        "why": "The job runs daily. 36h tolerates one missed run without false alarms, but catches a pipeline that has genuinely stopped.",
    },
    {
        "name": "[indian_ecommerce] Same-Day delay rate improved or worsened materially",
        "query_name": "[indian_ecommerce] same-day delay trend",
        "sql": """
SELECT AVG(delay_rate_pct) AS avg_same_day_delay_pct
FROM indian_ecommerce.gold.delivery_performance
WHERE shipping_method = 'Same-Day'
""".strip(),
        "column": "avg_same_day_delay_pct",
        "op": "GREATER_THAN",
        "threshold": 65.0,
        "why": "Baseline is ~54-60%. Above 65% the service tier has degraded further and needs escalation beyond the standing finding.",
    },
    {
        "name": "[indian_ecommerce] Referential integrity check failed",
        "query_name": "[indian_ecommerce] data quality regression",
        "sql": """
SELECT MAX(pct_affected) AS worst_check_pct
FROM indian_ecommerce.gold.data_quality
""".strip(),
        "column": "worst_check_pct",
        "op": "GREATER_THAN",
        "threshold": 1.0,
        "why": "All four checks currently read 0.00%. Any non-zero value means the source generator or ingestion introduced a referential integrity break that was not present before.",
    },
]


def api(method, path, body=None):
    req = urllib.request.Request(
        f"{HOST}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
    )
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        print(f"[{e.code}] {e.read().decode()[:500]}", file=sys.stderr)
        raise


def upsert_query(name, sql):
    existing = api("GET", "/api/2.0/sql/queries?page_size=100").get("results", [])
    for q in existing:
        if q.get("display_name") == name:
            api("PATCH", f"/api/2.0/sql/queries/{q['id']}",
                {"query": {"query_text": sql}, "update_mask": "query_text"})
            return q["id"]
    created = api("POST", "/api/2.0/sql/queries", {
        "query": {"display_name": name, "query_text": sql, "warehouse_id": WAREHOUSE_ID}
    })
    return created["id"]


def upsert_alert(spec, query_id):
    condition = {
        "op": spec["op"],
        "operand": {"column": {"name": spec["column"]}},
        "threshold": {"value": {"double_value": spec["threshold"]}},
    }
    payload = {"display_name": spec["name"], "query_id": query_id,
               "condition": condition, "custom_body": spec["why"]}
    existing = api("GET", "/api/2.0/sql/alerts?page_size=100").get("results", [])
    for a in existing:
        if a.get("display_name") == spec["name"]:
            api("PATCH", f"/api/2.0/sql/alerts/{a['id']}",
                {"alert": payload, "update_mask": "condition,custom_body,query_id"})
            return a["id"], "updated"
    created = api("POST", "/api/2.0/sql/alerts", {"alert": payload})
    return created["id"], "created"


if __name__ == "__main__":
    for spec in ALERTS:
        qid = upsert_query(spec["query_name"], spec["sql"])
        aid, action = upsert_alert(spec, qid)
        print(f"{action}: {spec['name']}")
        print(f"   {spec['column']} > {spec['threshold']}  ->  {HOST}/sql/alerts/{aid}")
    print("\nAlerts have no schedule and no notification destination by design.")
