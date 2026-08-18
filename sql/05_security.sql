-- Data classification. This dataset is synthetic, but customer_id, state,
-- city, and pincode_prefix constitute a location-identifiable profile per
-- customer, and the pattern (tag now, mask later) is worth applying even on
-- synthetic data so it's already in place when real data uses this pipeline.

ALTER TABLE indian_ecommerce.silver.dim_customer
  ALTER COLUMN customer_id SET TAGS ('pii' = 'pseudonymous_id', 'sensitivity' = 'confidential');
ALTER TABLE indian_ecommerce.silver.dim_customer
  ALTER COLUMN city SET TAGS ('pii' = 'location', 'sensitivity' = 'internal');
ALTER TABLE indian_ecommerce.silver.dim_customer
  ALTER COLUMN pincode_prefix SET TAGS ('pii' = 'location', 'sensitivity' = 'internal');

ALTER TABLE indian_ecommerce.silver.fact_orders
  ALTER COLUMN customer_id SET TAGS ('pii' = 'pseudonymous_id', 'sensitivity' = 'confidential');

ALTER TABLE indian_ecommerce.silver.dim_customer SET TAGS ('layer' = 'silver', 'domain' = 'customer', 'contains_pii' = 'true');
ALTER TABLE indian_ecommerce.gold.segment_performance SET TAGS ('layer' = 'gold', 'domain' = 'customer', 'contains_pii' = 'false');

-- Grain documentation on the tables most likely to be misjoined
COMMENT ON TABLE indian_ecommerce.silver.fact_order_items IS
  'Grain: one line item per (order_id, product_id). Join to dim_product for category/brand; do not sum across orders without grouping, an order can contain multiple line items.';
COMMENT ON TABLE indian_ecommerce.gold.product_true_profitability IS
  'Grain: one row per product_id. refund_pct_of_profit > 100 means the product is a net loss after returns despite showing positive gross_profit.';
COMMENT ON TABLE indian_ecommerce.gold.campaign_targeting_precision IS
  'Grain: one row per target_segment. targeting_precision_pct is the pct of resulting orders that actually came from the targeted segment -- low values mean targeting is not working.';
