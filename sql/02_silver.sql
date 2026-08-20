-- Silver layer: typed, conformed star schema, WITH validation.
-- This source data is already relationally consistent (single generator,
-- consistent FKs), so on this dataset every filter below rejects 0 rows --
-- but TRY_CAST + a WHERE filter (not plain CAST) is what actually protects
-- a future refresh from a bad row silently becoming NULL everywhere
-- downstream, or crashing the whole table build. Rejected rows are counted,
-- not silently dropped -- see silver.validation_rejects at the bottom.

CREATE OR REPLACE TABLE indian_ecommerce.silver.dim_customer AS
SELECT
  customer_id,
  TRY_CAST(customer_signup_date AS DATE) AS signup_date,
  gender,
  TRY_CAST(TRY_CAST(age AS DOUBLE) AS INT) AS age,  -- source stores age as "44.0"
  age_group,
  state, city, pincode_prefix,
  customer_segment,
  preferred_device,
  preferred_payment_method,
  acquisition_channel,
  TRY_CAST(total_orders AS INT) AS total_orders,
  TRY_CAST(total_spend AS DOUBLE) AS total_spend,
  TRY_CAST(last_order_date AS DATE) AS last_order_date,
  TRY_CAST(average_order_value AS DOUBLE) AS average_order_value,
  customer_status,
  loyalty_tier
FROM indian_ecommerce.bronze.customers
WHERE customer_id IS NOT NULL AND TRIM(customer_id) != '';

CREATE OR REPLACE TABLE indian_ecommerce.silver.dim_product AS
SELECT
  product_id, product_name, category, subcategory, brand,
  TRY_CAST(price AS DOUBLE) AS price,
  TRY_CAST(cost_price AS DOUBLE) AS cost_price,
  discount_range,
  TRY_CAST(rating_average AS DOUBLE) AS rating_average,
  TRY_CAST(rating_count AS INT) AS rating_count,
  TRY_CAST(stock_quantity AS INT) AS stock_quantity,
  TRY_CAST(product_launch_date AS DATE) AS product_launch_date,
  product_type,
  TRY_CAST(return_rate_baseline AS DOUBLE) AS return_rate_baseline
FROM indian_ecommerce.bronze.products
WHERE product_id IS NOT NULL AND TRIM(product_id) != ''
  AND TRY_CAST(price AS DOUBLE) >= 0
  AND TRY_CAST(cost_price AS DOUBLE) >= 0;

CREATE OR REPLACE TABLE indian_ecommerce.silver.dim_campaign AS
SELECT
  campaign_id, campaign_name, channel,
  TRY_CAST(campaign_start_date AS DATE) AS campaign_start_date,
  TRY_CAST(campaign_end_date AS DATE) AS campaign_end_date,
  campaign_type, target_segment,
  TRY_CAST(discount_percentage AS DOUBLE) AS discount_percentage,
  TRY_CAST(conversions AS INT) AS conversions,
  TRY_CAST(revenue_generated AS DOUBLE) AS revenue_generated,
  TRY_CAST(impressions AS INT) AS impressions,
  TRY_CAST(clicks AS INT) AS clicks,
  TRY_CAST(campaign_cost AS DOUBLE) AS campaign_cost,
  TRY_CAST(roi AS DOUBLE) AS roi
FROM indian_ecommerce.bronze.marketing_campaigns
WHERE campaign_id IS NOT NULL AND TRIM(campaign_id) != '';

CREATE OR REPLACE TABLE indian_ecommerce.silver.fact_orders AS
SELECT
  order_id, customer_id,
  TRY_CAST(order_date AS DATE) AS order_date,
  order_time,
  TRY_CAST(CONCAT(order_date,' ',order_time) AS TIMESTAMP) AS order_timestamp,
  order_status, shipping_method, delivery_city, delivery_state,
  NULLIF(coupon_code,'') AS coupon_code,
  TRY_CAST(discount_percentage AS DOUBLE) AS discount_percentage,
  marketing_channel,
  TRY_CAST(subtotal AS DOUBLE) AS subtotal,
  TRY_CAST(shipping_fee AS DOUBLE) AS shipping_fee,
  TRY_CAST(tax_amount AS DOUBLE) AS tax_amount,
  TRY_CAST(final_amount AS DOUBLE) AS final_amount,
  NULLIF(campaign_id,'') AS campaign_id
