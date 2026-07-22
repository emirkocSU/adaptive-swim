# Ertelenen Bilesenler Haritasi

Asagidakiler Faz 1 aktif tree'de YOKTUR (bos klasor dahi acilmaz). Her biri ilgili fazda kendi
commit setiyle dogar.

## Faz 2 — Minimal UI + Edge
`src/edge/` (asyncio runtime, tasks, yerel REST/WS, snapshot servisi) · `src/edge/store/` (SQLite WAL
projection; log-first sozlesmesinin tuketicisi) · `src/edge/export/` (CSV/Parquet + imzali yedek,
ADR-026) · `src/adapters/` (DeviceAdapter ABC + PaceFrame + SimulatedLED + MockLED + ButtonSplit) ·
`src/ui_minimal/` (edge'in sundugu basit yerel sayfa; React/PWA DEGIL).

### Faz 1'den ertelenen iki dosya (gercek tuketicisi yok)
* `swimcore/pacing/estimator.py` — gercek yuzucu konum tahmini Faz 1'de gerekmez (split-tabanli,
  headless). StopPause'daki havuz-ortasi hizalama Faz 1'de takip edilen son bilinen noktayi kullanir;
  estimator (konfidansli ara-tahmin) sensor-assisted mod ile (Faz 2/4) dogar.
* `swimcore/session/event_bus.py` — saf `(state, command) -> events` fold'unda in-process bus
  gereksizdir. Gercek tuketici (UI/WS fan-out) Faz 2'de dogar; o zaman eklenir.

## Faz 3 — Pool Pilot 0
`tools/verification/` (split dogrulama, manualErrorMs raporu, ADR-027) · `adapters/led_prototype/`
(kablolu dusuk voltaj mock, D5 uzman kontrolu).

## Faz 4 — Pilot A + yerel wearable import
`src/wearable_import/` (FIT/TCX yerel dosya parse + normalize + quality flag).

## Faz 5 — Kural tabanli adaptasyon + data audit
`src/swimcore/safety/rule_engine.py` (EWMA-sapma + olu-bant, ADR-029) · `tools/data_audit/`
(ML Activation Gate G1-G7 raporu, ADR-028).

## Pre-gate research (AYRI epic/dizin veya AYRI repo; urun runtime'ina baglanmaz)
`research/` (parser prototipleri, cleaning, normalized research schema donusumleri, pacing prior
analizi, wearable task-specific deneyler; ADR-032 pre-gate).

## Faz 6 — Production ML (yalnizca G1-G7 acikken)
`src/ml/` (features, training, evaluation, calibration, inference) · `artifacts/` (imzali model +
model card; yerel, registry degil).

## Faz 8 — Cloud (yalnizca K17 tetikleyicisiyle)
`src/cloud/` (FastAPI, PostgreSQL, object storage, sync, registry, auth).

## Faz 10 — OEM
`src/adapters/partner_*/` · `src/cloud/tenants/`.


## Deferred by ADR-039 (Commit 8 correction)

| Item | Deferred to | Trigger |
|---|---|---|
| `src/ml/` package | Phase 5 | Phase 1 closed and Phase 5A started |
| Real model training (race prior, training correction, forecasting) | Phase 5A–5C | validated bundles + verified licenses |
| Constrained operational target-envelope compiler (learned shapes) | Phase 5D | Phase 5A/5B deliver a usable prior |
| FORM export / pilot personalisation | Phase 5E | consented wearable export available |
| Phase-aware conditional transformer (ADR-038 long-term target) | after high-resolution continuous data exists | genuine within-length position-time ground truth |
| Production training on external data | after per-source license verification | `source_license_status = VERIFIED_ALLOWED` |

## Still deferred after Commit 9

- Real forecasting/model training and model registry.
- Live ML inference or automatic target changes.
- UI/report visualization, cloud sync and database projections.
- Device/wearable connectors and official-distance claims from wearable positions.
- Medical/fatigue diagnosis; Commit 9 collapse/HR relationships are advisory only.


## Deferred at Phase 1 closure (ADR-041)

| Item | Deferred to | Trigger |
|---|---|---|
| Coach UI, curve editor, PWA | Phase 2 | coach tooling starts |
| Web/API transport (FastAPI, WebSocket), cloud deployment | Phase 2+ | a remote surface is actually needed |
| Device / LED adapter, live wearable integration | Phase 3 | pool pilot hardware exists |
| FORM export production integration | Phase 4 | consented athlete exports available |
| Real ML training (`src/ml/`) | Phase 5 | Phase 1 closed and validated bundles licensed |
| Personalization | Phase 6 | pilot data volume justifies it |
