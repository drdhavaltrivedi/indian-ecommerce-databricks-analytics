-- Gold layer: business-facing aggregates.

-- Revenue trend: monthly, with order volume and AOV
CREATE OR REPLACE TABLE indian_ecommerce.gold.revenue_trends AS
SELECT
  DATE_TRUNC('MONTH', order_date) AS month,
  COUNT(DISTINCT order_id) AS orders,
  COUNT(DISTINCT customer_id) AS unique_customers,
  ROUND(SUM(final_amount), 0) AS revenue,
  ROUND(AVG(final_amount), 0) AS avg_order_value,
  SUM(CASE WHEN order_status = 'Cancelled' THEN 1 ELSE 0 END) AS cancelled_orders,
  SUM(CASE WHEN order_status = 'Failed' THEN 1 ELSE 0 END) AS failed_orders,
  SUM(CASE WHEN order_status = 'Delivered' THEN 1 ELSE 0 END) AS delivered_orders,
  ROUND(SUM(CASE WHEN order_status = 'Delivered' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS delivered_pct
FROM indian_ecommerce.silver.fact_orders
GROUP BY DATE_TRUNC('MONTH', order_date)
ORDER BY month;

-- Category performance: revenue, profit margin, return exposure
CREATE OR REPLACE TABLE indian_ecommerce.gold.category_performance AS
SELECT
  p.category,
  COUNT(DISTINCT oi.order_id) AS orders,
  SUM(oi.quantity) AS units_sold,
  ROUND(SUM(oi.item_revenue), 0) AS revenue,
  ROUND(SUM(oi.profit), 0) AS profit,
  ROUND(SUM(oi.profit) * 100.0 / NULLIF(SUM(oi.item_revenue), 0), 2) AS margin_pct,
  ROUND(AVG(p.rating_average), 2) AS avg_rating
FROM indian_ecommerce.silver.fact_order_items oi
JOIN indian_ecommerce.silver.dim_product p ON oi.product_id = p.product_id
GROUP BY p.category
ORDER BY revenue DESC;

-- Customer segment performance: does the segment label predict value?
CREATE OR REPLACE TABLE indian_ecommerce.gold.segment_performance AS
SELECT
  customer_segment,
  COUNT(*) AS customers,
  ROUND(AVG(total_spend), 0) AS avg_lifetime_spend,
  ROUND(AVG(total_orders), 1) AS avg_orders,
  ROUND(AVG(average_order_value), 0) AS avg_order_value,
  SUM(CASE WHEN customer_status = 'Churned' THEN 1 ELSE 0 END) AS churned,
  ROUND(SUM(CASE WHEN customer_status = 'Churned' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS churn_rate_pct
FROM indian_ecommerce.silver.dim_customer
GROUP BY customer_segment
ORDER BY avg_lifetime_spend DESC;

-- Marketing channel performance: orders/revenue attributed to each channel
CREATE OR REPLACE TABLE indian_ecommerce.gold.channel_performance AS
SELECT
  marketing_channel,
  COUNT(*) AS orders,
  ROUND(SUM(final_amount), 0) AS revenue,
  ROUND(AVG(final_amount), 0) AS avg_order_value,
  ROUND(AVG(discount_percentage), 2) AS avg_discount_pct
FROM indian_ecommerce.silver.fact_orders
WHERE marketing_channel IS NOT NULL
GROUP BY marketing_channel
ORDER BY revenue DESC;

-- Campaign ROI ranking
CREATE OR REPLACE TABLE indian_ecommerce.gold.campaign_roi AS
SELECT
  campaign_id, campaign_name, channel, campaign_type, target_segment,
  conversions, impressions, clicks,
  ROUND(clicks * 100.0 / NULLIF(impressions, 0), 3) AS ctr_pct,
  ROUND(conversions * 100.0 / NULLIF(clicks, 0), 2) AS conversion_pct,
  ROUND(campaign_cost, 0) AS campaign_cost,
  ROUND(revenue_generated, 0) AS revenue_generated,
  roi
FROM indian_ecommerce.silver.dim_campaign
ORDER BY roi DESC;

-- Delivery performance: where are the delays?
CREATE OR REPLACE TABLE indian_ecommerce.gold.delivery_performance AS
SELECT
  warehouse_city,
  shipping_method,
  COUNT(*) AS shipments,
  ROUND(AVG(delivery_days), 2) AS avg_delivery_days,
  SUM(delayed_flag) AS delayed_shipments,
  ROUND(SUM(delayed_flag) * 100.0 / COUNT(*), 2) AS delay_rate_pct
FROM indian_ecommerce.silver.fact_shipments
GROUP BY warehouse_city, shipping_method
ORDER BY delay_rate_pct DESC;

-- Return analysis: reasons and category exposure
CREATE OR REPLACE TABLE indian_ecommerce.gold.return_analysis AS
SELECT
  p.category,
  r.return_reason,
  COUNT(*) AS returns,
  ROUND(SUM(r.refund_amount), 0) AS refunded_amount,
  ROUND(AVG(p.return_rate_baseline) * 100, 2) AS baseline_return_rate_pct
FROM indian_ecommerce.silver.fact_returns r
JOIN indian_ecommerce.silver.dim_product p ON r.product_id = p.product_id
GROUP BY p.category, r.return_reason
ORDER BY returns DESC;

-- Payment method reliability: failure rate and fees
CREATE OR REPLACE TABLE indian_ecommerce.gold.payment_performance AS
SELECT
  payment_method,
  COUNT(*) AS payments,
  SUM(CASE WHEN payment_status = 'Success' THEN 1 ELSE 0 END) AS successful,
  SUM(CASE WHEN payment_status = 'Failed' THEN 1 ELSE 0 END) AS failed,
  ROUND(SUM(CASE WHEN payment_status = 'Failed' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS failure_rate_pct,
  ROUND(AVG(transaction_fee), 2) AS avg_transaction_fee,
  ROUND(SUM(refund_amount), 0) AS total_refunded
FROM indian_ecommerce.silver.fact_payments
GROUP BY payment_method
ORDER BY failure_rate_pct DESC;

-- Geographic performance: state-level revenue
CREATE OR REPLACE TABLE indian_ecommerce.gold.state_performance AS
SELECT
  delivery_state,
  COUNT(*) AS orders,
  ROUND(SUM(final_amount), 0) AS revenue,
  ROUND(AVG(final_amount), 0) AS avg_order_value
FROM indian_ecommerce.silver.fact_orders
GROUP BY delivery_state
ORDER BY revenue DESC;

-- Review sentiment vs verified purchase -- are unverified reviews skewing ratings?
CREATE OR REPLACE TABLE indian_ecommerce.gold.review_integrity AS
SELECT
  verified_purchase,
  review_sentiment,
  COUNT(*) AS reviews,
  ROUND(AVG(rating), 2) AS avg_rating
FROM indian_ecommerce.silver.fact_reviews
GROUP BY verified_purchase, review_sentiment
ORDER BY verified_purchase DESC, reviews DESC;

-- Data quality: known checks, same principle as the ecommerce project --
-- surface defects as a queryable table, not a footnote.
--
-- Written as CTEs that each compute one count, rather than a UNION of
-- correlated subqueries: the latter triggered a Spark SQL optimizer internal
-- error on this query shape, and precomputing each count separately avoids it.
CREATE OR REPLACE TABLE indian_ecommerce.gold.data_quality AS
WITH totals AS (
  SELECT COUNT(*) AS total_orders FROM indian_ecommerce.silver.fact_orders
),
delivered_totals AS (
  SELECT COUNT(*) AS n FROM indian_ecommerce.silver.fact_orders WHERE order_status = 'Delivered'
),
failed_totals AS (
  SELECT COUNT(*) AS n FROM indian_ecommerce.silver.fact_orders WHERE order_status = 'Failed'
),
orders_without_payment AS (
  SELECT COUNT(*) AS n
  FROM indian_ecommerce.silver.fact_orders o
  LEFT JOIN indian_ecommerce.silver.fact_payments p ON p.order_id = o.order_id
  WHERE p.order_id IS NULL
),
delivered_without_shipment AS (
  SELECT COUNT(*) AS n
  FROM indian_ecommerce.silver.fact_orders o
  LEFT JOIN indian_ecommerce.silver.fact_shipments s ON s.order_id = o.order_id
  WHERE o.order_status = 'Delivered' AND s.order_id IS NULL
),
failed_orders_with_payment AS (
  SELECT COUNT(*) AS n
  FROM indian_ecommerce.silver.fact_orders o
  JOIN indian_ecommerce.silver.fact_payments p ON p.order_id = o.order_id
  WHERE o.order_status = 'Failed' AND p.payment_status = 'Success'
),
zero_amount AS (
  SELECT COUNT(*) AS n FROM indian_ecommerce.silver.fact_orders WHERE final_amount = 0
),
future_dated_orders AS (
  SELECT COUNT(*) AS n FROM indian_ecommerce.silver.fact_orders WHERE order_date > CURRENT_DATE()
),
delivery_before_dispatch AS (
  SELECT COUNT(*) AS n
  FROM indian_ecommerce.silver.fact_shipments
  WHERE actual_delivery_date IS NOT NULL AND dispatch_date IS NOT NULL
    AND actual_delivery_date < dispatch_date
),
duplicate_order_ids AS (
  SELECT COUNT(*) AS n FROM (
    SELECT order_id FROM indian_ecommerce.silver.fact_orders
    GROUP BY order_id HAVING COUNT(*) > 1
  )
),
orphaned_order_items AS (
  SELECT COUNT(*) AS n
  FROM indian_ecommerce.silver.fact_order_items oi
  LEFT JOIN indian_ecommerce.silver.dim_product p ON p.product_id = oi.product_id
  WHERE p.product_id IS NULL
)
SELECT 'orders_without_payment' AS check_name,
       'Orders with no matching payment record' AS description,
       n AS affected_rows,
       ROUND(n * 100.0 / (SELECT total_orders FROM totals), 2) AS pct_affected
FROM orders_without_payment

UNION ALL
SELECT 'delivered_without_shipment',
       'Orders marked Delivered with no shipment record',
       n,
       ROUND(n * 100.0 / NULLIF((SELECT n FROM delivered_totals), 0), 2)
FROM delivered_without_shipment

UNION ALL
SELECT 'failed_orders_with_payment',
       'Orders marked Failed but with a successful payment recorded',
       n,
       ROUND(n * 100.0 / NULLIF((SELECT n FROM failed_totals), 0), 2)
FROM failed_orders_with_payment

UNION ALL
SELECT 'zero_final_amount',
       'Orders with a final_amount of zero',
       n,
       ROUND(n * 100.0 / (SELECT total_orders FROM totals), 2)
FROM zero_amount

UNION ALL
SELECT 'future_dated_orders',
       'Orders with an order_date after today -- impossible, flags a source or type-parsing bug',
       n,
       ROUND(n * 100.0 / (SELECT total_orders FROM totals), 2)
FROM future_dated_orders

UNION ALL
SELECT 'delivery_before_dispatch',
       'Shipments where actual_delivery_date is before dispatch_date -- impossible sequence',
       n,
       ROUND(n * 100.0 / (SELECT COUNT(*) FROM indian_ecommerce.silver.fact_shipments), 2)
FROM delivery_before_dispatch

UNION ALL
SELECT 'duplicate_order_ids',
       'order_id values appearing more than once in fact_orders -- breaks the star-schema PK assumption',
       n,
       ROUND(n * 100.0 / (SELECT total_orders FROM totals), 2)
FROM duplicate_order_ids

UNION ALL
SELECT 'orphaned_order_items',
       'Order line items referencing a product_id not present in dim_product',
       n,
       ROUND(n * 100.0 / (SELECT COUNT(*) FROM indian_ecommerce.silver.fact_order_items), 2)
FROM orphaned_order_items

ORDER BY pct_affected DESC;
