-- Silver layer: typed, conformed star schema.
-- Unlike the clickstream project, this source data is already relationally
-- consistent (single generator, consistent FKs), so silver here is mostly
-- about typing and deriving a few analysis-ready fields -- not heavy cleanup.

CREATE OR REPLACE TABLE indian_ecommerce.silver.dim_customer AS
SELECT
  customer_id,
  CAST(customer_signup_date AS DATE) AS signup_date,
  gender,
  CAST(CAST(age AS DOUBLE) AS INT) AS age,  -- source stores age as "44.0"
  age_group,
  state, city, pincode_prefix,
  customer_segment,
  preferred_device,
  preferred_payment_method,
  acquisition_channel,
  CAST(total_orders AS INT) AS total_orders,
  CAST(total_spend AS DOUBLE) AS total_spend,
  CAST(last_order_date AS DATE) AS last_order_date,
  CAST(average_order_value AS DOUBLE) AS average_order_value,
  customer_status,
  loyalty_tier
FROM indian_ecommerce.bronze.customers;

CREATE OR REPLACE TABLE indian_ecommerce.silver.dim_product AS
SELECT
  product_id, product_name, category, subcategory, brand,
  CAST(price AS DOUBLE) AS price,
  CAST(cost_price AS DOUBLE) AS cost_price,
  discount_range,
  CAST(rating_average AS DOUBLE) AS rating_average,
  CAST(rating_count AS INT) AS rating_count,
  CAST(stock_quantity AS INT) AS stock_quantity,
  CAST(product_launch_date AS DATE) AS product_launch_date,
  product_type,
  CAST(return_rate_baseline AS DOUBLE) AS return_rate_baseline
FROM indian_ecommerce.bronze.products;

CREATE OR REPLACE TABLE indian_ecommerce.silver.dim_campaign AS
SELECT
  campaign_id, campaign_name, channel,
  CAST(campaign_start_date AS DATE) AS campaign_start_date,
  CAST(campaign_end_date AS DATE) AS campaign_end_date,
  campaign_type, target_segment,
  CAST(discount_percentage AS DOUBLE) AS discount_percentage,
  CAST(conversions AS INT) AS conversions,
  CAST(revenue_generated AS DOUBLE) AS revenue_generated,
  CAST(impressions AS INT) AS impressions,
  CAST(clicks AS INT) AS clicks,
  CAST(campaign_cost AS DOUBLE) AS campaign_cost,
  CAST(roi AS DOUBLE) AS roi
FROM indian_ecommerce.bronze.marketing_campaigns;

CREATE OR REPLACE TABLE indian_ecommerce.silver.fact_orders AS
SELECT
  order_id, customer_id,
  CAST(order_date AS DATE) AS order_date,
  order_time,
  CAST(CONCAT(order_date,' ',order_time) AS TIMESTAMP) AS order_timestamp,
  order_status, shipping_method, delivery_city, delivery_state,
  NULLIF(coupon_code,'') AS coupon_code,
  CAST(discount_percentage AS DOUBLE) AS discount_percentage,
  marketing_channel,
  CAST(subtotal AS DOUBLE) AS subtotal,
  CAST(shipping_fee AS DOUBLE) AS shipping_fee,
  CAST(tax_amount AS DOUBLE) AS tax_amount,
  CAST(final_amount AS DOUBLE) AS final_amount,
  NULLIF(campaign_id,'') AS campaign_id
FROM indian_ecommerce.bronze.orders;

CREATE OR REPLACE TABLE indian_ecommerce.silver.fact_order_items AS
SELECT
  order_item_id, order_id, product_id,
  CAST(quantity AS INT) AS quantity,
  CAST(unit_price AS DOUBLE) AS unit_price,
  CAST(discount_percentage AS DOUBLE) AS discount_percentage,
  CAST(item_revenue AS DOUBLE) AS item_revenue,
  CAST(item_cost AS DOUBLE) AS item_cost,
  CAST(profit AS DOUBLE) AS profit
FROM indian_ecommerce.bronze.order_items;

CREATE OR REPLACE TABLE indian_ecommerce.silver.fact_payments AS
SELECT
  payment_id, order_id,
  CAST(payment_date AS DATE) AS payment_date,
  payment_method, payment_status,
  CAST(amount_paid AS DOUBLE) AS amount_paid,
  CAST(transaction_fee AS DOUBLE) AS transaction_fee,
  CAST(refund_amount AS DOUBLE) AS refund_amount
FROM indian_ecommerce.bronze.payments;

CREATE OR REPLACE TABLE indian_ecommerce.silver.fact_shipments AS
SELECT
  shipment_id, order_id, warehouse_city, delivery_city, shipping_method,
  CAST(dispatch_date AS DATE) AS dispatch_date,
  CAST(expected_delivery_date AS DATE) AS expected_delivery_date,
  CAST(actual_delivery_date AS DATE) AS actual_delivery_date,
  CAST(delivery_days AS DOUBLE) AS delivery_days,
  delivery_status,
  CAST(delayed_flag AS INT) AS delayed_flag
FROM indian_ecommerce.bronze.shipments;

CREATE OR REPLACE TABLE indian_ecommerce.silver.fact_returns AS
SELECT
  return_id, order_id, customer_id, product_id,
  CAST(return_date AS DATE) AS return_date,
  return_reason,
  CAST(refund_amount AS DOUBLE) AS refund_amount,
  return_status
FROM indian_ecommerce.bronze.returns;

CREATE OR REPLACE TABLE indian_ecommerce.silver.fact_reviews AS
SELECT
  review_id, order_id, customer_id, product_id,
  CAST(review_date AS DATE) AS review_date,
  CAST(rating AS INT) AS rating,
  review_sentiment,
  CAST(verified_purchase AS BOOLEAN) AS verified_purchase
FROM indian_ecommerce.bronze.customer_reviews;
