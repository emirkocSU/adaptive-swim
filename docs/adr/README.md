# Architecture Decision Records — Index

Statuses: **ACTIVE**, **REVISED**, **DEFERRED** (design ready, build gated by a trigger),
**NEW**, **SUPERSEDED**.

| ADR | Decision | Status |
|---|---|---|
| 001 | Modular monolith + separate edge process; monorepo | ACTIVE |
| 002 | Edge runtime: Python asyncio; laptop first, RPi later | ACTIVE |
| 003 | Edge storage: SQLite WAL + append-only JSONL; log-first ordering | ACTIVE (Faz 2) |
| 004 | Cloud DB + object storage | DEFERRED → Faz 8 |
| 005 | DSL versioning: semver-major, immutable versions, migration registry | ACTIVE |
| 006 | In-process event bus + JSONL; no broker | ACTIVE |
| 007 | Device adapter ABC + fixed envelope + latency calibration | ACTIVE (Faz 2) |
| 008 | Edge→cloud sync protocol | DEFERRED → Faz 8 |
| 009 | Realtime transport: WebSocket + resync handshake | ACTIVE (Faz 2) |
| 010 | Auth: operator PIN + pre-provisioned profiles; OIDC deferred | REVISED |
| 011 | Telemetry format: JSONL chunk + envelope | ACTIVE |
| 012 | Simulator: real runtime embedded, SimClock, golden replay | ACTIVE |
| 013 | ML inference: LightGBM native; ONNX only for OEM device | ACTIVE (gate-gated) |
| 014 | Model registry & rollout channels | DEFERRED → Faz 8 |
| 015 | Tenant isolation | DEFERRED → Faz 10 |
| 016 | Privacy/research export: pseudonym map, small-cell suppression | ACTIVE |
| 017 | Frontend: minimal edge-served UI; full PWA deferred | REVISED |
| 018–020 | Repo structure / CI-CD / feature flags | ACTIVE |
| 021 | Coach pacing reset / accounting only at wall boundary | ACTIVE |
| 022 | Split detection: button/coach-tap + mandatory verification | ACTIVE |
| 023 | Swimmer position: gap-at-wall + low-confidence interpolation | ACTIVE |
| 024 | Hardware comms: wired (Ethernet/RS-485) preferred | ACTIVE |
| 025 | Retention: local-phase simple delete/mask | REVISED |
| 026 | Local export & backup | NEW |
| 027 | Split verification | NEW |
| 028 | ML Activation Gate | NEW |
| 029 | Rule-based adaptation | NEW |
| 030 | Confidence composition | NEW |
| **031** | **StopPause & controlled ghost alignment** (supersedes the earlier ghost re-anchor policy) | **NEW** |
| 032 | External Data Bootstrapping Strategy | NEW |

Full ADR text lives in this directory. ADR-031 and ADR-032 are in Phase 1 scope
(ADR-032 as document + contract draft only).
