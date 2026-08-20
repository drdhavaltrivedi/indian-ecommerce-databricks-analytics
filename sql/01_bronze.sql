-- Bronze layer: raw ingestion, minimal transformation, full fidelity.
-- Every column STRING: if a downstream number looks wrong, bronze is the
-- reference to check against, and casting at ingest would destroy that
-- evidence.

CREATE TABLE IF NOT EXISTS indian_ecommerce.bronze.customers (
  customer_id STRING, customer_signup_date STRING, gender STRING, age STRING,
  age_group STRING, state STRING, city STRING, pincode_prefix STRING,
  customer_segment STRING, preferred_device STRING, preferred_payment_method STRING,
  acquisition_channel STRING, total_orders STRING, total_spend STRING,
  last_order_date STRING, average_order_value STRING, customer_status STRING,
  loyalty_tier STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS indian_ecommerce.bronze.products (
  product_id STRING, product_name STRING, category STRING, subcategory STRING,
  brand STRING, price STRING, cost_price STRING, discount_range STRING,
  rating_average STRING, rating_count STRING, stock_quantity STRING,
  product_launch_date STRING, product_type STRING, return_rate_baseline STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS indian_ecommerce.bronze.orders (
  order_id STRING, customer_id STRING, order_date STRING, order_time STRING,
  order_status STRING, shipping_method STRING, delivery_city STRING,
  delivery_state STRING, coupon_code STRING, discount_percentage STRING,
  marketing_channel STRING, subtotal STRING, shipping_fee STRING,
  tax_amount STRING, final_amount STRING, campaign_id STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS indian_ecommerce.bronze.order_items (
  order_item_id STRING, order_id STRING, product_id STRING, quantity STRING,
  unit_price STRING, discount_percentage STRING, item_revenue STRING,
  item_cost STRING, profit STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS indian_ecommerce.bronze.payments (
  payment_id STRING, order_id STRING, payment_date STRING, payment_method STRING,
  payment_status STRING, amount_paid STRING, transaction_fee STRING, refund_amount STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS indian_ecommerce.bronze.shipments (
  shipment_id STRING, order_id STRING, warehouse_city STRING, delivery_city STRING,
  shipping_method STRING, dispatch_date STRING, expected_delivery_date STRING,
  actual_delivery_date STRING, delivery_days STRING, delivery_status STRING, delayed_flag STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS indian_ecommerce.bronze.returns (
  return_id STRING, order_id STRING, customer_id STRING, product_id STRING,
  return_date STRING, return_reason STRING, refund_amount STRING, return_status STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS indian_ecommerce.bronze.customer_reviews (
  review_id STRING, order_id STRING, customer_id STRING, product_id STRING,
  review_date STRING, rating STRING, review_sentiment STRING, verified_purchase STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS indian_ecommerce.bronze.marketing_campaigns (
  campaign_id STRING, campaign_name STRING, channel STRING, campaign_start_date STRING,
  campaign_end_date STRING, campaign_type STRING, target_segment STRING,
  discount_percentage STRING, conversions STRING, revenue_generated STRING,
  impressions STRING, clicks STRING, campaign_cost STRING, roi STRING
) USING DELTA;

COPY INTO indian_ecommerce.bronze.customers FROM '/Volumes/indian_ecommerce/bronze/raw_files/customers.csv'
  FILEFORMAT = CSV FORMAT_OPTIONS ('header'='true');
COPY INTO indian_ecommerce.bronze.products FROM '/Volumes/indian_ecommerce/bronze/raw_files/products.csv'
  FILEFORMAT = CSV FORMAT_OPTIONS ('header'='true');
COPY INTO indian_ecommerce.bronze.orders FROM '/Volumes/indian_ecommerce/bronze/raw_files/orders.csv'
  FILEFORMAT = CSV FORMAT_OPTIONS ('header'='true');
COPY INTO indian_ecommerce.bronze.order_items FROM '/Volumes/indian_ecommerce/bronze/raw_files/order_items.csv'
  FILEFORMAT = CSV FORMAT_OPTIONS ('header'='true');
COPY INTO indian_ecommerce.bronze.payments FROM '/Volumes/indian_ecommerce/bronze/raw_files/payments.csv'
  FILEFORMAT = CSV FORMAT_OPTIONS ('header'='true');
COPY INTO indian_ecommerce.bronze.shipments FROM '/Volumes/indian_ecommerce/bronze/raw_files/shipments.csv'
  FILEFORMAT = CSV FORMAT_OPTIONS ('header'='true');
COPY INTO indian_ecommerce.bronze.returns FROM '/Volumes/indian_ecommerce/bronze/raw_files/returns.csv'
  FILEFORMAT = CSV FORMAT_OPTIONS ('header'='true');
COPY INTO indian_ecommerce.bronze.customer_reviews FROM '/Volumes/indian_ecommerce/bronze/raw_files/customer_reviews.csv'
  FILEFORMAT = CSV FORMAT_OPTIONS ('header'='true');
COPY INTO indian_ecommerce.bronze.marketing_campaigns FROM '/Volumes/indian_ecommerce/bronze/raw_files/marketing_campaigns.csv'
  FILEFORMAT = CSV FORMAT_OPTIONS ('header'='true');

-- ---------------------------------------------------------------------------
-- Bronze validation: does NOT filter or touch bronze itself (bronze stays
-- raw, full-fidelity STRING, by design -- see header comment). This only
-- counts, per source table and column, how many rows fail to parse as their
-- expected type or violate an obvious sanity rule. On this dataset every
-- count should be 0; the point is to catch a future data refresh with dirty
-- values here, in bronze, before silver's TRY_CAST-based filters silently
-- drop them and gold's numbers just look a little different with no
-- visible cause.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE TABLE indian_ecommerce.bronze.validation_log
COMMENT 'Row counts per bronze table/column that fail to parse as their target type or an obvious sanity rule (non-negative price, 1-5 rating, etc). Bronze rows are never dropped -- this is a read-only pre-check for silver.'
AS
SELECT 'customers' AS source_table, 'customer_id' AS column_name, 'not_null_or_blank' AS rule,
       COUNT(*) AS failed_rows
FROM indian_ecommerce.bronze.customers WHERE customer_id IS NULL OR TRIM(customer_id) = ''
UNION ALL
SELECT 'customers', 'customer_signup_date', 'parses_as_date', COUNT(*)
FROM indian_ecommerce.bronze.customers
WHERE customer_signup_date IS NOT NULL AND TRY_CAST(customer_signup_date AS DATE) IS NULL
UNION ALL
SELECT 'products', 'product_id', 'not_null_or_blank', COUNT(*)
FROM indian_ecommerce.bronze.products WHERE product_id IS NULL OR TRIM(product_id) = ''
UNION ALL
SELECT 'products', 'price', 'parses_as_nonneg_double', COUNT(*)
FROM indian_ecommerce.bronze.products
WHERE price IS NOT NULL
  AND (TRY_CAST(price AS DOUBLE) IS NULL OR TRY_CAST(price AS DOUBLE) < 0)
UNION ALL
SELECT 'products', 'cost_price', 'parses_as_nonneg_double', COUNT(*)
FROM indian_ecommerce.bronze.products
WHERE cost_price IS NOT NULL
  AND (TRY_CAST(cost_price AS DOUBLE) IS NULL OR TRY_CAST(cost_price AS DOUBLE) < 0)
UNION ALL
SELECT 'orders', 'order_id', 'not_null_or_blank', COUNT(*)
FROM indian_ecommerce.bronze.orders WHERE order_id IS NULL OR TRIM(order_id) = ''
UNION ALL
SELECT 'orders', 'order_date', 'parses_as_date', COUNT(*)
FROM indian_ecommerce.bronze.orders
WHERE order_date IS NOT NULL AND TRY_CAST(order_date AS DATE) IS NULL
UNION ALL
SELECT 'orders', 'final_amount', 'parses_as_nonneg_double', COUNT(*)
FROM indian_ecommerce.bronze.orders
WHERE final_amount IS NOT NULL
  AND (TRY_CAST(final_amount AS DOUBLE) IS NULL OR TRY_CAST(final_amount AS DOUBLE) < 0)
UNION ALL
SELECT 'orders', 'discount_percentage', 'parses_as_pct_0_100', COUNT(*)
FROM indian_ecommerce.bronze.orders
WHERE discount_percentage IS NOT NULL
  AND (TRY_CAST(discount_percentage AS DOUBLE) IS NULL
       OR TRY_CAST(discount_percentage AS DOUBLE) NOT BETWEEN 0 AND 100)
UNION ALL
SELECT 'order_items', 'order_item_id', 'not_null_or_blank', COUNT(*)
FROM indian_ecommerce.bronze.order_items WHERE order_item_id IS NULL OR TRIM(order_item_id) = ''
UNION ALL
SELECT 'order_items', 'quantity', 'parses_as_positive_int', COUNT(*)
FROM indian_ecommerce.bronze.order_items
WHERE quantity IS NOT NULL
  AND (TRY_CAST(quantity AS INT) IS NULL OR TRY_CAST(quantity AS INT) <= 0)
UNION ALL
SELECT 'payments', 'payment_id', 'not_null_or_blank', COUNT(*)
FROM indian_ecommerce.bronze.payments WHERE payment_id IS NULL OR TRIM(payment_id) = ''
UNION ALL
SELECT 'payments', 'order_id', 'not_null_or_blank', COUNT(*)
FROM indian_ecommerce.bronze.payments WHERE order_id IS NULL OR TRIM(order_id) = ''
UNION ALL
SELECT 'shipments', 'shipment_id', 'not_null_or_blank', COUNT(*)
FROM indian_ecommerce.bronze.shipments WHERE shipment_id IS NULL OR TRIM(shipment_id) = ''
UNION ALL
SELECT 'shipments', 'delivery_days', 'parses_as_nonneg_double', COUNT(*)
FROM indian_ecommerce.bronze.shipments
WHERE delivery_days IS NOT NULL
  AND (TRY_CAST(delivery_days AS DOUBLE) IS NULL OR TRY_CAST(delivery_days AS DOUBLE) < 0)
UNION ALL
SELECT 'returns', 'return_id', 'not_null_or_blank', COUNT(*)
FROM indian_ecommerce.bronze.returns WHERE return_id IS NULL OR TRIM(return_id) = ''
UNION ALL
SELECT 'customer_reviews', 'review_id', 'not_null_or_blank', COUNT(*)
FROM indian_ecommerce.bronze.customer_reviews WHERE review_id IS NULL OR TRIM(review_id) = ''
UNION ALL
SELECT 'customer_reviews', 'rating', 'parses_as_int_1_to_5', COUNT(*)
FROM indian_ecommerce.bronze.customer_reviews
WHERE rating IS NOT NULL
  AND (TRY_CAST(rating AS INT) IS NULL OR TRY_CAST(rating AS INT) NOT BETWEEN 1 AND 5)
UNION ALL
SELECT 'marketing_campaigns', 'campaign_id', 'not_null_or_blank', COUNT(*)
FROM indian_ecommerce.bronze.marketing_campaigns WHERE campaign_id IS NULL OR TRIM(campaign_id) = ''
ORDER BY failed_rows DESC;
