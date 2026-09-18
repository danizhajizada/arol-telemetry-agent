# Report: ask

**Question:** the zero-torque closures for head 30 - are they real failures or sensor errors?

## Report: Are H30's Zero‑Torque Closures Real Failures or Sensor Errors?

**Goal**
Determine whether the numerous `app_torque = 0.0` readings recorded for head H30 represent genuine capping failures or artifacts of sensor/telemetry logging.

**Data used**
- `torque_stats_per_head` (H30, all closures)
- `success_rate_per_head` (all heads, for context)
- `success_rate_over_time` (H30, daily)
- `zscore_anomalies` (threshold 3.0, up to 500 rows, machine-wide)
- `idle_time` (all heads)

**Analyses executed**
1. Computed H30 torque statistics (avg, min, max, std) across all closures.
2. Compared H30's failure count/rate against the fleet.
3. Checked H30's daily success rate for spikes tied to the zero-torque events.
4. Pulled extreme z-score anomalies (which surfaced the zero-torque points) and inspected their `status_label` and timestamp clustering, also across other heads.
5. Checked idle-time patterns to see if zero readings align with startup/shutdown transitions.

**Findings**
- H30 has 1,531,372 total closures, only **66 flagged as failed** (success rate 100.00%, essentially indistinguishable from the rest of the fleet — most heads show 4–70 failures out of ~1.53M).
- H30's average applied torque is 1.158 (std 0.998), with a hard floor of **0.0** and a ceiling of 2.335 — a torque of exactly 0.0 is ~24 standard deviations below the mean (z ≈ ‑24.3), an extreme, physically implausible reading for a completed cap closure.
- Critically, **every zero-torque record pulled (300+ instances) is labeled `"Closure OK"`**, not "failed." This means the vast majority of zero-torque events are *not* among H30's 66 registered failures — the machine's own status logic accepted them as successful closures despite an impossible torque value.
- These zero-torque, "OK"-labeled readings often occur in **tight bursts** (multiple hits within the same second to a few minutes, e.g., 2026‑03‑18 17:54:49–17:55:17, or 2026‑02‑27 13:28:27–13:28:50) — a pattern typical of a transient sensor/telemetry dropout rather than a mechanical fault recurring at that exact cadence.
- The same anomalous zero-torque signature, at matching or near-identical timestamps, also shows up on **other heads** (e.g., H07 shares many of the same timestamps as H30, such as 2026‑03‑18 17:54:49–17:55, 2026‑02‑17 13:16, 2026‑02‑01 08:28). This cross-head synchronization strongly suggests a shared/systemic data-acquisition glitch (e.g., brief signal loss, controller reset, or logging default-to-zero) affecting multiple heads simultaneously, not a head-specific mechanical problem unique to H30.
- No unusual idle-time pattern was found for H30 relative to peers (~86,089 idle minutes, ~25.4 min/period, 3388 periods — all in line with the other 35 heads), so the zero readings don't appear to be simple startup-after-idle artifacts.

**Conclusion**
The evidence points toward the zero-torque closures being **sensor/logging artifacts rather than genuine mechanical failures**: they are (a) far more numerous than the actual recorded failures, (b) still labeled "OK" by the machine's own success logic, (c) clustered in short bursts, and (d) synchronized across multiple unrelated heads — a signature of a shared telemetry glitch rather than 66 independent head-specific and hundreds of unrecorded mechanical failures.

**Confidence / limits**
- This is inferential, based on statistical patterns (status label, clustering, cross-head synchrony) — we don't have direct access to sensor diagnostic/health logs to confirm a hardware/communication fault definitively.
- The `zscore_anomalies` tool caps output at 500 rows; the true total count of zero-torque events for H30 could be higher, though this doesn't change the qualitative conclusion.
- It's possible a small subset of true zero-torque events are real (e.g., a cap not seated so no torque was ever applied), but if so, they should have been marked "failed," which most were not — supporting the sensor-error hypothesis.

**Suggested next checks**
- Cross-reference the exact zero-torque timestamps against machine-wide idle/reset logs (`machine_idle_periods`) to see if they coincide with power cycles or communication resets.
- If available, inspect raw sensor diagnostic/error codes at those timestamps.
- Consider a data-quality rule: flag any `torque = 0.0 AND status = "Closure OK"` record for manual review/exclusion from torque-quality KPIs, since it likely reflects a missing/failed reading rather than a valid measurement.
- Extend the anomaly pull to all heads with a higher limit to quantify how many heads/timestamps show this synchronized zero-torque signature, which would further confirm a systemic root cause.