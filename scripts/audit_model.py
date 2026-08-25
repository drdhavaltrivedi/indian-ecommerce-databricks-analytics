#!/usr/bin/env python3
"""Generic data-modelling auditor.

Written after two real bugs in this project traced to the same root cause: a
join key that was assumed unique and never actually tested. Spot-checking
does not catch that class of problem -- you have to test every key, on every
table, every time the data changes.

This script discovers the schema itself rather than being told about it, so
it works on any catalog.schema, including ones it has never seen. It reports:

  PK        columns that are unique + non-null (viable primary keys)
  NO-PK     tables with no single-column unique key at all
  CARTESIAN two tables repeating the same key -- joining both multiplies rows
  NEAR-KEY  a column that looks unique but has a few duplicates
  FANOUT    multi-column candidate keys that are not actually unique
  ORPHAN    foreign-key values with no matching parent row
  CONSTANT  columns holding exactly one value (carry no information)
  NULLS     columns more than 50% null
  NEGATIVE  amount/price/qty columns containing negative values
  RANGE     pct/rate columns outside 0-100
  FUTURE    date columns containing dates after today

Usage:
    python3 scripts/audit_model.py indian_ecommerce.silver
    python3 scripts/audit_model.py ecommerce.silver
    python3 scripts/audit_model.py indian_ecommerce.silver --fail-on-orphan
"""
import os, sys, re
from dbx_sql import run_sql

SEV = {"ORPHAN": 1, "CARTESIAN": 1, "FANOUT": 2, "NEAR-KEY": 2, "NO-PK": 2, "NEGATIVE": 2, "RANGE": 2,
       "FUTURE": 2, "CONSTANT": 3, "NULLS": 3, "PK": 4}

AMOUNT_RE = re.compile(r"(amount|price|revenue|cost|spend|profit|fee|refund|value|qty|quantity|count|orders|sessions|units)", re.I)
PCT_RE    = re.compile(r"(_pct|percent|percentage|_rate$|rate_pct)", re.I)
ID_RE     = re.compile(r"(_id$|^id$)", re.I)
NUMERIC   = {"INT", "BIGINT", "DOUBLE", "FLOAT", "DECIMAL", "SMALLINT", "TINYINT", "LONG"}
DATEISH   = {"DATE", "TIMESTAMP"}


def q(sql):
    r = run_sql(sql)
    return r["result"].get("data_array", []) if r.get("result") else []


def discover(catalog, schema):
    rows = q(f"""SELECT table_name, column_name, data_type
                 FROM {catalog}.information_schema.columns
                 WHERE table_schema = '{schema}'
                 ORDER BY table_name, ordinal_position""")
    tables = {}
    for t, c, dt in rows:
        tables.setdefault(t, []).append((c, dt.upper().split("(")[0]))
    return tables


