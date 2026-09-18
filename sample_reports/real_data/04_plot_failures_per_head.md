# Report: ask

**Question:** plot failure count per head

# Report: Failure Count per Head

**Goal:** Visualize the raw number of failed closures for each of the 36 capping heads.

**Data used:** Full closure event dataset across all heads (all recorded time periods).

**Analyses executed:** `plot_failures_per_head` — generates a bar chart of absolute failure counts per head (not success rate %, since that metric compresses near 100% and hides differences).

**Findings:**
- Chart saved to: `output\plots\failures_per_head_d98ce726.png`
- 36 heads plotted.
- **H29** stands out as the worst performer with **117 failures**, the highest of all heads.

**Confidence/limits:** This is a direct count from the underlying event log, so it is reliable as-is. The chart shows relative ranking across heads but doesn't explain *why* H29 fails more — that requires further investigation (e.g., torque drift, timing clusters).

**Suggested next checks:**
- Run `success_rate_per_head` to see H29's failure rate in percentage terms alongside its peers.
- Run `detect_drift` and `torque_stats_per_head` for H29 to check if torque drift or variability is driving the failures.
- Run `success_rate_over_time` with `head_id="H29"` to see if failures cluster in a specific time window (e.g., a shift change or maintenance gap).

## Generated charts
![failures_per_head_d98ce726](..\plots\failures_per_head_d98ce726.png)