#!/usr/bin/env python3
"""Run a .sql file against a Databricks SQL warehouse, one statement at a time."""
import sys, os, re, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dbx_sql import run_sql

def split_statements(sql_text):
    """Split on semicolons that are NOT inside a string literal."""
    lines = [l for l in sql_text.splitlines() if not l.strip().startswith("--")]
    body = "\n".join(lines)

    statements, buf, in_str = [], [], False
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == "'":
            # '' inside a string is an escaped quote, not a terminator
            if in_str and i + 1 < len(body) and body[i + 1] == "'":
                buf.append("''")
                i += 2
                continue
            in_str = not in_str
            buf.append(ch)
        elif ch == ";" and not in_str:
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
        else:
            buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements

if __name__ == "__main__":
    path = sys.argv[1]
    with open(path) as f:
        statements = split_statements(f.read())
    print(f"{len(statements)} statement(s) in {os.path.basename(path)}")
    for i, stmt in enumerate(statements, 1):
        label = " ".join(stmt.split())[:90]
        print(f"\n[{i}/{len(statements)}] {label}...")
        t0 = time.time()
        res = run_sql(stmt, wait=50)
        data = res.get("result", {})
        if "data_array" in data:
            cols = [c["name"] for c in res["manifest"]["schema"]["columns"]]
            print("  " + " | ".join(cols))
            for row in data["data_array"][:20]:
                print("  " + " | ".join(str(v) for v in row))
        print(f"  OK ({time.time()-t0:.1f}s)")
    print("\nAll statements completed.")
