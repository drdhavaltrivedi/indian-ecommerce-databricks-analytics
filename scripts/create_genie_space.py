#!/usr/bin/env python3
"""Create/update an AI/BI Genie space over the Indian e-commerce gold layer.

Scoped to gold only, and given explicit instructions about the findings that are easy to
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
    "indian_ecommerce.gold.category_affinity",
    "indian_ecommerce.gold.cohort_retention",
    "indian_ecommerce.gold.repeat_purchase_timing",
    "indian_ecommerce.gold.rfm_segmentation",
    "indian_ecommerce.gold.seasonality_patterns",
    "indian_ecommerce.gold.sentiment_by_category",
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
    "indian_ecommerce.gold.loyalty_tier_parity",
    "indian_ecommerce.gold.acquisition_channel_funnel",
    "indian_ecommerce.gold.seasonality_by_year",
    "indian_ecommerce.gold.revenue_forecast",
    "indian_ecommerce.gold.forecast_accuracy",
    "indian_ecommerce.gold.reactivation_targets",
    "indian_ecommerce.gold.reactivation_summary",
]

INSTRUCTIONS = [
    "DATASET CONTEXT. This is a synthetic but internally consistent Indian "
    "e-commerce dataset (2023-2025): 100K orders, 25K customers, amounts in "
    "Indian Rupees. When reporting revenue or spend, use INR and prefer lakh "
    "(1,00,000) or crore (1,00,00,000) for large figures rather than raw "
    "rupee counts, since that is how these numbers are normally read in an "
    "Indian business context.",

    "DELIVERY DELAY NUANCE. gold.delay_impact_on_experience shows delayed "
    "shipments drop average review rating from 3.93 to 3.37, a real and "
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

    "PATTERN ANALYSIS TABLES. gold.cohort_retention shows signup-month cohorts "
    "and what pct reordered by month 1/3/6 -- retention decays from about 29% "
    "at month 1 to about 24% by month 3, not a flat number. "
    "gold.rfm_segmentation computes RFM scores independently from raw order "
    "data and averages them by the existing customer_segment label: frequency "
    "and monetary scores sort cleanly by segment (Premium highest) but "
    "recency scores are nearly flat across all segments -- this "
    "INDEPENDENTLY confirms that segment predicts spend, not how recently a "
    "customer is active, i.e. not churn risk. gold.category_affinity shows "
    "which categories are bought together in the same order; Fashion appears "
    "in nearly every top pair and is the natural cross-category bundling "
    "anchor, not just a category on its own. gold.seasonality_patterns "
    "aggregates order volume by month-of-year across ALL THREE years at once, "
    "which makes it LOOK like orders triple from January to December. That is "
    "an AGGREGATION ARTIFACT, not a seasonal pattern -- never use it for "
    "capacity, staffing or inventory planning. Use gold.seasonality_by_year "
    "instead, which splits by year: 2023 is a launch ramp (January starts at "
    "398 orders), 2024 is flat all year with no Q4 lift at all, and only 2025 "
    "surges in Q4 (December 9,590 orders vs 2,706 in December 2024). The "
    "'festival season peak' does NOT repeat in this data -- it happened once. "
    "gold.repeat_purchase_timing shows a median of 34 days to a customer's "
    "second order (mean is higher, about 74 days, pulled up by a long tail "
    "of slow repeaters) -- use the median for lifecycle-email timing, not "
    "the mean. gold.sentiment_by_category uses the STRUCTURED rating and "
    "review_sentiment fields; there is no free-text review column in this "
    "dataset, so never claim to have analyzed review text or done NLP "
    "sentiment analysis -- say the sentiment data is a pre-labeled category, "
    "not derived from text.",

    "GRAIN AND JOIN RULES. silver.fact_order_items is ONE ROW PER "
    "order_item_id, NOT one row per (order_id, product_id) -- 1,997 "
    "order+product pairs appear on more than one line item, so joining "
    "fact_order_items to fact_returns on that pair FANS OUT and "
    "double-counts revenue and refunds. Join on order_item_id, or aggregate "
    "each side to the (order_id, product_id) grain BEFORE joining. "
    "Each gold table is independently aggregated at "
    "its own grain -- do not join gold tables to each other, it will double "
    "count. gold.revenue_trends is one row per month; use it for trends. "
    "gold.segment_performance and gold.channel_efficiency are each one row "
    "per category value, not a time series.",

    "LOYALTY AND ACQUISITION NUANCE. gold.loyalty_tier_parity shows Platinum "
    "customers have spent 28x what Bronze customers have (Rs 5.17L vs Rs "
    "18.4K average), but delay_pct and churn_pct barely move across tiers "
    "(41.7-42.1% delay, 52.2-55.9% churn). Never say loyalty tier improves "
    "service or retention -- it tracks past spend only, not treatment. "
    "gold.acquisition_channel_funnel shows paid social channels (Facebook, "
    "Affiliate, Instagram, Influencer) have a HIGHER never_purchased_pct "
    "(10-12%) AND a LOWER avg_lifetime_spend (Rs 85-92K) than Referral/"
    "Direct-App (6.5-6.6% never-purchase, Rs 116-118K spend). Report both "
    "metrics together when asked which channel is 'best' -- a channel can "
    "look fine on campaign ROI (gold.channel_efficiency) while still "
    "underperforming on conversion and lifetime value; they are different "
    "questions.",

    "FORECASTING RULES. gold.revenue_forecast is a 6-month forward forecast "
    "with 95% prediction intervals. NEVER quote the point estimate alone -- "
    "always give the interval too, because it is wide (roughly Rs 5-22 crore "
    "on a Rs 12 crore central estimate). gold.forecast_accuracy holds the "
    "backtest that justifies that caution: trained on 2023-2024 and tested "
    "against actual 2025, overall error is about 17%, but that average hides "
    "the failure mode -- January to September errors are 0-23%, while October "
    "and November errors are 50-55% AND fall OUTSIDE the model's own 95% "
    "interval. The model fits a near-linear trend and cannot anticipate a "
    "structural break. So: treat the forecast as reliable for steady-state "
    "months, and as a FLOOR rather than a centre whenever a surge may be "
    "underway. If asked 'what will revenue be', give the range, state the "
    "backtest error, and say the model would miss another Q4-2025-style "
    "surge. Do not present forecasts as fact.",

    "REACTIVATION TARGETING. gold.reactivation_targets flags repeat customers "
    "who are overdue for their next order, measured against EACH CUSTOMER'S "
    "OWN average gap between orders -- not a global average, which would "
    "wrongly label naturally-infrequent buyers as churning. Tiers 1-3 (just "
    "due, slipping, high risk) total about 3,400 customers and Rs 40 crore of "
    "lifetime value and are the realistic outreach list. Tier 4 ('likely "
    "lost', 10,405 customers, Rs 138 crore) averages 555 days since last "
    "order -- around 18 months -- so treat it as a win-back experiment, not a "
    "reactivation campaign, and do not promise that value is recoverable.",
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
        space_id = api("POST", "/api/2.0/genie/spaces", body)["space_id"    "FORECASTING RULES. gold.revenue_forecast is a 6-month forward forecast "
    "with 95% prediction intervals. NEVER quote the point estimate alone -- "
    "always give the interval too, because it is wide (roughly Rs 5-22 crore "
    "on a Rs 12 crore central estimate). gold.forecast_accuracy holds the "
    "backtest that justifies that caution: trained on 2023-2024 and tested "
    "against actual 2025, overall error is about 17%, but that average hides "
    "the failure mode -- January to September errors are 0-23%, while October "
    "and November errors are 50-55% AND fall OUTSIDE the model's own 95% "
    "interval. The model fits a near-linear trend and cannot anticipate a "
    "structural break. So: treat the forecast as reliable for steady-state "
    "months, and as a FLOOR rather than a centre whenever a surge may be "
    "underway. If asked 'what will revenue be', give the range, state the "
    "backtest error, and say the model would miss another Q4-2025-style "
    "surge. Do not present forecasts as fact.",

    "REACTIVATION TARGETING. gold.reactivation_targets flags repeat customers "
    "who are overdue for their next order, measured against EACH CUSTOMER'S "
    "OWN average gap between orders -- not a global average, which would "
    "wrongly label naturally-infrequent buyers as churning. Tiers 1-3 (just "
    "due, slipping, high risk) total about 3,400 customers and Rs 40 crore of "
    "lifetime value and are the realistic outreach list. Tier 4 ('likely "
    "lost', 10,405 customers, Rs 138 crore) averages 555 days since last "
    "order -- around 18 months -- so treat it as a win-back experiment, not a "
    "reactivation campaign, and do not promise that value is recoverable.",
]
        print("Created Genie space:", space_id)

    print(f"  tables:       {len(TABLES)}")
    print(f"  instructions: {len(INSTRUCTIONS)}")
    print(f"URL: {HOST}/genie/rooms/{space_id}")
