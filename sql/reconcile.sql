-- Я сначала сворачиваю платежи до зерна order_id + currency.
-- Иначе два платежа размножат expected_minor одного заказа при JOIN.
WITH active_orders AS (
    SELECT * FROM orders WHERE ordered_on <= $as_of
), payment_totals AS (
    SELECT order_id, currency, count(*)::BIGINT AS payment_count,
           sum(CASE WHEN kind = 'capture' THEN amount_minor ELSE 0 END)::BIGINT AS captured_minor,
           sum(CASE WHEN kind = 'refund' THEN amount_minor ELSE 0 END)::BIGINT AS refunded_minor
    FROM payments WHERE settled_on <= $as_of
    GROUP BY order_id, currency
), paired AS (
    SELECT coalesce(o.order_id, p.order_id) AS order_id,
           coalesce(o.currency, p.currency) AS currency,
           o.order_id IS NOT NULL AS has_order,
           coalesce(p.payment_count, 0)::BIGINT AS payment_count,
           coalesce(o.expected_minor, 0)::BIGINT AS expected_minor,
           coalesce(p.captured_minor, 0)::BIGINT AS captured_minor,
           coalesce(p.refunded_minor, 0)::BIGINT AS refunded_minor
    FROM active_orders o
    FULL OUTER JOIN payment_totals p USING (order_id, currency)
), amounts AS (
    SELECT *, captured_minor - refunded_minor AS net_minor,
           captured_minor - refunded_minor - expected_minor AS delta_minor
    FROM paired
)
SELECT *, CASE
    -- Я сохраняю платежи без заказа даже при нулевом net и большом допуске.
    WHEN NOT has_order THEN 'orphan_payment'
    WHEN payment_count = 0 AND expected_minor > 0 THEN 'missing_payment'
    WHEN abs(delta_minor) <= $tolerance THEN 'matched'
    WHEN delta_minor < 0 THEN 'underpaid'
    ELSE 'overpaid'
END AS status
FROM amounts ORDER BY order_id, currency;
