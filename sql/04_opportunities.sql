-- Opportunity analysis: findings that identify a specific fixable problem,
-- size it, and point at a decision. The gold.* tables above describe what
-- happened; these describe what to do about it.

-- ---------------------------------------------------------------------------
-- 1. PRODUCTS THAT LOOK PROFITABLE BUT ARE NET LOSSES AFTER RETURNS.
--
-- Standard product P&L (order_items.profit) never nets against refunds, so a
-- product can show healthy profit while quietly losing money once returns are
-- counted. The worst cases here have refunds at 5-22x their recorded profit.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE indian_ecommerce.gold.product_true_profitability
COMMENT 'Product profit from order_items netted against refunds from returns. A product with refund_pct_of_profit > 100 is a net loss despite showing profit in a standard P&L.'
AS
WITH prof AS (
  SELECT product_id, SUM(profit) AS gross_profit, SUM(item_revenue) AS revenue, SUM(quantity) AS units_sold
  FROM indian_ecommerce.silver.fact_order_items GROUP BY product_id
),
ret AS (
  SELECT product_id, COUNT(*) AS return_count, SUM(refund_amount) AS total_refunded
  FROM indian_ecommerce.silver.fact_returns GROUP BY product_id
)
SELECT
  p.product_id, p.product_name, p.category, p.brand,
  pr.units_sold,
  ROUND(pr.gross_profit, 0) AS gross_profit,
  COALESCE(r.return_count, 0) AS return_count,
  ROUND(COALESCE(r.total_refunded, 0), 0) AS total_refunded,
  ROUND(pr.gross_profit - COALESCE(r.total_refunded, 0), 0) AS net_profit_after_refunds,
  ROUND(COALESCE(r.total_refunded, 0) * 100.0 / NULLIF(pr.gross_profit, 0), 1) AS refund_pct_of_profit
FROM prof pr
JOIN indian_ecommerce.silver.dim_product p ON p.product_id = pr.product_id
LEFT JOIN ret r ON r.product_id = pr.product_id
ORDER BY refund_pct_of_profit DESC NULLS LAST;

-- ---------------------------------------------------------------------------
-- 2. CAMPAIGN TARGETING BARELY REACHES ITS TARGET SEGMENT.
--
-- A campaign with target_segment = 'New' should skew heavily toward new
-- customers. It reaches New customers only 3.98% of the time. Even the best
-- case (Regular-targeted campaigns reaching Regular customers) hits 52.32% --
-- barely better than chance given four segments exist.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE indian_ecommerce.gold.campaign_targeting_precision
COMMENT 'For campaigns with a specific target_segment, the pct of resulting orders that actually came from that segment. Low precision means targeting is not working as designed.'
AS
WITH matched AS (
  SELECT
    c.target_segment,
    cust.customer_segment AS actual_segment,
    COUNT(*) AS orders
  FROM indian_ecommerce.silver.fact_orders o
  JOIN indian_ecommerce.silver.dim_campaign c ON o.campaign_id = c.campaign_id
  JOIN indian_ecommerce.silver.dim_customer cust ON o.customer_id = cust.customer_id
  WHERE c.target_segment <> 'All'
  GROUP BY c.target_segment, cust.customer_segment
),
totals AS (
  SELECT target_segment, SUM(orders) AS total_orders
  FROM matched GROUP BY target_segment
)
SELECT
  m.target_segment,
  t.total_orders,
  SUM(CASE WHEN m.actual_segment = m.target_segment THEN m.orders ELSE 0 END) AS matched_orders,
  ROUND(SUM(CASE WHEN m.actual_segment = m.target_segment THEN m.orders ELSE 0 END) * 100.0
        / t.total_orders, 2) AS targeting_precision_pct
FROM matched m
JOIN totals t ON t.target_segment = m.target_segment
GROUP BY m.target_segment, t.total_orders
ORDER BY targeting_precision_pct DESC;

