# Sample Report — Multi-Tool Root Cause Investigation (Real AROL Data, Optimized Pipeline)

**Question asked:** "which head has the most problems and why?"

**Dataset:** Full 90-day dataset (55,128,924 closures, 36 heads), on the
Parquet-based closures pipeline. Closures load time: 1.22s (down from
~75-105s on the prior SQLite-backed pipeline).

**Tool(s) called (6, chained across 3 LLM turns):**
`success_rate_per_head` -> `torque_stats_per_head` -> `detect_drift` ->
`zscore_anomalies` -> `success_rate_over_time` (head_id=H29) -> `idle_time`

This is the deepest tool chain observed in this project and the clearest
demonstration of genuine hypothesis elimination: the agent tested and
ruled out four separate candidate explanations (torque variability,
gradual drift, downtime) before isolating the real, event-driven cause,
and independently surfaced a new data-quality finding along the way.

---

## Goal

Identify which capping head has the most reliability problems and diagnose the likely cause.

## Data used

- Per-head success/failure counts (`success_rate_per_head`)
- Per-head torque statistics (`torque_stats_per_head`)
- Drift detection across all heads (`detect_drift`)
- Torque anomaly scan, threshold z=3.5 (`zscore_anomalies`)
- Daily success-rate time series for the worst head (`success_rate_over_time`, head_id=H29)
- Idle-time profile per head (`idle_time`)

## Analyses executed

1. Compared failed-closure counts across all 36 heads (each has ~1.53M closures).
2. Compared average/min/max/std torque per head to see if any head runs "hotter" or more variable.
3. Ran drift detection to check for gradual torque degradation per head.
4. Pulled the top ~100 highest z-score torque anomalies to see if they cluster on one head.
5. Broke the worst head's failures down by day to see if they're chronic or a one-off event.
6. Checked idle-time/downtime per head as an alternative explanation.

## Findings

- **H29 has the most problems**: 117 failed closures out of 1,531,624 (success rate 99.99%, the lowest of all 36 heads, though still numerically high). The next worst are H35 (78 failures) and H30 (66 failures); all other heads have well under 70 failures, most under 40.
- **Cause is event-driven, not a chronic torque/calibration issue**: H29's torque stats (avg 2.015, std 0.084, max 2.464) are essentially identical to every other head — there's no evidence of systematically high/low or noisy torque. Drift detection returned no heads with significant torque drift over time.
- Breaking H29's failures down daily shows they are **not evenly spread**: most days have 0–3 failures, but **2026-02-25 alone accounts for 49 of the 117 failures** (0.15% failure rate that day vs. near-zero normally). This single-day spike is the dominant driver of H29's worse-than-average ranking, suggesting a discrete incident (e.g., a jam, sensor glitch, or material batch issue) rather than a persistently degrading head.
- **Data-quality flag on H30**: the anomaly scan returned dozens of H30 closures with `app_torque = 0.0` (z ≈ -24) still labeled "Closure OK." These are almost certainly sensor/logging glitches (zero-reading dropouts) rather than true zero-torque successful caps, and inflate H30's apparent anomaly count without necessarily reflecting real closure failures.
- Idle time is essentially uniform across all heads (~80,400–80,600 min total, ~49–50 min average per idle period, ~1600-1640 idle periods each) — downtime does not explain the difference in failure counts.

## Confidence/limits

- Failure counts are tiny relative to volume (max 117 failures per head out of >1.5M), so conclusions about "worst" head are statistically thin — a handful of events shifts the ranking.
- The Feb-25 spike for H29 is inferred from a coarse daily aggregation; exact root cause (mechanical, material, sensor) isn't identifiable from this data alone.
- The H30 zero-torque anomalies are flagged as suspicious but not confirmed as sensor faults vs. genuine short closures — needs raw log/sensor inspection.

## Suggested next checks

- Pull hourly (not daily) success-rate breakdown for H29 around 2026-02-25 to pinpoint the exact window and correlate with maintenance/changeover logs.
- Inspect raw records for H30's zero-torque "Closure OK" events to confirm sensor dropout vs. real failures; consider excluding/correcting before recomputing success rates.
- Compare H35's failure timeline the same way, to see if it's also one incident or a slow chronic issue.
