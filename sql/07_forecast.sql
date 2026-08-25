-- Forecasting and forward-looking prediction.
--
-- Everything above this file describes what already happened. This file is
-- the first that makes claims about what happens NEXT -- which means it
-- carries a different burden of proof. Every forecast here ships with a
-- measured backtest accuracy (gold.forecast_accuracy) rather than a bare
-- point estimate, because a forecast without an error bar is a guess with
-- a decimal point.

-- ---------------------------------------------------------------------------
-- 1. CORRECTION: THERE IS NO REPEATING ANNUAL SEASONALITY.
--
-- gold.seasonality_patterns aggregates order volume by month-of-year across
-- ALL THREE years at once. That produces a clean-looking "orders nearly
-- triple from January to December" ramp -- and it is an artifact, not a
-- seasonal pattern. Splitting the same data by year shows why:
--
--     month   2023    2024    2025
--        1     398    2213    2558
--        9    2397    2030    3408
--       12    2613    2706    9590   <-- only 2025 spikes
--
-- 2023 is a launch ramp (January starts at 398 orders and climbs as the
-- business spins up). 2024 is flat all year -- no Q4 lift at all. 2025 is
-- flat until September and then surges. Averaging the three together blends
-- 2023's start-up ramp with 2025's Q4 surge and manufactures a "festival
-- season" that never repeats in the data.
--
-- This matters because the previous framing told planners to staff delivery
-- and inventory for a Sep-Nov peak every year. On this data that would have
-- been wrong in 2 of 3 years.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE indian_ecommerce.gold.seasonality_by_year
COMMENT 'Order volume and revenue by month, split BY YEAR rather than aggregated across years. Use this instead of gold.seasonality_patterns for any capacity or inventory decision: the aggregate view blends 2023 launch-ramp with a one-off 2025 Q4 surge and implies an annual seasonal pattern that does not repeat.'
AS
SELECT
  YEAR(order_date)  AS order_year,
  MONTH(order_date) AS month_num,
  DATE_FORMAT(order_date, 'MMMM') AS month_name,
  COUNT(*) AS orders,
  ROUND(SUM(final_amount) / 1e7, 2) AS revenue_cr,
  ROUND(AVG(final_amount), 0) AS avg_order_value
FROM indian_ecommerce.silver.fact_orders
GROUP BY YEAR(order_date), MONTH(order_date), DATE_FORMAT(order_date, 'MMMM')
ORDER BY order_year, month_num;

-- ---------------------------------------------------------------------------
-- 2. REVENUE AND ORDER-VOLUME FORECAST, 6 MONTHS FORWARD.
--
-- Uses Databricks' built-in AI_FORECAST over all 36 months. Read the
-- interval, not just the point estimate -- see gold.forecast_accuracy for
-- why the interval is the honest part of this table.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE indian_ecommerce.gold.revenue_forecast
COMMENT 'Six-month forward forecast of monthly revenue and order volume with 95% prediction intervals. ALWAYS read alongside gold.forecast_accuracy -- backtesting shows this model tracks stable periods well but badly under-predicts a structural surge like 2025 Q4.'
AS
WITH rev AS (
  SELECT * FROM AI_FORECAST(
    TABLE(
      SELECT DATE_TRUNC('MONTH', order_date) AS ds, SUM(final_amount) AS y
      FROM indian_ecommerce.silver.fact_orders GROUP BY 1
    ),
    horizon => '2026-07-01', time_col => 'ds', value_col => 'y')
),
ord AS (
  SELECT * FROM AI_FORECAST(
    TABLE(
      SELECT DATE_TRUNC('MONTH', order_date) AS ds, CAST(COUNT(*) AS DOUBLE) AS y
      FROM indian_ecommerce.silver.fact_orders GROUP BY 1
    ),
    horizon => '2026-07-01', time_col => 'ds', value_col => 'y')
)
SELECT
  DATE_FORMAT(r.ds, 'yyyy-MM') AS forecast_month,
  ROUND(r.y_forecast / 1e7, 2) AS revenue_cr_forecast,
  ROUND(r.y_lower    / 1e7, 2) AS revenue_cr_lower,
  ROUND(r.y_upper    / 1e7, 2) AS revenue_cr_upper,
  ROUND(o.y_forecast, 0)       AS orders_forecast,
  ROUND(o.y_lower, 0)          AS orders_lower,
  ROUND(o.y_upper, 0)          AS orders_upper
FROM rev r JOIN ord o ON o.ds = r.ds
ORDER BY r.ds;

