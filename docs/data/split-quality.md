# Split Kalite Modeli (ADR-027)

Manuel split (COACH_TAP, BUTTON) **ground truth degildir**. Her split kaynagi + kalitesiyle dogar;
ML ve arastirma yalnizca uygun siniflari tuketir.

| qualityFlag | Tanim | Canli pacing | ML egitimi | Arastirma birincil |
|---|---|---|---|---|
| VERIFIED_HIGH | Bagimsiz kaynakla dogrulanmis (touchpad/video/cift zamanlayici) | evet | evet | evet |
| RELIABLE | Otomatik guvenilir kaynak (touchpad dogrudan; kalibre wearable) | evet | evet | evet (duyarlilik) |
| MANUAL_UNVERIFIED | COACH_TAP/BUTTON, dogrulamasiz | evet | hayir (varsayilan) | hayir (yalnizca ikincil) |
| ESTIMATED | Sistem tahmini (interpolasyon, gec split normalizasyonu) | evet (dusuk guven) | hayir | hayir |
| INVALID | Duplicate artigi, sira disi, sanity ihlali | hayir | hayir | hayir |

**Onemli:** `qualityFlag` yalnizca OLCUM kalitesidir. Incident dislamasi AYRI eksendir
(`AnalyticsExclusionReason.STOP_TIME_UNRELIABLE`). Guvenilir stop varsa VERIFIED_HIGH bir split StopPause icinde olabilir ve
yine VERIFIED_HIGH kalir; length atilmaz (active/stopped ayri). Guvenilmez stop -> length analiz disi. `mlEligible = quality_ok AND NOT in_stop_interval`.
