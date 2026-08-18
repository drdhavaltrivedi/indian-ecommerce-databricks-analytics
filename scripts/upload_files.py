#!/usr/bin/env python3
"""Upload small CSVs directly to a UC Volume via a single PUT each.

These files are all well under the 5GiB Files API limit, so no splitting is
needed -- just a plain PUT per file, verified by size afterward.
"""
import os, sys, glob, http.client, ssl
from urllib.parse import urlparse

HOST = os.environ["DATABRICKS_HOST"].rstrip("/")
TOKEN = os.environ["DATABRICKS_TOKEN"]


def put_file(local_path, volume_path):
    parsed = urlparse(HOST)
    size = os.path.getsize(local_path)
    conn = http.client.HTTPSConnection(parsed.netloc, context=ssl.create_default_context(), timeout=120)
    conn.putrequest("PUT", f"/api/2.0/fs/files{volume_path}?overwrite=true")
    conn.putheader("Authorization", f"Bearer {TOKEN}")
    conn.putheader("Content-Type", "application/octet-stream")
    conn.putheader("Content-Length", str(size))
    conn.endheaders()
    with open(local_path, "rb") as f:
        while True:
            chunk = f.read(4 * 1024 * 1024)
            if not chunk:
                break
            conn.send(chunk)
    resp = conn.getresponse()
    body = resp.read().decode()
    conn.close()
    if resp.status >= 300:
        raise SystemExit(f"Upload failed [{resp.status}]: {body[:300]}")
    print(f"  uploaded {volume_path} ({size/1e6:.2f} MB) -> {resp.status}")


if __name__ == "__main__":
    local_dir, volume_dir = sys.argv[1], sys.argv[2]
    for path in sorted(glob.glob(os.path.join(local_dir, "*.csv"))):
        name = os.path.basename(path)
        put_file(path, f"{volume_dir}/{name}")
    print("All files uploaded.")