-- ---------------------------------------------------------------------------
-- 3. FORECAST ACCURACY, MEASURED BY BACKTEST -- NOT ASSUMED.
--
-- Trains on 2023-2024 only, predicts 2025, compares to what actually
-- happened. Overall MAPE lands around 17%, but that single number hides the
-- important part: Jan-Sep 2025 errors are 0-23%, while Oct-Nov are 50-55%
-- AND fall outside the model's own 95% interval. The model fits a near-
-- linear trend and cannot see a structural break coming.
--
-- Practical reading: trust this forecast for steady-state months, treat it
-- as a floor (not a centre) whenever a surge may be underway.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE indian_ecommerce.gold.forecast_accuracy
COMMENT 'Backtest of the revenue forecast: trained on 2023-2024, evaluated against actual 2025. Per-month absolute pct error and whether the actual fell inside the 95% prediction interval. Published so the forecast is never read without its error bar.'
AS
WITH fc AS (
  SELECT * FROM AI_FORECAST(
    TABLE(
      SELECT DATE_TRUNC('MONTH', order_date) AS ds, SUM(final_amount) AS y
      FROM indian_ecommerce.silver.fact_orders
      WHERE order_date < '2025-01-01' GROUP BY 1
    ),
    horizon => '2025-12-01', time_col => 'ds', value_col => 'y')
),
act AS (
  SELECT DATE_TRUNC('MONTH', order_date) AS ds, SUM(final_amount) AS actual
  FROM indian_ecommerce.silver.fact_orders
  WHERE order_date >= '2025-01-01' GROUP BY 1
)
SELECT
  DATE_FORMAT(a.ds, 'yyyy-MM') AS eval_month,
  ROUND(a.actual      / 1e7, 2) AS actual_cr,
  ROUND(f.y_forecast  / 1e7, 2) AS forecast_cr,
  ROUND(ABS(f.y_forecast - a.actual) * 100.0 / a.actual, 1) AS abs_pct_error,
  CASE WHEN a.actual BETWEEN f.y_lower AND f.y_upper THEN true ELSE false END AS inside_95_interval
FROM act a JOIN fc f ON f.ds = a.ds
ORDER BY a.ds;

-- ---------------------------------------------------------------------------
-- 4. REACTIVATION TARGETS: WHO IS OVERDUE FOR THEIR NEXT ORDER.
--
-- This is the prediction that does not depend on the shaky trend above, and
-- is the most directly actionable thing in this file. For every customer
-- with 2+ orders, compute their OWN average gap between orders, then flag
-- how far past due they are relative to their own cadence -- not a global
-- average, which would mislabel naturally-infrequent buyers as churning.
--
-- Tiered so outreach can start with the highest-value, most-recoverable
-- segment rather than emailing 12.5K people at once.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE indian_ecommerce.gold.reactivation_targets
COMMENT 'Repeat customers who are overdue for their next order, measured against each customer own average inter-order gap rather than a global average. Tiered by how overdue and by lifetime value, so reactivation outreach can be prioritised.'
AS
WITH asof AS (
  SELECT MAX(order_date) AS ref_date FROM indian_ecommerce.silver.fact_orders
),
cust AS (
  SELECT
    o.customer_id,
    COUNT(*) AS orders,
    MAX(o.order_date) AS last_order_date,
    SUM(o.final_amount) AS lifetime_value,
    DATEDIFF(DAY, MIN(o.order_date), MAX(o.order_date)) * 1.0
      / NULLIF(COUNT(*) - 1, 0) AS avg_gap_days
  FROM indian_ecommerce.silver.fact_orders o
  GROUP BY o.customer_id
  HAVING COUNT(*) >= 2
),
scored AS (
  SELECT
    c.*,
    DATEDIFF(DAY, c.last_order_date, (SELECT ref_date FROM asof)) AS days_since_last_order,
    DATEDIFF(DAY, c.last_order_date, (SELECT ref_date FROM asof)) / c.avg_gap_days AS overdue_ratio
  FROM cust c
  WHERE c.avg_gap_days IS NOT NULL AND c.avg_gap_days > 0
)
SELECT
  s.customer_id,
  d.customer_segment,
  d.loyalty_tier,
  d.state,
  s.orders,
  s.last_order_date,
  s.days_since_last_order,
  ROUND(s.avg_gap_days, 0)   AS avg_gap_days,
  ROUND(s.overdue_ratio, 2)  AS overdue_ratio,
  ROUND(s.lifetime_value, 0) AS lifetime_value,
  CASE
    WHEN s.overdue_ratio >= 3.0 THEN '4. Likely lost (3x+ overdue)'
    WHEN s.overdue_ratio >= 2.0 THEN '3. High risk (2-3x overdue)'
    WHEN s.overdue_ratio >= 1.5 THEN '2. Slipping (1.5-2x overdue)'
    WHEN s.overdue_ratio >= 1.0 THEN '1. Just due (1-1.5x)'
    ELSE '0. On cadence'
  END AS reactivation_tier
FROM scored s
JOIN indian_ecommerce.silver.dim_customer d ON d.customer_id = s.customer_id
ORDER BY s.overdue_ratio DESC, s.lifetime_value DESC;

-- ---------------------------------------------------------------------------
-- 5. REACTIVATION SUMMARY: THE SIZED VERSION OF THE ABOVE.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE indian_ecommerce.gold.reactivation_summary
COMMENT 'gold.reactivation_targets rolled up by tier: how many customers sit in each overdue band and how much lifetime value each band represents.'
AS
SELECT
  reactivation_tier,
  COUNT(*) AS customers,
  ROUND(SUM(lifetime_value) / 1e7, 1) AS lifetime_value_cr,
  ROUND(AVG(lifetime_value), 0) AS avg_lifetime_value,
  ROUND(AVG(days_since_last_order), 0) AS avg_days_since_order
FROM indian_ecommerce.gold.reactivation_targets
GROUP BY reactivation_tier
ORDER BY reactivation_tier;
