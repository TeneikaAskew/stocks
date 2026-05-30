SELECT
    COUNT(*)                                  AS total_rows,
    COUNT(*) FILTER (WHERE dgs3mo IS NULL)    AS null_dgs3mo,
    COUNT(*) FILTER (WHERE sp500_div_yld IS NULL) AS null_divyld,
    MIN(date) AS earliest,
    MAX(date) AS latest
FROM daily_rates
