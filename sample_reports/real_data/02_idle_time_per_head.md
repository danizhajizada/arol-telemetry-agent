# Report: ask

**Question:** what is the idle time for each head?

## Idle Time per Head (sustained idle ≥ 300s threshold, default)

**Goal:** Determine idle time (downtime) for each of the 36 capping heads.

**Data used:** Full closure/telemetry dataset, `idle_time` tool with default sustained-idle threshold of 300 seconds.

**Analyses executed:** Retrieved total idle minutes, average idle period length, and number of distinct idle periods for each head (H01–H36).

**Findings:**
All 36 heads show remarkably uniform idle behavior — no single head stands out as significantly more or less idle than the rest:

| Metric | Range across heads |
|---|---|
| Total idle time | ~80,307 – 80,579 minutes (≈1339–1343 hours) |
| Avg idle period duration | ~49.0 – 50.1 minutes |
| Number of idle periods | ~1,604 – 1,642 |

Representative examples:
- Highest total idle: **H23** (80,578.8 min, 1,620 periods)
- Lowest total idle: **H34** (80,306.9 min, 1,610 periods)
- Most idle periods: **H07** (1,642 periods, avg 49.0 min each)
- Fewest idle periods: **H36** / **H35** (~1,604–1,606 periods, avg ~50.1 min each)

The spread between the busiest and least-idle head is only ~272 minutes (~0.34%) out of ~80,500 total idle minutes — essentially negligible. This strongly suggests idle time is driven by shared/systemic stoppages (e.g., scheduled breaks, line-wide stops) affecting all heads nearly equally, rather than head-specific mechanical issues.

**Confidence/limits:** 
- Idle time is defined per-head only (that head stopped, regardless of others), using a 300s minimum threshold — shorter micro-stops are not counted.
- The near-identical totals across heads hint the idle events may be line-wide rather than independent; this hasn't been confirmed here.

**Suggested next checks:**
- Run `machine_idle_periods` to check whether idle time is dominated by full-line shutdowns (all heads idle simultaneously) rather than isolated head faults.
- Cross-reference idle periods with `success_rate_over_time` or `detect_drift` to see if idle events correlate with quality issues after restart.
- If finer-grained (sub-5-min) stoppages are of interest, rerun with a lower `sustained_seconds` threshold.