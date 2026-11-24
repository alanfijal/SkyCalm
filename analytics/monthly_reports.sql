SELECT substr(observed, 1, 7) AS month,
       intensity,
       count(DISTINCT id) AS reports
FROM skycalm_dev_weather.observations
WHERE day BETWEEN '2026-11-20' AND '2026-11-24'
  AND kind = 'report'
GROUP BY substr(observed, 1, 7), intensity
ORDER BY month, intensity;
