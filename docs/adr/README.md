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
| 033 | Deterministic identity and time | ACTIVE |
| **034** | **Distance-specific approved pace profiles** (leg ≠ official split; exact total-time reconciliation) | **ACTIVE (Faz 1)** |
| **035** | **Pre-session planning ML vs live adaptation ML; coach authority; Planning Model Gate P1–P7** | **ACTIVE (Faz 1: contract/gate only)** |
| **036** | **Start mode & official-distance authority** (wearable estimate never rewrites official distance) | **ACTIVE (Faz 1)** |
| **037** | **Append-only event journal + deterministic historical replay** (command-batch-per-line JSONL; fsync-per-batch; pure event-derived replay; SQLite → Faz 2) | **ACTIVE (Faz 1)** |
| **038** | **Continuous pace curves + phase-aware model generation** (leg/split duration = time constraint; PCHIP curve; exact total/locked-split reconciliation; safe-wall coach curve reset; planning ML contract only; phase-aware transformer = long-term target, scoped by ADR-039) | **ACTIVE (Faz 1)** |
| **039** | **Dataset-realistic pacing prior, training correction, forecasting and operational target envelopes** (first active model = coarse conditional split prior; no fake phase labels; forecast ≠ target; bounded envelope ≠ measured velocity; dataset catalog, license/quarantine gates, leakage rules) | **ACTIVE (Faz 1: contracts/catalog/validators/docs only)** |

Full ADR text lives in this directory. ADR-031, ADR-032, ADR-034, ADR-035, ADR-036, ADR-037,
ADR-038 and ADR-039 are in Phase 1 scope (034/035/036/039 as contracts, deterministic core,
and docs — no real ML/UI, no `src/ml/`).
