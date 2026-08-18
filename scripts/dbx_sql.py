#!/usr/bin/env python3
import os, sys, json, time, urllib.request

HOST = os.environ["DATABRICKS_HOST"].rstrip("/")
TOKEN = os.environ["DATABRICKS_TOKEN"]
WAREHOUSE_ID = os.environ["DBX_WAREHOUSE_ID"]

def api(method, path, body=None):
    url = f"{HOST}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(e.read().decode(), file=sys.stderr)
        raise

def run_sql(statement, wait=60):
    res = api("POST", "/api/2.0/sql/statements", {
        "warehouse_id": WAREHOUSE_ID,
        "statement": statement,
        "wait_timeout": f"{min(wait,50)}s",
    })
    stmt_id = res["statement_id"]
    status = res["status"]["state"]
    while status in ("PENDING", "RUNNING"):
        time.sleep(2)
        res = api("GET", f"/api/2.0/sql/statements/{stmt_id}")
        status = res["status"]["state"]
    if status != "SUCCEEDED":
        print(json.dumps(res, indent=2), file=sys.stderr)
        raise SystemExit(f"Statement failed: {status}")
    return res

if __name__ == "__main__":
    sql = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
    result = run_sql(sql)
    data = result.get("result", {})
    if "data_array" in data:
        cols = [c["name"] for c in result["manifest"]["schema"]["columns"]]
        print("\t".join(cols))
        for row in data["data_array"]:
            print("\t".join(str(v) for v in row))
    else:
        print("OK")
