#!/usr/bin/env python3
"""Create/update the Lakeview dashboard for the Indian e-commerce project.

Second pass: the first version was a flat grid of same-sized charts with raw
INR values in the hundreds of millions and a stray '$' from an earlier draft
of the widget helpers. Neither is readable at a glance, which is the whole
point of a dashboard.

This version:
  - Uses INR (Cr = crore = 1e7) throughout, since the source data is Indian
    Rupees, not dollars.
  - Groups widgets into labelled sections with a one-line markdown note under
    each explaining what to look for -- a bar chart of "margin_pct by
    category" means nothing without the sentence that says why margin and
    revenue diverge.
  - Leads with the headline finding (Same-Day delivery, category margin gap)
    rather than burying it below generic KPIs.
"""
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


def chart(name, ds, x, y, title, widget_type="bar", scale_x="categorical", sort_desc=True):
    x_scale = {"type": scale_x}
    if scale_x == "categorical" and sort_desc:
        x_scale["sort"] = {"by": "y-reversed"}
    return {"widget": {
        "name": name,
        "queries": [{"name": "main_query", "query": {
            "datasetName": ds,
            "fields": [{"name": x, "expression": f"`{x}`"}, {"name": y, "expression": f"`{y}`"}],
            "disaggregated": True}}],
        "spec": {"version": 3, "widgetType": widget_type,
                 "encodings": {
                     "x": {"fieldName": x, "scale": x_scale, "displayName": x},
                     "y": {"fieldName": y, "scale": {"type": "quantitative"}, "displayName": y}},
                 "frame": {"title": title, "showTitle": True}},
    }}


def table(name, ds, columns, title):
    # The minimal column spec ({"fieldName", "displayName"}) renders as
    # "Visualization has no fields selected" in Lakeview -- table widgets
    # need each column's type/display/order made explicit, unlike counter
    # and chart widgets where a minimal encodings block is enough.
    return {"widget": {
        "name": name,
        "queries": [{"name": "main_query", "query": {
            "datasetName": ds, "fields": [{"name": c, "expression": f"`{c}`"} for c in columns],
            "disaggregated": True}}],
        "spec": {"version": 1, "widgetType": "table",
                 "encodings": {"columns": [
                     {"fieldName": c, "title": c, "type": "string", "displayAs": "string",
                      "visible": True, "order": i, "alignContent": "left",
                      "allowSearch": False, "allowHTML": False, "highlightLinks": False,
                      "useMonospaceFont": False, "preserveWhitespace": False}
                     for i, c in enumerate(columns)
                 ]},
                 "frame": {"title": title, "showTitle": True}},
    }}


def markdown(name, text):
    return {"widget": {"name": name, "textbox_spec": text}}


def pos(w, x, y, width, height):
    w["position"] = {"x": x, "y": y, "width": width, "height": height}
    return w


