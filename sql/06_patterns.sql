-- Pattern analysis: cohort retention, RFM, market-basket affinity,
-- seasonality, and repeat-purchase timing. Complements 04_opportunities.sql
-- (which answers "what's broken") with a different lens: "what shape does
-- customer behaviour take, and does it match what we assume."
--
-- No free-text review column exists in the source (only a pre-labeled
-- review_sentiment category and a numeric rating), so this does not attempt
-- NLP/text sentiment analysis -- it goes deeper on the structured sentiment
-- data instead (by category, by month) rather than pretending to mine text
-- that isn't there.

-- ---------------------------------------------------------------------------
-- 1. COHORT RETENTION: does a customer who signs up keep ordering?
--
-- Real decay curve, not a flat retention number: ~29% of a signup cohort
-- places another order within 1 month, dropping to ~24% by month 3. That's
-- the shape a single churn-rate KPI (see gold.segment_performance) can't show.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE indian_ecommerce.gold.cohort_retention
COMMENT 'Signup-month cohorts and what pct placed another order in month+1/+3/+6. Shows the retention decay curve behind the single churn-rate number in segment_performance.'
AS
WITH cohort AS (
  SELECT customer_id, DATE_TRUNC('MONTH', signup_date) AS cohort_month
  FROM indian_ecommerce.silver.dim_customer
),
activity AS (
  SELECT customer_id, DATE_TRUNC('MONTH', order_date) AS order_month
  FROM indian_ecommerce.silver.fact_orders
  WHERE order_status <> 'Cancelled'
)
SELECT
  c.cohort_month,
  COUNT(DISTINCT c.customer_id) AS cohort_size,
  COUNT(DISTINCT CASE WHEN MONTHS_BETWEEN(a.order_month, c.cohort_month) = 1 THEN a.customer_id END) AS active_month_1,
  COUNT(DISTINCT CASE WHEN MONTHS_BETWEEN(a.order_month, c.cohort_month) = 3 THEN a.customer_id END) AS active_month_3,
  COUNT(DISTINCT CASE WHEN MONTHS_BETWEEN(a.order_month, c.cohort_month) = 6 THEN a.customer_id END) AS active_month_6,
  ROUND(COUNT(DISTINCT CASE WHEN MONTHS_BETWEEN(a.order_month, c.cohort_month) = 1 THEN a.customer_id END) * 100.0
        / NULLIF(COUNT(DISTINCT c.customer_id), 0), 1) AS retention_m1_pct,
  ROUND(COUNT(DISTINCT CASE WHEN MONTHS_BETWEEN(a.order_month, c.cohort_month) = 3 THEN a.customer_id END) * 100.0
        / NULLIF(COUNT(DISTINCT c.customer_id), 0), 1) AS retention_m3_pct
FROM cohort c
LEFT JOIN activity a ON a.customer_id = c.customer_id
GROUP BY c.cohort_month
ORDER BY c.cohort_month;

-- ---------------------------------------------------------------------------
-- 2. RFM SCORING, VALIDATED AGAINST THE GIVEN customer_segment LABEL.
--
-- Computed independently from raw order behaviour (recency/frequency/
-- monetary quartiles), then averaged by the segment label already on the
-- customer record. Frequency and monetary scores sort cleanly with segment
-- (Premium highest, New lowest) -- the label is doing real work there. Recency
-- scores are nearly flat across segments (2.29-2.69 of 4), which independently
-- confirms the earlier finding that segment does not predict how recently
-- active someone is, i.e. does not predict churn risk.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE indian_ecommerce.gold.rfm_segmentation
COMMENT 'RFM scores (1-4 quartiles) computed from raw order behaviour, averaged by the pre-existing customer_segment label. Segment sorts cleanly on frequency/monetary but not recency -- independent confirmation that segment predicts spend, not retention.'
AS
WITH rfm_base AS (
  SELECT
    customer_id,
    DATEDIFF(CURRENT_DATE(), MAX(order_date)) AS recency_days,
    COUNT(*) AS frequency,
    SUM(final_amount) AS monetary
  FROM indian_ecommerce.silver.fact_orders
  WHERE order_status <> 'Cancelled'
  GROUP BY customer_id
),
scored AS (
  SELECT
    customer_id, recency_days, frequency, monetary,
    NTILE(4) OVER (ORDER BY recency_days DESC) AS recency_score,   -- 4 = most recent
    NTILE(4) OVER (ORDER BY frequency ASC)     AS frequency_score, -- 4 = most frequent
    NTILE(4) OVER (ORDER BY monetary ASC)      AS monetary_score   -- 4 = highest spend
  FROM rfm_base
)
SELECT
  c.customer_segment,
  COUNT(*) AS customers,
  ROUND(AVG(s.recency_days), 0) AS avg_recency_days,
  ROUND(AVG(s.recency_score), 2) AS avg_recency_score,
  ROUND(AVG(s.frequency_score), 2) AS avg_frequency_score,
  ROUND(AVG(s.monetary_score), 2) AS avg_monetary_score,
  ROUND(AVG(s.recency_score + s.frequency_score + s.monetary_score), 2) AS avg_rfm_total
FROM scored s
JOIN indian_ecommerce.silver.dim_customer c ON c.customer_id = s.customer_id
GROUP BY c.customer_segment
ORDER BY avg_monetary_score DESC;

