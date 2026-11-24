SELECT source, observed, expires, intensity, base_ft, top_ft
FROM skycalm_dev_weather.observations
WHERE day = '2026-11-22' AND kind = 'sigmet'
GROUP BY id, source, observed, expires, intensity, base_ft, top_ft
ORDER BY observed, source;
