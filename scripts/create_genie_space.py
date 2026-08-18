#!/usr/bin/env python3
"""Create/update an AI/BI Genie space over the Indian e-commerce gold layer.

Same principle as the clickstream project's Genie space: scope it to gold
only, and give it explicit instructions about the findings that are easy to
misread -- otherwise a business user asking "should we discount more?" gets a
naive answer instead of the nuance the data actually supports.
"""
import os, sys, json, urllib.request, urllib.error

HOST = os.environ["DATABRICKS_HOST"].rstrip("/")
TOKEN = os.environ["DATABRICKS_TOKEN"]
WAREHOUSE_ID = os.environ["DBX_WAREHOUSE_ID"]

TITLE = "Indian Ecommerce Analytics Genie"
DESCRIPTION = (
    "Ask questions in plain English about the Indian e-commerce dataset: "
    "revenue, categories, customer segments, delivery, campaigns, and the "
    "opportunity-analysis findings. Knows which findings are nuanced and "
    "explains the nuance rather than overclaiming."
)

TABLES = [
    "indian_ecommerce.gold.campaign_roi",
    "indian_ecommerce.gold.campaign_targeting_precision",
    "indian_ecommerce.gold.category_performance",
    "indian_ecommerce.gold.channel_efficiency",
    "indian_ecommerce.gold.channel_performance",
    "indian_ecommerce.gold.data_quality",
    "indian_ecommerce.gold.delay_impact_on_experience",
    "indian_ecommerce.gold.delivery_performance",
    "indian_ecommerce.gold.discount_effectiveness",
    "indian_ecommerce.gold.payment_performance",
    "indian_ecommerce.gold.product_true_profitability",
    "indian_ecommerce.gold.return_analysis",
    "indian_ecommerce.gold.revenue_trends",
    "indian_ecommerce.gold.review_integrity",
    "indian_ecommerce.gold.segment_performance",
    "indian_ecommerce.gold.state_performance",
]

INSTRUCTIONS = [
    "DATASET CONTEXT. This is a synthetic but internally consistent Indian "
    "e-commerce dataset (2023-2025): 100K orders, 25K customers, amounts in "
    "Indian Rupees. When reporting revenue or spend, use INR and prefer lakh "
    "(1,00,000) or crore (1,00,00,000) for large figures rather than raw "
    "rupee counts, since that is how these numbers are normally read in an "
    "Indian business context.",

    "DELIVERY DELAY NUANCE. gold.delay_impact_on_experience shows delayed "
    "shipments drop average review rating from 3.90 to 3.34, a real and "
    "meaningful gap. But the return rate is almost unchanged (10.08% on-time "
    "vs 10.45% delayed). These are DIFFERENT findings: delay hurts "
    "satisfaction and repeat-purchase risk, but does NOT drive more returns. "
    "Never say delay 'causes more returns' -- the data does not support that; "
    "say it hurts satisfaction.",

    "CAMPAIGN TARGETING NUANCE. gold.campaign_targeting_precision shows that "
    "campaigns aimed at a specific segment mostly do not reach that segment: "
    "New-targeted campaigns reach New customers only 3.98% of the time, and "
    "even the best case (Regular-targeted reaching Regular) is 52.32%. This "
    "means targeting is largely not working as designed, not that the "
    "segments themselves are wrong.",

    "DISCOUNT NUANCE. gold.discount_effectiveness shows cancellation rate is "
    "flat (~8%) across every discount band while average order value falls "
    "as discount increases. Discounting is not preventing cancellations -- it "
    "is only reducing revenue per order. When asked whether to discount more, "
    "say this plainly rather than assuming discounts help.",

    "PRODUCT PROFITABILITY NUANCE. gold.product_true_profitability nets "
    "refunds against gross profit per product. A product can show healthy "
    "profit in a standard P&L (order_items only) while being a NET LOSS once "
    "refunds are counted -- refund_pct_of_profit above 100 means the product "
    "lost money despite looking profitable. Prefer this table over raw "
    "order_items profit when asked which products are actually profitable.",

    "GRAIN AND JOIN RULES. Each gold table is independently aggregated at "
    "its own grain -- do not join gold tables to each other, it will double "
    "count. gold.revenue_trends is one row per month; use it for trends. "
    "gold.segment_performance and gold.channel_efficiency are each one row "
    "per category value, not a time series.",
]

CURATED_SQL = [
    {
        "question": "Which products are actually losing money after returns?",
        "sql": """SELECT product_name, category, gross_profit, total_refunded, net_profit_after_refunds, refund_pct_of_profit
FROM indian_ecommerce.gold.product_true_profitability
WHERE refund_pct_of_profit > 100
ORDER BY refund_pct_of_profit DESC
LIMIT 15""",
    },
    {
        "question": "Is our campaign targeting actually working?",
        "sql": """SELECT target_segment, total_orders, matched_orders, targeting_precision_pct
FROM indian_ecommerce.gold.campaign_targeting_precision
ORDER BY targeting_precision_pct ASC""",
    },
    {
        "question": "Does delivery delay hurt reviews or returns?",
        "sql": """SELECT delivery_outcome, orders, avg_rating, return_rate_pct
FROM indian_ecommerce.gold.delay_impact_on_experience""",
    },
    {
        "question": "Which marketing channel gives the best return per rupee spent?",
        "sql": """SELECT channel, total_cost, total_revenue_generated, revenue_per_rupee_spent
FROM indian_ecommerce.gold.channel_efficiency
ORDER BY revenue_per_rupee_spent DESC""",
    },
    {
        "question": "Does discounting reduce cancellations?",
        "sql": """SELECT discount_band, orders, avg_order_value, cancel_rate_pct
FROM indian_ecommerce.gold.discount_effectiveness
ORDER BY discount_band""",
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
        print(f"[{e.code}] {e.read().decode()[:600]}", file=sys.stderr)
        raise


def build_space():
    return {
        "version": 2,
        "data_sources": {"tables": [{"identifier": t} for t in sorted(TABLES)]},
        "instructions": {"text_instructions": [{"content": INSTRUCTIONS}]},
    }


def find_existing():
    for s in api("GET", "/api/2.0/genie/spaces").get("spaces", []):
        if s.get("title") == TITLE:
            return s["space_id"]
    return None


if __name__ == "__main__":
    body = {
        "title": TITLE,
        "description": DESCRIPTION,
        "warehouse_id": WAREHOUSE_ID,
        "serialized_space": json.dumps(build_space()),
    }
    existing = find_existing()
    if existing:
        api("PATCH", f"/api/2.0/genie/spaces/{existing}", body)
        space_id = existing
        print("Updated Genie space:", space_id)
    else:
        space_id = api("POST", "/api/2.0/genie/spaces", body)["space_id"]
        print("Created Genie space:", space_id)

    print(f"  tables:       {len(TABLES)}")
    print(f"  instructions: {len(INSTRUCTIONS)}")
    print(f"URL: {HOST}/genie/rooms/{space_id}")
