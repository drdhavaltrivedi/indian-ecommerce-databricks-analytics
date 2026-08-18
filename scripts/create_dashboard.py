#!/usr/bin/env python3
"""Create/update the Lakeview dashboard for the Indian e-commerce project."""
import os, sys, json, urllib.request, urllib.error

HOST = os.environ["DATABRICKS_HOST"].rstrip("/")
TOKEN = os.environ["DATABRICKS_TOKEN"]
WAREHOUSE_ID = os.environ["DBX_WAREHOUSE_ID"]
DISPLAY_NAME = "Indian Ecommerce Analytics"


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


def dataset(name, query):
    return {"name": name, "displayName": name, "queryLines": [query]}


def counter(name, ds, field, title):
    return {"widget": {
        "name": name,
        "queries": [{"name": "main_query", "query": {
            "datasetName": ds, "fields": [{"name": field, "expression": f"`{field}`"}],
            "disaggregated": False}}],
        "spec": {"version": 2, "widgetType": "counter",
                 "encodings": {"value": {"fieldName": field, "displayName": title}},
                 "frame": {"title": title, "showTitle": True}},
    }}


def chart(name, ds, x, y, title, widget_type="bar", scale_x="categorical"):
    return {"widget": {
        "name": name,
        "queries": [{"name": "main_query", "query": {
            "datasetName": ds,
            "fields": [{"name": x, "expression": f"`{x}`"}, {"name": y, "expression": f"`{y}`"}],
            "disaggregated": True}}],
        "spec": {"version": 3, "widgetType": widget_type,
                 "encodings": {
                     "x": {"fieldName": x, "scale": {"type": scale_x}, "displayName": x},
                     "y": {"fieldName": y, "scale": {"type": "quantitative"}, "displayName": y}},
                 "frame": {"title": title, "showTitle": True}},
    }}


def table(name, ds, columns, title):
    return {"widget": {
        "name": name,
        "queries": [{"name": "main_query", "query": {
            "datasetName": ds, "fields": [{"name": c, "expression": f"`{c}`"} for c in columns],
            "disaggregated": True}}],
        "spec": {"version": 1, "widgetType": "table",
                 "encodings": {"columns": [{"fieldName": c, "displayName": c} for c in columns]},
                 "frame": {"title": title, "showTitle": True}},
    }}


def pos(w, x, y, width, height):
    w["position"] = {"x": x, "y": y, "width": width, "height": height}
    return w


datasets = [
    dataset("kpi", """
        SELECT
          (SELECT ROUND(SUM(revenue)/1e6,1) FROM indian_ecommerce.gold.revenue_trends) AS revenue_m,
          (SELECT SUM(orders) FROM indian_ecommerce.gold.revenue_trends) AS total_orders,
          (SELECT COUNT(*) FROM indian_ecommerce.silver.dim_customer) AS total_customers,
          (SELECT ROUND(AVG(delay_rate_pct),1) FROM indian_ecommerce.gold.delivery_performance) AS avg_delay_pct
    """),
    dataset("revenue_trend", "SELECT month, revenue, orders FROM indian_ecommerce.gold.revenue_trends ORDER BY month"),
    dataset("category", "SELECT category, revenue, margin_pct FROM indian_ecommerce.gold.category_performance ORDER BY revenue DESC"),
    dataset("segment", "SELECT customer_segment, avg_lifetime_spend, churn_rate_pct FROM indian_ecommerce.gold.segment_performance"),
    dataset("channel", "SELECT marketing_channel, revenue FROM indian_ecommerce.gold.channel_performance"),
    dataset("delivery", "SELECT CONCAT(warehouse_city,' - ',shipping_method) AS route, delay_rate_pct FROM indian_ecommerce.gold.delivery_performance ORDER BY delay_rate_pct DESC LIMIT 12"),
    dataset("payment", "SELECT payment_method, failure_rate_pct FROM indian_ecommerce.gold.payment_performance ORDER BY failure_rate_pct DESC"),
    dataset("returns", "SELECT CONCAT(category,' - ',return_reason) AS reason, returns FROM indian_ecommerce.gold.return_analysis ORDER BY returns DESC LIMIT 10"),
    dataset("state", "SELECT delivery_state, revenue FROM indian_ecommerce.gold.state_performance ORDER BY revenue DESC LIMIT 10"),
    dataset("campaigns", "SELECT campaign_name, roi FROM indian_ecommerce.gold.campaign_roi ORDER BY roi DESC LIMIT 10"),
    dataset("dq", "SELECT check_name, affected_rows, pct_affected FROM indian_ecommerce.gold.data_quality ORDER BY pct_affected DESC"),
]