FROM indian_ecommerce.bronze.orders
WHERE order_id IS NOT NULL AND TRIM(order_id) != ''
  AND customer_id IS NOT NULL AND TRIM(customer_id) != ''
  AND TRY_CAST(order_date AS DATE) IS NOT NULL
  AND TRY_CAST(order_date AS DATE) <= CURRENT_DATE()
  AND TRY_CAST(final_amount AS DOUBLE) >= 0
  AND TRY_CAST(discount_percentage AS DOUBLE) BETWEEN 0 AND 100;

CREATE OR REPLACE TABLE indian_ecommerce.silver.fact_order_items AS
SELECT
  order_item_id, order_id, product_id,
  TRY_CAST(quantity AS INT) AS quantity,
  TRY_CAST(unit_price AS DOUBLE) AS unit_price,
  TRY_CAST(discount_percentage AS DOUBLE) AS discount_percentage,
  TRY_CAST(item_revenue AS DOUBLE) AS item_revenue,
  TRY_CAST(item_cost AS DOUBLE) AS item_cost,
  TRY_CAST(profit AS DOUBLE) AS profit
FROM indian_ecommerce.bronze.order_items
WHERE order_item_id IS NOT NULL AND TRIM(order_item_id) != ''
  AND order_id IS NOT NULL AND TRIM(order_id) != ''
  AND TRY_CAST(quantity AS INT) > 0
  AND TRY_CAST(unit_price AS DOUBLE) >= 0;

CREATE OR REPLACE TABLE indian_ecommerce.silver.fact_payments AS
SELECT
  payment_id, order_id,
  TRY_CAST(payment_date AS DATE) AS payment_date,
  payment_method, payment_status,
  TRY_CAST(amount_paid AS DOUBLE) AS amount_paid,
  TRY_CAST(transaction_fee AS DOUBLE) AS transaction_fee,
  TRY_CAST(refund_amount AS DOUBLE) AS refund_amount
FROM indian_ecommerce.bronze.payments
WHERE payment_id IS NOT NULL AND TRIM(payment_id) != ''
  AND order_id IS NOT NULL AND TRIM(order_id) != ''
  AND TRY_CAST(amount_paid AS DOUBLE) >= 0;

CREATE OR REPLACE TABLE indian_ecommerce.silver.fact_shipments AS
SELECT
  shipment_id, order_id, warehouse_city, delivery_city, shipping_method,
  TRY_CAST(dispatch_date AS DATE) AS dispatch_date,
  TRY_CAST(expected_delivery_date AS DATE) AS expected_delivery_date,
  TRY_CAST(actual_delivery_date AS DATE) AS actual_delivery_date,
  TRY_CAST(delivery_days AS DOUBLE) AS delivery_days,
  delivery_status,
  TRY_CAST(delayed_flag AS INT) AS delayed_flag
FROM indian_ecommerce.bronze.shipments
WHERE shipment_id IS NOT NULL AND TRIM(shipment_id) != ''
  AND order_id IS NOT NULL AND TRIM(order_id) != ''
  AND (delivery_days IS NULL OR TRY_CAST(delivery_days AS DOUBLE) >= 0);

CREATE OR REPLACE TABLE indian_ecommerce.silver.fact_returns AS
SELECT
  return_id, order_id, customer_id, product_id,
  TRY_CAST(return_date AS DATE) AS return_date,
  return_reason,
  TRY_CAST(refund_amount AS DOUBLE) AS refund_amount,
  return_status
FROM indian_ecommerce.bronze.returns
WHERE return_id IS NOT NULL AND TRIM(return_id) != ''
  AND order_id IS NOT NULL AND TRIM(order_id) != ''
  AND (refund_amount IS NULL OR TRY_CAST(refund_amount AS DOUBLE) >= 0);

CREATE OR REPLACE TABLE indian_ecommerce.silver.fact_reviews AS
SELECT
  review_id, order_id, customer_id, product_id,
  TRY_CAST(review_date AS DATE) AS review_date,
  TRY_CAST(rating AS INT) AS rating,
  review_sentiment,
  TRY_CAST(verified_purchase AS BOOLEAN) AS verified_purchase
FROM indian_ecommerce.bronze.customer_reviews
WHERE review_id IS NOT NULL AND TRIM(review_id) != ''
  AND order_id IS NOT NULL AND TRIM(order_id) != ''
  AND TRY_CAST(rating AS INT) BETWEEN 1 AND 5;