datasets = [
    dataset("kpi", """
        SELECT
          (SELECT ROUND(SUM(revenue)/1e7,1) FROM indian_ecommerce.gold.revenue_trends) AS revenue_cr,
          (SELECT SUM(orders) FROM indian_ecommerce.gold.revenue_trends) AS total_orders,
          (SELECT COUNT(*) FROM indian_ecommerce.silver.dim_customer) AS total_customers,
          (SELECT ROUND(AVG(delay_rate_pct),1) FROM indian_ecommerce.gold.delivery_performance
             WHERE shipping_method = 'Same-Day') AS same_day_delay_pct
    """),
    dataset("revenue_trend", """
        SELECT month, ROUND(revenue/1e7,2) AS revenue_cr, orders
        FROM indian_ecommerce.gold.revenue_trends ORDER BY month
    """),
    dataset("category", """
        SELECT category, ROUND(revenue/1e7,1) AS revenue_cr, margin_pct
        FROM indian_ecommerce.gold.category_performance ORDER BY revenue_cr DESC LIMIT 10
    """),
    dataset("segment", "SELECT customer_segment, ROUND(avg_lifetime_spend/1000,1) AS avg_lifetime_spend_k, churn_rate_pct FROM indian_ecommerce.gold.segment_performance"),
    dataset("channel", "SELECT marketing_channel, ROUND(revenue/1e7,1) AS revenue_cr FROM indian_ecommerce.gold.channel_performance ORDER BY revenue_cr DESC"),
    dataset("delivery", """
        SELECT CONCAT(warehouse_city,' · ',shipping_method) AS route, delay_rate_pct
        FROM indian_ecommerce.gold.delivery_performance ORDER BY delay_rate_pct DESC LIMIT 12
    """),
    dataset("payment", "SELECT payment_method, failure_rate_pct FROM indian_ecommerce.gold.payment_performance ORDER BY failure_rate_pct DESC"),
    dataset("returns", "SELECT CONCAT(category,' · ',return_reason) AS reason, returns FROM indian_ecommerce.gold.return_analysis ORDER BY returns DESC LIMIT 10"),
    dataset("state", "SELECT delivery_state, ROUND(revenue/1e7,1) AS revenue_cr FROM indian_ecommerce.gold.state_performance ORDER BY revenue_cr DESC LIMIT 10"),
    dataset("campaigns", "SELECT campaign_name, roi FROM indian_ecommerce.gold.campaign_roi ORDER BY roi DESC LIMIT 10"),
    dataset("dq", "SELECT check_name, description, affected_rows, pct_affected FROM indian_ecommerce.gold.data_quality ORDER BY pct_affected DESC"),
    dataset("true_profit", """
        SELECT product_name, category, gross_profit, total_refunded, refund_pct_of_profit
        FROM indian_ecommerce.gold.product_true_profitability
        WHERE refund_pct_of_profit > 100
        ORDER BY refund_pct_of_profit DESC LIMIT 10
    """),
    dataset("targeting", "SELECT target_segment, targeting_precision_pct FROM indian_ecommerce.gold.campaign_targeting_precision ORDER BY targeting_precision_pct"),
    dataset("delay_impact", "SELECT delivery_outcome, avg_rating, return_rate_pct FROM indian_ecommerce.gold.delay_impact_on_experience"),
    dataset("chan_eff", "SELECT channel, revenue_per_rupee_spent FROM indian_ecommerce.gold.channel_efficiency ORDER BY revenue_per_rupee_spent DESC"),
    dataset("discount_eff", "SELECT discount_band, cancel_rate_pct, avg_order_value FROM indian_ecommerce.gold.discount_effectiveness ORDER BY discount_band"),
    dataset("cohort", "SELECT cohort_month, retention_m1_pct, retention_m3_pct FROM indian_ecommerce.gold.cohort_retention ORDER BY cohort_month"),
    dataset("rfm", "SELECT customer_segment, avg_recency_score, avg_frequency_score, avg_monetary_score FROM indian_ecommerce.gold.rfm_segmentation ORDER BY avg_monetary_score DESC"),
    dataset("affinity", "SELECT CONCAT(category_a,' + ',category_b) AS pair, orders_together FROM indian_ecommerce.gold.category_affinity ORDER BY orders_together DESC LIMIT 8"),
    dataset("season", "SELECT CONCAT(LPAD(month_num,2,'0'), ' - ', month_name) AS month_name, orders FROM indian_ecommerce.gold.seasonality_patterns ORDER BY month_num"),
    dataset("repeat_timing", "SELECT pct_repeat_at_least_once, avg_days_to_2nd_order, median_days_to_2nd_order FROM indian_ecommerce.gold.repeat_purchase_timing"),
    dataset("sentiment_cat", "SELECT category, avg_rating, pct_negative FROM indian_ecommerce.gold.sentiment_by_category ORDER BY pct_negative DESC LIMIT 8"),
    dataset("sentiment_vol", "SELECT category, negative_reviews FROM indian_ecommerce.gold.sentiment_by_category ORDER BY negative_reviews DESC LIMIT 8"),
]