def profile_table(fq, cols):
    """One query per table: row count plus non-null and distinct per column."""
    sel = ["COUNT(*) AS __rows"]
    for c, _ in cols:
        sel.append(f"COUNT(`{c}`) AS `nn_{c}`")
        sel.append(f"COUNT(DISTINCT `{c}`) AS `dc_{c}`")
    data = q(f"SELECT {', '.join(sel)} FROM {fq}")
    if not data:
        return None
    vals = data[0]
    out = {"rows": int(vals[0]), "cols": {}}
    i = 1
    for c, dt in cols:
        out["cols"][c] = {"non_null": int(vals[i]), "distinct": int(vals[i + 1]), "type": dt}
        i += 2
    return out


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    target = sys.argv[1]
    strict = "--fail-on-orphan" in sys.argv
    catalog, schema = target.split(".")
    findings = []

    tables = discover(catalog, schema)
    if not tables:
        sys.exit(f"No tables found in {target}")
    print(f"Auditing {target} -- {len(tables)} tables\n")

    prof = {}
    for t, cols in tables.items():
        p = profile_table(f"{catalog}.{schema}.{t}", cols)
        if p:
            prof[t] = p

    # ---- per-table column findings + PK discovery -------------------------
    pk_of = {}
    for t, p in prof.items():
        rows = p["rows"]
        pks = []
        for c, m in p["cols"].items():
            if rows and m["non_null"] == rows and m["distinct"] == rows:
                pks.append(c)
                findings.append(("PK", t, c, f"unique + non-null over {rows:,} rows"))
            if rows and m["distinct"] == 1:
                findings.append(("CONSTANT", t, c, "only one distinct value -- carries no information"))
            if rows and m["non_null"] / rows < 0.5:
                pct = 100 * (1 - m["non_null"] / rows)
                findings.append(("NULLS", t, c, f"{pct:.0f}% null"))
        if pks:
            # prefer an *_id column as the declared PK
            pk_of[t] = next((c for c in pks if ID_RE.search(c)), pks[0])
        else:
            findings.append(("NO-PK", t, "-", f"no single column is unique over {rows:,} rows"))

    # ---- fan-out: every id column, and every id-column pair ---------------
    for t, p in prof.items():
        rows = p["rows"]
        ids = [c for c in p["cols"] if ID_RE.search(c)]
        for c in ids:
            d = p["cols"][c]["distinct"]
            # A fact table having many rows per dimension member is normal star
            # schema, not a defect -- only report it when the column is this
            # table's own apparent grain (i.e. nearly unique but not quite),
            # which is where someone is likely to assume uniqueness.
            if rows and d < rows and d / rows > 0.9:
                findings.append(("NEAR-KEY", t, c,
                                 f"{rows:,} rows / {d:,} distinct -- {rows - d:,} dupes, looks unique but is not"))
        pairs = [(ids[i], ids[j]) for i in range(len(ids)) for j in range(i + 1, len(ids))]
        if pairs:
            sel = ", ".join(f"COUNT(DISTINCT CONCAT_WS('|',`{a}`,`{b}`)) AS p{k}"
                            for k, (a, b) in enumerate(pairs))
            got = q(f"SELECT COUNT(*) AS n, {sel} FROM {catalog}.{schema}.{t}")
            if got:
                n = int(got[0][0])
                for k, (a, b) in enumerate(pairs):
                    d = int(got[0][k + 1])
                    if n > d:
                        findings.append(("FANOUT", t, f"{a} + {b}",
                                         f"{n:,} rows / {d:,} distinct -- pair is NOT unique"))

    # ---- orphan FKs: any id column matching another table's PK -----------
    fk_pairs = []
    for t, p in prof.items():
        for c in p["cols"]:
            if not ID_RE.search(c):
                continue
            for pt, pc in pk_of.items():
                if pt != t and pc == c:
                    fk_pairs.append((t, c, pt, pc))
    if fk_pairs:
        union = " UNION ALL ".join(
            f"""SELECT '{t}' AS ct, '{c}' AS cc, '{pt}' AS pt, COUNT(*) AS orphans
                FROM {catalog}.{schema}.{t} ch
                LEFT JOIN {catalog}.{schema}.{pt} pa ON pa.`{pc}` = ch.`{c}`
                WHERE ch.`{c}` IS NOT NULL AND pa.`{pc}` IS NULL"""
            for t, c, pt, pc in fk_pairs)
        for row in q(union):
            n = int(row[3])
            if n:
                findings.append(("ORPHAN", row[0], row[1], f"{n:,} values with no row in {row[2]}"))

    # ---- cartesian risk: two tables that BOTH fan out on the same key ----
    # This is the shape that produced the delay_impact AVG(rating) bug: join
    # two fact tables to a common parent on a key that repeats on both sides
    # and the row count multiplies, silently inflating SUM/AVG.
    multi = {}
    for t, p in prof.items():
        rows = p["rows"]
        for c in p["cols"]:
            if ID_RE.search(c) and rows and p["cols"][c]["distinct"] < rows:
                multi.setdefault(c, []).append(t)
    for key, ts in sorted(multi.items()):
        if len(ts) < 2:
            continue
        for i in range(len(ts)):
            for j in range(i + 1, len(ts)):
                findings.append(("CARTESIAN", f"{ts[i]} x {ts[j]}", key,
                                 "both sides repeat this key -- joining both to a "
                                 "common parent multiplies rows; aggregate each side first"))

    # ---- value sanity on typed columns ----------------------------------
    for t, p in prof.items():
        checks = []
        for c, m in p["cols"].items():
            if m["type"] not in NUMERIC and m["type"] not in DATEISH:
                continue
            if m["type"] in NUMERIC and AMOUNT_RE.search(c) and not PCT_RE.search(c):
                checks.append(("NEGATIVE", c, f"SUM(CASE WHEN `{c}` < 0 THEN 1 ELSE 0 END)", "negative values"))
            if m["type"] in NUMERIC and PCT_RE.search(c):
                checks.append(("RANGE", c, f"SUM(CASE WHEN `{c}` < 0 OR `{c}` > 100 THEN 1 ELSE 0 END)", "outside 0-100"))
            if m["type"] in DATEISH:
                checks.append(("FUTURE", c, f"SUM(CASE WHEN `{c}` > CURRENT_DATE() THEN 1 ELSE 0 END)", "dated after today"))
        if not checks:
            continue
        sel = ", ".join(f"{expr} AS c{i}" for i, (_, _, expr, _) in enumerate(checks))
        got = q(f"SELECT {sel} FROM {catalog}.{schema}.{t}")
        if got:
            for i, (kind, col, _, label) in enumerate(checks):
                v = got[0][i]
                n = int(v) if v not in (None, "null") else 0
                if n:
                    findings.append((kind, t, col, f"{n:,} rows {label}"))

    # ---- report ----------------------------------------------------------
    findings.sort(key=lambda f: (SEV.get(f[0], 9), f[1], f[2]))
    width = max((len(f[1]) for f in findings), default=10)
    shown = 0
    for kind, t, c, msg in findings:
        if kind == "PK":
            continue  # informational; summarised below
        print(f"  [{kind:<8}] {t:<{width}}  {c:<26} {msg}")
        shown += 1
    if not shown:
        print("  No structural issues found.")

    print(f"\n  Primary keys detected: " +
          ", ".join(f"{t}.{c}" for t, c in sorted(pk_of.items())))

    counts = {}
    for kind, *_ in findings:
        counts[kind] = counts.get(kind, 0) + 1
    print("\nSummary: " + (", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "clean"))

    if strict and counts.get("ORPHAN"):
        sys.exit("FAILED: orphaned foreign keys present")


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main()