-- ---------------------------------------------------------------------------
-- 3. MARKET-BASKET AFFINITY: which categories get bought in the same order?
--
-- Fashion appears in nearly every top pair -- it is the connective category
-- across the whole catalog, not just a category in its own right. That makes
-- it the natural anchor for cross-category bundling, independent of the
-- margin story in gold.category_performance.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE indian_ecommerce.gold.category_affinity
COMMENT 'Category pairs bought in the same order, ranked by co-occurrence. Fashion appears in nearly every top pair -- the natural cross-category bundling anchor.'
AS
WITH order_categories AS (
  SELECT DISTINCT oi.order_id, p.category
  FROM indian_ecommerce.silver.fact_order_items oi
  JOIN indian_ecommerce.silver.dim_product p ON p.product_id = oi.product_id
)
SELECT
  a.category AS category_a,
  b.category AS category_b,
  COUNT(*) AS orders_together
FROM order_categories a
JOIN order_categories b ON a.order_id = b.order_id AND a.category < b.category
GROUP BY a.category, b.category
ORDER BY orders_together DESC;

-- ---------------------------------------------------------------------------
-- 4. SEASONALITY: orders nearly triple from January to December.
--
-- A steady ramp, not a single spike -- the steepest single jump is Sep->Oct
-- (+40%), consistent with the festival season (Navratri/Dussehra/Diwali fall
-- in Sep-Nov) building into year-end. Anyone reading a flat monthly average
-- from gold.revenue_trends without this table would badly under-provision
-- Q4 inventory and delivery capacity.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE indian_ecommerce.gold.seasonality_patterns
COMMENT 'Order volume and AOV by calendar month, aggregated across all years. Orders nearly triple January to December -- a steady Q4 ramp, not a single spike.'
AS
SELECT
  MONTH(order_date) AS month_num,
  DATE_FORMAT(order_date, 'MMMM') AS month_name,
  COUNT(*) AS orders,
  ROUND(AVG(final_amount), 0) AS avg_order_value,
  ROUND(SUM(final_amount) / 1e7, 1) AS revenue_cr
FROM indian_ecommerce.silver.fact_orders
WHERE order_status <> 'Cancelled'
GROUP BY MONTH(order_date), DATE_FORMAT(order_date, 'MMMM')
ORDER BY month_num;

-- ---------------------------------------------------------------------------
-- 5. REPEAT-PURCHASE TIMING: how long until a customer's second order?
--
-- Median 34 days, mean 73.9 days (a long tail of slow repeaters pulling the
-- average up), and 73% of all customers (18,254 of 25,000) eventually place a
-- second order. The median is the number to use for lifecycle-email timing --
-- a "come back" nudge scheduled around day 30-35 targets the point where the
-- typical repeat customer is already returning, not before it.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE indian_ecommerce.gold.repeat_purchase_timing
COMMENT 'Days between a customers first and second order. Median is the number to use for lifecycle-email timing -- mean is inflated by a long tail of slow repeaters.'
AS
WITH ranked AS (
  SELECT customer_id, order_date,
    ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY order_date) AS order_seq
  FROM indian_ecommerce.silver.fact_orders
  WHERE order_status <> 'Cancelled'
),
gaps AS (
  SELECT a.customer_id, DATEDIFF(b.order_date, a.order_date) AS days_to_repeat
  FROM ranked a
  JOIN ranked b ON a.customer_id = b.customer_id AND b.order_seq = a.order_seq + 1
  WHERE a.order_seq = 1
)
SELECT
  (SELECT COUNT(*) FROM indian_ecommerce.silver.dim_customer) AS total_customers,
  COUNT(*) AS customers_with_2nd_order,
  ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM indian_ecommerce.silver.dim_customer), 1) AS pct_repeat_at_least_once,
  ROUND(AVG(days_to_repeat), 1) AS avg_days_to_2nd_order,
  ROUND(PERCENTILE(days_to_repeat, 0.5), 0) AS median_days_to_2nd_order,
  ROUND(PERCENTILE(days_to_repeat, 0.25), 0) AS p25_days,
  ROUND(PERCENTILE(days_to_repeat, 0.75), 0) AS p75_days
FROM gaps;

-- ---------------------------------------------------------------------------
-- 6. SENTIMENT DEEP DIVE: rating and negative-review rate by category.
--
-- No free-text review column exists in the source, so this works with the
-- structured fields that do (rating, review_sentiment) rather than attempting
-- NLP on text that isn't there. Musical Instruments and Furniture stand out
-- with the highest negative-review share -- categories where fit, quality
-- expectations, or damage-in-transit are hardest to get right sight unseen.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE indian_ecommerce.gold.sentiment_by_category
COMMENT 'Average rating and pct-negative review share by product category. No free-text reviews exist in the source -- this uses the structured rating/sentiment fields.'
AS
SELECT
  p.category,
  COUNT(*) AS reviews,
  ROUND(AVG(r.rating), 2) AS avg_rating,
  SUM(CASE WHEN r.review_sentiment = 'Negative' THEN 1 ELSE 0 END) AS negative_reviews,
  ROUND(SUM(CASE WHEN r.review_sentiment = 'Negative' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS pct_negative
FROM indian_ecommerce.silver.fact_reviews r
JOIN indian_ecommerce.silver.dim_product p ON p.product_id = r.product_id
GROUP BY p.category
ORDER BY pct_negative DESC;
