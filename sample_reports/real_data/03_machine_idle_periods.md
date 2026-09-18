# Report: ask

**Question:** were there times the entire machine was idle at once?

## Goal
Determine whether there were periods when the entire capping machine (all heads simultaneously) was idle, and characterize those events.

## Data used
`machine_idle_periods` tool (default threshold: sustained idle ≥ 300 seconds = 5 minutes), which scans the full telemetry log for windows where every head was inactive at once.

## Analyses executed
- Ran `machine_idle_periods` with the default 5-minute sustained-idle threshold across the entire dataset (spanning late Jan 2026 through end of April 2026).

## Findings
Yes — the machine (all heads together) went idle **hundreds of times** over the observed period, ranging from brief 5–10 minute stops up to very long multi-day shutdowns. Highlights:

- **Frequent short stops (5–30 min):** The large majority of idle events are brief pauses of 5–30 minutes, occurring many times per day — likely routine micro-stops (changeovers, minor jams, breaks).
- **Moderate stops (30 min–a few hours):** Numerous events in the 30–120 minute range, and several multi-hour idle windows (e.g., ~1–3 hours), suggesting planned breaks, maintenance checks, or larger interruptions.
- **Extended/full shutdowns (many hours to multiple days):** A number of very long full-machine idle periods stand out, including:
  - 2026‑02‑04 16:11 → 2026‑02‑05 08:35 (~16.4 h)
  - 2026‑02‑11 01:13 → 2026‑02‑11 15:27 (~14.2 h), followed almost immediately by 2026‑02‑11 15:54 → 2026‑02‑12 02:29 (~10.6 h)
  - 2026‑02‑18 20:20 → 2026‑02‑19 19:11 (~22.8 h)
  - 2026‑03‑08 20:22 → 2026‑03‑09 14:46 (~18.4 h) and 2026‑03‑09 15:41 → 2026‑03‑10 08:53 (~17.2 h)
  - 2026‑03‑12 16:54 → 2026‑03‑13 11:39 (~18.7 h)
  - 2026‑03‑13 16:16 → 2026‑03‑14 09:33 (~17.3 h)
  - 2026‑03‑14 18:09 → 2026‑03‑16 21:30 (~51.3 h, over 2 days)
  - 2026‑03‑16 21:30 → 2026‑03‑18 11:04 (~37.6 h)
  - 2026‑03‑20 15:30 → 2026‑03‑21 14:26 (~22.9 h)
  - 2026‑03‑22 10:55 → 2026‑03‑23 09:04 (~22.1 h)
  - 2026‑03‑28 20:00 → 2026‑03‑30 12:38 (~40.6 h, weekend-length shutdown)
  - 2026‑04‑08 17:22 → 2026‑04‑09 02:55 (~9.5 h)
  - **2026‑04‑26 07:33 → 2026‑04‑28 18:47 (~59.2 h / ~2.5 days) — the longest single full-machine shutdown observed**

These long gaps repeat roughly every 1–2 weeks and often span overnight or weekend periods, consistent with planned production breaks (weekends, shift changes, scheduled maintenance) rather than random faults.

## Confidence/limits
- High confidence that simultaneous full-machine idling occurred repeatedly — this is directly confirmed by telemetry gaps affecting all heads at once.
- The 5-minute sustained-idle threshold means very brief (<5 min) synchronized pauses are not counted; results could look different with a stricter or looser threshold.
- The tool doesn't label *why* the machine was idle (planned downtime vs. fault vs. end of shift) — this requires other context (shift schedules, maintenance logs) to interpret the long shutdowns.
- Some closely-spaced idle periods (e.g., a 5‑min active gap between two long idles) may reflect a single practical downtime event split by a brief sensor blip.

## Suggested next checks
- Cross-reference the long shutdown windows (multi-hour/multi-day) with a shift/maintenance calendar to classify them as planned vs. unplanned.
- Re-run `machine_idle_periods` with a higher threshold (e.g., 30 or 60 minutes) to get a cleaner list of only "significant" downtime events, filtering out routine micro-stops.
- Check `success_rate_over_time` around the long shutdown boundaries to see if failure rates spike right after machine restarts (common with cold-start torque variance).
- Use `idle_time` per head to see whether all heads resume simultaneously after these full-machine idle periods or if some heads lag/lead, which could reveal mechanical/synchronization issues.