-- ---------------------------------------------------------------------------
-- Validation rejects: bronze row count vs. silver row count per table, so a
-- pipeline run makes it visible at a glance if any filter above actually
-- rejected something. On this dataset every row here should read 0.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE indian_ecommerce.silver.validation_rejects
COMMENT 'Bronze row count minus silver row count, per table. Nonzero means the WHERE filters in this file rejected rows on the most recent run -- check bronze.validation_log for which rule and column.'
AS
SELECT 'dim_customer' AS silver_table,
       (SELECT COUNT(*) FROM indian_ecommerce.bronze.customers) AS bronze_rows,
       (SELECT COUNT(*) FROM indian_ecommerce.silver.dim_customer) AS silver_rows,
       (SELECT COUNT(*) FROM indian_ecommerce.bronze.customers)
         - (SELECT COUNT(*) FROM indian_ecommerce.silver.dim_customer) AS rejected_rows
UNION ALL
SELECT 'dim_product',
       (SELECT COUNT(*) FROM indian_ecommerce.bronze.products),
       (SELECT COUNT(*) FROM indian_ecommerce.silver.dim_product),
       (SELECT COUNT(*) FROM indian_ecommerce.bronze.products)
         - (SELECT COUNT(*) FROM indian_ecommerce.silver.dim_product)
UNION ALL
SELECT 'dim_campaign',
       (SELECT COUNT(*) FROM indian_ecommerce.bronze.marketing_campaigns),
       (SELECT COUNT(*) FROM indian_ecommerce.silver.dim_campaign),
       (SELECT COUNT(*) FROM indian_ecommerce.bronze.marketing_campaigns)
         - (SELECT COUNT(*) FROM indian_ecommerce.silver.dim_campaign)
UNION ALL
SELECT 'fact_orders',
       (SELECT COUNT(*) FROM indian_ecommerce.bronze.orders),
       (SELECT COUNT(*) FROM indian_ecommerce.silver.fact_orders),
       (SELECT COUNT(*) FROM indian_ecommerce.bronze.orders)
         - (SELECT COUNT(*) FROM indian_ecommerce.silver.fact_orders)
UNION ALL
SELECT 'fact_order_items',
       (SELECT COUNT(*) FROM indian_ecommerce.bronze.order_items),
       (SELECT COUNT(*) FROM indian_ecommerce.silver.fact_order_items),
       (SELECT COUNT(*) FROM indian_ecommerce.bronze.order_items)
         - (SELECT COUNT(*) FROM indian_ecommerce.silver.fact_order_items)
UNION ALL
SELECT 'fact_payments',
       (SELECT COUNT(*) FROM indian_ecommerce.bronze.payments),
       (SELECT COUNT(*) FROM indian_ecommerce.silver.fact_payments),
       (SELECT COUNT(*) FROM indian_ecommerce.bronze.payments)
         - (SELECT COUNT(*) FROM indian_ecommerce.silver.fact_payments)
UNION ALL
SELECT 'fact_shipments',
       (SELECT COUNT(*) FROM indian_ecommerce.bronze.shipments),
       (SELECT COUNT(*) FROM indian_ecommerce.silver.fact_shipments),
       (SELECT COUNT(*) FROM indian_ecommerce.bronze.shipments)
         - (SELECT COUNT(*) FROM indian_ecommerce.silver.fact_shipments)
UNION ALL
SELECT 'fact_returns',
       (SELECT COUNT(*) FROM indian_ecommerce.bronze.returns),
       (SELECT COUNT(*) FROM indian_ecommerce.silver.fact_returns),
       (SELECT COUNT(*) FROM indian_ecommerce.bronze.returns)
         - (SELECT COUNT(*) FROM indian_ecommerce.silver.fact_returns)
UNION ALL
SELECT 'fact_reviews',
       (SELECT COUNT(*) FROM indian_ecommerce.bronze.customer_reviews),
       (SELECT COUNT(*) FROM indian_ecommerce.silver.fact_reviews),
       (SELECT COUNT(*) FROM indian_ecommerce.bronze.customer_reviews)
         - (SELECT COUNT(*) FROM indian_ecommerce.silver.fact_reviews)
ORDER BY rejected_rows DESC;
