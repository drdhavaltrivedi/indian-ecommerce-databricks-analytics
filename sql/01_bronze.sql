-- Bronze layer: raw ingestion, minimal transformation, full fidelity.
-- Every column STRING -- same principle as the ecommerce clickstream project:
-- if a downstream number looks wrong, bronze is the reference to check
-- against, and casting at ingest would destroy that evidence.

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
