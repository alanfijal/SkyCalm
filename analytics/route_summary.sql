SELECT origin, destination, substr(departure, 1, 7) AS month, peak,
       count(*) AS forecast_days, sum(report_count) AS matched_reports
FROM skycalm_dev_weather.route_days
GROUP BY origin, destination, substr(departure, 1, 7), peak
ORDER BY origin, destination, month, peak;
