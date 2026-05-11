UPDATE earnings_calendar AS ec
SET options_volume = v.vol,
    open_interest  = v.oi
FROM (VALUES
  ('YUEIF',0::bigint,0::bigint),
  ('ZLSCF',0::bigint,0::bigint)
) AS v(ticker, vol, oi)
WHERE ec.ticker = v.ticker
  AND ec.earnings_date = '2026-05-11'::date
  AND (ec.options_volume IS NULL OR ec.open_interest IS NULL);