-- ---------------------------------------------------------------------------
-- 3. DELAYED DELIVERY HURTS SATISFACTION BUT NOT THE RETURN RATE.
--
-- A delayed shipment drops the average review rating from 3.93 to 3.37 -- a
-- real, meaningful gap. But the return rate is essentially unchanged (10.08%
-- vs 10.45%). The two effects are DIFFERENT costs: delay does not create
-- direct refund cost, it creates a reputation/repeat-purchase risk that a
-- return-rate KPI alone would completely miss.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE indian_ecommerce.gold.delay_impact_on_experience
COMMENT 'Review rating and return rate for delayed vs on-time shipments, at the order level. Delay depresses rating meaningfully; it does not measurably change the return rate.'
AS
-- NOTE ON THE JOIN SHAPE. fact_reviews and fact_returns BOTH fan out on
-- order_id (77,530 review rows over 54,363 orders; 12,075 return rows over
-- 9,510 orders). Joining both directly to the order list builds a cartesian
-- product per order. That does not affect COUNT(DISTINCT ...) but it DOES
-- bias AVG(rating): every review is repeated once per return on the same
-- order, over-weighting orders that had returns. That bug was live here and
-- published 3.90/3.34 instead of the correct 3.93/3.37. Each side is now
-- collapsed to one row per order BEFORE joining.
WITH order_delay AS (
  SELECT order_id, MAX(delayed_flag) AS was_delayed
  FROM indian_ecommerce.silver.fact_shipments
  GROUP BY order_id
),
order_rating AS (
  SELECT order_id, AVG(rating) AS order_avg_rating
  FROM indian_ecommerce.silver.fact_reviews
  GROUP BY order_id
),
order_returned AS (
  SELECT DISTINCT order_id FROM indian_ecommerce.silver.fact_returns
)
SELECT
  CASE WHEN d.was_delayed = 1 THEN 'Delayed' ELSE 'On-time' END AS delivery_outcome,
  COUNT(*) AS orders,
  COUNT(r.order_id) AS orders_reviewed,
  ROUND(AVG(r.order_avg_rating), 2) AS avg_rating,
  COUNT(ret.order_id) AS orders_returned,
  ROUND(COUNT(ret.order_id) * 100.0 / COUNT(*), 2) AS return_rate_pct
FROM order_delay d
LEFT JOIN order_rating   r   ON r.order_id   = d.order_id
LEFT JOIN order_returned ret ON ret.order_id = d.order_id
GROUP BY d.was_delayed;

-- ---------------------------------------------------------------------------
-- 4. MARKETING CHANNELS RETURN WILDLY DIFFERENT VALUE PER RUPEE SPENT.
--
-- Direct/App returns Rs 6.20 of attributed revenue per Rs 1 of campaign cost.
-- Facebook returns Rs 1.08 -- barely above break-even. That is a 5.7x
-- efficiency gap sitting inside one marketing budget.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE indian_ecommerce.gold.channel_efficiency
COMMENT 'Revenue generated per rupee of campaign cost, by channel. A 5.7x gap exists between the best (Direct/App) and worst (Facebook) channel.'
AS
SELECT
  channel,
  COUNT(*) AS campaigns,
  ROUND(SUM(campaign_cost), 0) AS total_cost,
  ROUND(SUM(revenue_generated), 0) AS total_revenue_generated,
  ROUND(SUM(revenue_generated) / NULLIF(SUM(campaign_cost), 0), 2) AS revenue_per_rupee_spent
FROM indian_ecommerce.silver.dim_campaign
GROUP BY channel
ORDER BY revenue_per_rupee_spent DESC;

-- ---------------------------------------------------------------------------
-- 5. HEAVIER DISCOUNTS DO NOT REDUCE CANCELLATIONS -- THEY JUST COST MORE.
--
-- If discounting worked as a cancellation-prevention lever, cancel rate would
-- fall as discount rises. It does not: cancel rate is flat at ~8% across every
-- discount band, while AOV drops from Rs 29,033 (no discount) to Rs 21,951
-- (20%+ discount). The same shape of result -- discounting not visibly
-- preventing the behaviour it's meant to prevent -- shows up independently
-- on unrelated e-commerce datasets, which is worth taking seriously.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE indian_ecommerce.gold.discount_effectiveness
COMMENT 'Cancellation rate and AOV by discount band. Cancel rate is flat regardless of discount depth -- discounting is not preventing cancellations, only reducing order value.'
AS
SELECT
  CASE WHEN discount_percentage = 0  THEN '1. No discount'
       WHEN discount_percentage < 10 THEN '2. 1-10%'
       WHEN discount_percentage < 20 THEN '3. 10-20%'
       ELSE                              '4. 20%+' END AS discount_band,
  COUNT(*) AS orders,
  ROUND(AVG(final_amount), 0) AS avg_order_value,
  ROUND(SUM(CASE WHEN order_status = 'Cancelled' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS cancel_rate_pct
FROM indian_ecommerce.silver.fact_orders
GROUP BY discount_band
ORDER BY discount_band;
