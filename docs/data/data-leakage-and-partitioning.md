# Data leakage and partitioning rules

## Official race

- One `race_uid` stays in one partition; athlete-held-out and source/time-held-out evaluation
  remain possible.
- Random segment-row splitting is forbidden.
- Medley event/segment strokes and relay context remain distinct.
- Target-derived timing/speed columns do not enter feature allowlists.

## Training/fatigue

- The real discriminator is `record_granularity`.
- 228 `ATHLETE_WEEK` rows use time-aware athlete grouping.
- 168 `SPRINT_REPEAT` rows keep each `session_or_trial_id` intact.
- `next_week_*` columns are labels, not features.
- License is gated by row/source; the TBD sprint source cannot become production eligible.

## IMU

- Group by raw `source_participant_id` and `session_or_trial_id`.
- Never split one sensor time series across partitions.
- Technical targets remain separate from sensor features.
- IMU is research/technique evidence, not official distance or primary pacing target.

## External studies

- Pre/post and first/second-25 observations of one participant/trial stay together.
- Processed sensor statistics are not continuous position-time ground truth.
- Massage crossover analyses retain `condition_label` and crossover grouping.
- The quarantined stroke member is excluded before any production or primary-research view;
  it is available only to parser/multiclass smoke tests.

Canonical view keys are derived only after raw validation; see
`raw-to-canonical-mapping.md`.