widgets = [
    # ---------------------------------------------------------------- header
    pos(markdown("title",
        "# Indian E-Commerce Analytics\n"
        "Synthetic dataset · 100K orders · 25K customers · 2023–2025 · "
        "amounts in ₹ crore (1 Cr = ₹10,000,000)"), 0, 0, 6, 2),

    # -------------------------------------------------------------- KPI row
    pos(counter("c_rev", "kpi", "revenue_cr", "Total Revenue (₹ Cr)"), 0, 2, 3, 3),
    pos(counter("c_orders", "kpi", "total_orders", "Total Orders"), 3, 2, 3, 3),
    pos(counter("c_cust", "kpi", "total_customers", "Total Customers"), 0, 5, 3, 3),
    pos(counter("c_delay", "kpi", "same_day_delay_pct", "Same-Day Delivery Delay Rate (%)"), 3, 5, 3, 3),

    pos(markdown("headline",
        "**The Same-Day delay rate above is not a typo.** Every major warehouse "
        "runs 54–60% delayed on that service tier — see the Delivery "
        "Operations section below."), 0, 8, 6, 1),

    # --------------------------------------------------------- revenue trend
    pos(markdown("h_revenue", "## Revenue & Order Volume Over Time"), 0, 9, 6, 1),
    pos(chart("rev_trend", "revenue_trend", "month", "revenue_cr",
              "Monthly Revenue (₹ Cr)", widget_type="line", scale_x="temporal"), 0, 10, 3, 7),
    pos(chart("orders_trend", "revenue_trend", "month", "orders",
              "Monthly Order Count", widget_type="line", scale_x="temporal"), 3, 10, 3, 7),

    # ------------------------------------------------------------- category
    pos(markdown("h_category", "## Category Performance — Revenue vs. Margin"), 0, 17, 6, 1),
    pos(markdown("n_category",
        "*Electronics drives the most revenue but returns under 1% margin. "
        "Fashion earns 33% margin on a fraction of the revenue. A revenue-only "
        "view misses which category is actually profitable.*"), 0, 18, 6, 1),
    pos(chart("cat_rev", "category", "category", "revenue_cr", "Revenue by Category (₹ Cr)"), 0, 19, 3, 7),
    pos(chart("cat_margin", "category", "category", "margin_pct", "Margin % by Category"), 3, 19, 3, 7),

    # -------------------------------------------------------------- segment
    pos(markdown("h_segment", "## Customer Segments — Spend vs. Retention"), 0, 26, 6, 1),
    pos(markdown("n_segment",
        "*Segment predicts lifetime spend well (12.8x range, Premium to New) but "
        "predicts churn barely at all — three of four segments sit within "
        "3 points of each other. Don't use segment as a churn model input.*"), 0, 27, 6, 1),
    pos(chart("seg_spend", "segment", "customer_segment", "avg_lifetime_spend_k",
              "Avg Lifetime Spend by Segment (₹ '000)"), 0, 28, 3, 6),
    pos(chart("seg_churn", "segment", "customer_segment", "churn_rate_pct",
              "Churn Rate % by Segment"), 3, 28, 3, 6),

    # ----------------------------------------------------------- marketing
    pos(markdown("h_marketing", "## Marketing Channels & Campaign ROI"), 0, 34, 6, 1),
    pos(chart("channel_rev", "channel", "marketing_channel", "revenue_cr",
              "Revenue by Marketing Channel (₹ Cr)"), 0, 35, 3, 6),
    pos(chart("campaign_roi", "campaigns", "campaign_name", "roi",
              "Top 10 Campaigns by ROI"), 3, 35, 3, 6),

    # ----------------------------------------------------------- operations
    pos(markdown("h_delivery", "## Delivery Operations — Where Delays Happen"), 0, 41, 6, 1),
    pos(markdown("n_delivery",
        "*Delay rate clusters at 54–60% for Same-Day across every warehouse. "
        "That consistency rules out one bad city — the service tier itself "
        "is the problem.*"), 0, 42, 6, 1),
    pos(chart("delivery_delay", "delivery", "route", "delay_rate_pct",
              "Delivery Delay % by Warehouse × Method (worst 12)"), 0, 43, 6, 7),

    # ------------------------------------------------------- payments/returns
    pos(markdown("h_pay_ret", "## Payments & Returns"), 0, 50, 6, 1),
    pos(chart("payment_fail", "payment", "payment_method", "failure_rate_pct",
              "Payment Failure Rate % by Method"), 0, 51, 3, 6),
    pos(chart("return_reasons", "returns", "reason", "returns",
              "Top Return Reasons (Category · Reason)"), 3, 51, 3, 6),

    # ------------------------------------------------------------- geography
    pos(markdown("h_geo", "## Geography & Data Quality"), 0, 57, 6, 1),
    pos(chart("state_rev", "state", "delivery_state", "revenue_cr",
              "Revenue by State (₹ Cr, top 10)"), 0, 58, 6, 7),
    pos(markdown("n_dq",
        "*8 checks, 0% affected on every one — referential integrity "
        "(orders/payments/shipments) plus business-rule sanity (future-dated "
        "orders, delivery-before-dispatch, duplicate order IDs, orphaned "
        "line items). The chart below is flat because there's nothing to "
        "show, not because it's broken.*"), 0, 65, 6, 1),
    pos(chart("dq_chart", "dq", "check_name", "pct_affected",
              "Data Quality Checks — all clean"), 0, 66, 6, 7),

    # ------------------------------------------------------ opportunities
    pos(markdown("h_opp", "## Opportunities — Specific, Sized, Actionable"), 0, 73, 6, 1),
    pos(markdown("n_opp",
        "*Five findings below cross-cut the tables above to answer "
        "\"what should we actually do,\" not just \"what happened.\" "
        "Each is backed by a table that rebuilds every pipeline run.*"), 0, 74, 6, 1),

    pos(chart("true_profit_chart", "true_profit", "product_name", "refund_pct_of_profit",
              "Products That Look Profitable But Are Net Losses After Returns"), 0, 75, 3, 7),
    pos(chart("targeting_chart", "targeting", "target_segment", "targeting_precision_pct",
              "Campaign Targeting Precision % (worst: New at 4%)"), 3, 75, 3, 7),

    pos(chart("delay_rating", "delay_impact", "delivery_outcome", "avg_rating",
              "Review Rating: On-time vs Delayed (returns unaffected)"), 0, 82, 3, 6),
    pos(chart("chan_eff_chart", "chan_eff", "channel", "revenue_per_rupee_spent",
              "Revenue per ₹1 Campaign Spend, by Channel"), 3, 82, 3, 6),

    pos(chart("discount_cancel", "discount_eff", "discount_band", "cancel_rate_pct",
              "Cancel Rate % by Discount Band — flat, discounting doesn't prevent cancellations"), 0, 88, 6, 6),

    # -------------------------------------------------------------- patterns
    pos(markdown("h_patterns", "## Pattern Analysis — Cohorts, RFM, Affinity, Seasonality"), 0, 94, 6, 1),
    pos(markdown("n_patterns",
        "*No free-text reviews exist in this dataset, so sentiment analysis "
        "below uses the structured rating/sentiment fields, not NLP on text. "
        "Everything else is derived purely from order behaviour.*"), 0, 95, 6, 1),

    pos(chart("cohort_chart", "cohort", "cohort_month", "retention_m1_pct",
              "Month-1 Retention % by Signup Cohort", widget_type="line", scale_x="temporal"), 0, 96, 3, 6),
    pos(chart("rfm_chart", "rfm", "customer_segment", "avg_recency_score",
              "RFM Recency Score by Segment — flat, unlike frequency/monetary"), 3, 96, 3, 6),

    pos(chart("affinity_chart", "affinity", "pair", "orders_together",
              "Top Category Pairs Bought Together (Fashion is the connector)"), 0, 102, 3, 7),
    pos(chart("season_chart", "season", "month_name", "orders",
              "Orders by Calendar Month — nearly 3x Jan to Dec", scale_x="categorical", sort_desc=False), 3, 102, 3, 7),

    pos(counter("c_repeat_pct", "repeat_timing", "pct_repeat_at_least_once", "% Customers Who Ever Repeat-Purchase"), 0, 109, 3, 3),
    pos(counter("c_median_days", "repeat_timing", "median_days_to_2nd_order", "Median Days to 2nd Order"), 3, 109, 3, 3),

    pos(markdown("n_sentiment",
        "*Rate and volume tell different stories: the left chart is worst by "
        "*percentage* (small categories with few reviews can top it on noise); "
        "the right chart is worst by *count* of negative reviews -- where "
        "support/QA effort actually has the most to fix.*"), 0, 112, 6, 1),
    pos(chart("sentiment_chart", "sentiment_cat", "category", "pct_negative",
              "% Negative Reviews by Category (worst 8 by rate)"), 0, 113, 3, 6),
    pos(chart("sentiment_vol_chart", "sentiment_vol", "category", "negative_reviews",
              "Negative Review Volume by Category (worst 8 by count)"), 3, 113, 3, 6),
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
