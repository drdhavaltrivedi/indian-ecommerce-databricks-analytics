#!/usr/bin/env python3
"""Create/update the scheduled pipeline job for the Indian e-commerce project.
Same pattern as the clickstream project: SQL-file tasks against the shared
warehouse, created PAUSED so a script does not start spending someone's
warehouse budget without them deciding to turn it on.
"""
import os, sys, json, urllib.request, urllib.error, urllib.parse, base64

HOST = os.environ["DATABRICKS_HOST"].rstrip("/")
TOKEN = os.environ["DATABRICKS_TOKEN"]
WAREHOUSE_ID = os.environ["DBX_WAREHOUSE_ID"]

JOB_NAME = "indian-ecommerce-medallion-refresh"
WS_DIR = "/Shared/indian_ecommerce/sql"

TASKS = [
    ("bronze",        "01_bronze.sql",       []),
    ("silver",        "02_silver.sql",       ["bronze"]),
    ("gold",          "03_gold.sql",         ["silver"]),
    ("opportunities", "04_opportunities.sql", ["silver"]),
    ("security",      "05_security.sql",     ["silver"]),
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
        print(f"[{e.code}] {e.read().decode()[:600]}", file=sys.stderr)
        raise


def upload_sql_to_workspace():
    repo_sql = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sql")
    api("POST", "/api/2.0/workspace/mkdirs", {"path": WS_DIR})
    for _, filename, _ in TASKS:
        with open(os.path.join(repo_sql, filename), "rb") as f:
            content = base64.b64encode(f.read()).decode()
        api("POST", "/api/2.0/workspace/import", {
            "path": f"{WS_DIR}/{filename}", "format": "RAW",
            "content": content, "overwrite": True,
        })
        print(f"  uploaded {filename}")


def build_job_settings():
    tasks = []
    for key, filename, depends in TASKS:
        task = {
            "task_key": key,
            "sql_task": {"file": {"path": f"{WS_DIR}/{filename}", "source": "WORKSPACE"},
                         "warehouse_id": WAREHOUSE_ID},
        }
        if depends:
            task["depends_on"] = [{"task_key": d} for d in depends]
        tasks.append(task)
    return {
        "name": JOB_NAME,
        "tasks": tasks,
        "schedule": {"quartz_cron_expression": "0 0 5 * * ?", "timezone_id": "UTC",
                     "pause_status": "PAUSED"},
        "max_concurrent_runs": 1,
        "queue": {"enabled": True},
        "tags": {"project": "indian_ecommerce", "layer": "pipeline"},
    }


def find_existing():
    res = api("GET", f"/api/2.2/jobs/list?name={urllib.parse.quote(JOB_NAME)}")
    for j in res.get("jobs", []):
        if j["settings"]["name"] == JOB_NAME:
            return j["job_id"]
    return None


if __name__ == "__main__":
    print("Uploading SQL files to workspace...")
    upload_sql_to_workspace()
    settings = build_job_settings()
    existing = find_existing()
    if existing:
        api("POST", "/api/2.2/jobs/reset", {"job_id": existing, "new_settings": settings})
        job_id = existing
        print("Updated job:", job_id)
    else:
        job_id = api("POST", "/api/2.2/jobs/create", settings)["job_id"]
        print("Created job:", job_id)
    print(f"  tasks:    {' -> '.join(k for k, _, _ in TASKS)}")
    print(f"  schedule: 05:00 UTC daily (PAUSED)")
    print(f"URL: {HOST}/jobs/{job_id}")