widgets = [
    pos(counter("c_rev", "kpi", "revenue_m", "Revenue analysed ($M)"), 0, 0, 3, 3),
    pos(counter("c_orders", "kpi", "total_orders", "Total orders"), 3, 0, 3, 3),
    pos(counter("c_cust", "kpi", "total_customers", "Total customers"), 0, 3, 3, 3),
    pos(counter("c_delay", "kpi", "avg_delay_pct", "Avg delivery delay rate (%)"), 3, 3, 3, 3),

    pos(chart("rev_trend", "revenue_trend", "month", "revenue", "Monthly Revenue", widget_type="line", scale_x="temporal"), 0, 6, 6, 7),

    pos(chart("cat_rev", "category", "category", "revenue", "Revenue by Category"), 0, 13, 3, 7),
    pos(chart("cat_margin", "category", "category", "margin_pct", "Margin % by Category"), 3, 13, 3, 7),

    pos(chart("seg_spend", "segment", "customer_segment", "avg_lifetime_spend", "Avg Lifetime Spend by Segment"), 0, 20, 3, 6),
    pos(chart("seg_churn", "segment", "customer_segment", "churn_rate_pct", "Churn Rate % by Segment"), 3, 20, 3, 6),

    pos(chart("channel_rev", "channel", "marketing_channel", "revenue", "Revenue by Marketing Channel"), 0, 26, 3, 6),
    pos(chart("campaign_roi", "campaigns", "campaign_name", "roi", "Top Campaigns by ROI"), 3, 26, 3, 6),

    pos(chart("delivery_delay", "delivery", "route", "delay_rate_pct", "Delivery Delay % - Warehouse x Method (worst 12)"), 0, 32, 6, 7),

    pos(chart("payment_fail", "payment", "payment_method", "failure_rate_pct", "Payment Failure Rate % by Method"), 0, 39, 3, 6),
    pos(chart("return_reasons", "returns", "reason", "returns", "Top Return Reasons"), 3, 39, 3, 6),

    pos(table("state_table", "state", ["delivery_state", "revenue"], "Revenue by State"), 0, 45, 3, 7),
    pos(table("dq_table", "dq", ["check_name", "affected_rows", "pct_affected"], "Data Quality Checks"), 3, 45, 3, 7),
]

serialized = {
    "datasets": datasets,
    "pages": [{"name": "main", "displayName": "Overview", "layout": widgets}],
}


def find_existing():
    res = api("GET", "/api/2.0/lakeview/dashboards?page_size=100")
    for d in res.get("dashboards", []):
        if d.get("display_name") == DISPLAY_NAME and d.get("lifecycle_state") != "TRASHED":
            return d["dashboard_id"]
    return None


if __name__ == "__main__":
    body = {
        "display_name": DISPLAY_NAME,
        "warehouse_id": WAREHOUSE_ID,
        "serialized_dashboard": json.dumps(serialized),
    }
    existing = find_existing()
    if existing:
        result = api("PATCH", f"/api/2.0/lakeview/dashboards/{existing}", body)
        did = existing
        print("Updated dashboard:", did)
    else:
        did = api("POST", "/api/2.0/lakeview/dashboards", body)["dashboard_id"]
        print("Created dashboard:", did)

    api("POST", f"/api/2.0/lakeview/dashboards/{did}/published",
        {"embed_credentials": True, "warehouse_id": WAREHOUSE_ID})
    print("Published.")
    print(f"URL: {HOST}/dashboardsv3/{did}/published")
