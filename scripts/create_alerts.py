#!/usr/bin/env python3
"""SQL alerts for the Indian e-commerce pipeline, on the Alerts V2 API.

Each alert is self-contained (query text inline, no separate saved query),
runs on a daily schedule, and notifies a shared email notification
destination -- so a breach actually reaches someone instead of sitting
silent in the Alerts tab. The data pipeline itself stays on manual refresh
(run_pipeline.py) by design; these alerts run independently on their own
schedule so a stale-data breach gets flagged even between manual runs.
"""
import os, sys, json, urllib.request, urllib.error

HOST = os.environ["DATABRICKS_HOST"].rstrip("/")
TOKEN = os.environ["DATABRICKS_TOKEN"]
WAREHOUSE_ID = os.environ["DBX_WAREHOUSE_ID"]

NOTIFICATION_DESTINATION_NAME = "Dashboard alert email"
NOTIFICATION_EMAIL = "dhaval.m@brilworks.com"

ALERTS = [
    {
        "name": "[indian_ecommerce] Gold tables are stale (>36h)",
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
        "sql": """
SELECT MAX(pct_affected) AS worst_check_pct
FROM indian_ecommerce.gold.data_quality
""".strip(),
        "column": "worst_check_pct",
        "op": "GREATER_THAN",
        "threshold": 1.0,
        "why": "All eight checks currently read 0.00%. Any non-zero value means the source generator, ingestion, or a silver-layer filter change introduced a data integrity break that was not present before.",
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


def upsert_notification_destination():
    existing = api("GET", "/api/2.0/notification-destinations").get("results", [])
    for d in existing:
        if d.get("display_name") == NOTIFICATION_DESTINATION_NAME:
            return d["id"]
    created = api("POST", "/api/2.0/notification-destinations", {
        "display_name": NOTIFICATION_DESTINATION_NAME,
        "config": {"email": {"addresses": [NOTIFICATION_EMAIL]}},
    })
    return created["id"]


def upsert_alert(spec, destination_id):
    payload = {
        "display_name": spec["name"],
        "query_text": spec["sql"],
        "warehouse_id": WAREHOUSE_ID,
        "custom_body": spec["why"],
        "evaluation": {
            "source": {"name": spec["column"]},
            "comparison_operator": spec["op"],
            "threshold": {"value": {"double_value": spec["threshold"]}},
            "notification": {
                "notify_on_ok": True,
                "subscriptions": [{"destination_id": destination_id}],
            },
        },
        "schedule": {
            "quartz_cron_schedule": "0 0 6 * * ?",  # daily 06:00 UTC
            "timezone_id": "UTC",
            "pause_status": "UNPAUSED",
        },
    }
    existing = api("GET", "/api/2.0/alerts?page_size=100").get("results", [])
    for a in existing:
        if a.get("display_name") == spec["name"]:
            api("PATCH", f"/api/2.0/alerts/{a['id']}",
                {"alert": payload, "update_mask": "display_name,query_text,warehouse_id,custom_body,evaluation,schedule"})
            return a["id"], "updated"
    created = api("POST", "/api/2.0/alerts", payload)
    return created["id"], "created"


if __name__ == "__main__":
    destination_id = upsert_notification_destination()
    print(f"Notification destination: {NOTIFICATION_DESTINATION_NAME} ({NOTIFICATION_EMAIL}) -> {destination_id}\n")
    for spec in ALERTS:
        aid, action = upsert_alert(spec, destination_id)
        print(f"{action}: {spec['name']}")
        print(f"   {spec['column']} > {spec['threshold']}  ->  {HOST}/sql/alerts/{aid}")
    print(f"\nAlerts run daily (06:00 UTC) and notify {NOTIFICATION_EMAIL} on breach and on recovery.")
