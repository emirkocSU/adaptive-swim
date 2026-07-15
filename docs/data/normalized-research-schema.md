# Normalized Research Schema (ADR-032)

Provider-bagimsiz `NormalizedSwimmingRecord`. Her kaynak tum alanlari tasimak zorunda degildir;
**missingness korunur, sahte doldurma yapilmaz**.

Alanlar: source_id, source_record_id, athlete_pseudonym, session_or_race_id, data_domain, stroke,
pool_length_m, event_or_set_distance_m, length_or_split_index, cumulative_time_sec,
length_or_split_time_sec, target_pace_sec_per_100m, rest_before_sec, stroke_rate, stroke_count, swolf,
heart_rate, heart_rate_trend, sensor_quality, incident_like_flag, quality_flag, synthetic,
provenance_ref.

`data_domain` degerleri: ELITE_RACE | TRAINING_EXPORT | WEARABLE_SENSOR | ADAPTIVE_SWIM_SESSION |
SYNTHETIC_SIMULATION. Race split ile training session **`data_domain` olmadan sessizce birlestirilemez**.
