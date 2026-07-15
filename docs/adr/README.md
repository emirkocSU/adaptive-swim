# Architecture Decision Records

Her ADR şablon alanlarını taşır: Context / Problem / Considered options / Decision / (varsa Commands
/ Events / State changes) / Consequences / Reversibility / Validation.

## İndeks ve statü

| ADR | Karar | Statü | Faz |
|---|---|---|---|
| 001 | Modular monolith + ayrı edge süreci; monorepo | ACTIVE | — |
| 002 | Edge runtime Python asyncio; ilk pilotlarda laptop; RPi ayrı faz | REVISED | 2 |
| 003 | Edge storage SQLite WAL + append-only JSONL; log-first sıra + ≤50 ms fsync penceresi | REVISED | 1 (log), 2 (SQLite) |
| 004 | Cloud DB + object storage | DEFERRED | 8 |
| 005 | DSL versioning: semver-major, immutable versions, migration + golden | ACTIVE | 1 |
| 006 | In-process event bus + JSONL; broker yok | ACTIVE | 1 (bus tüketicisi Faz 2) |
| 007 | Adapter ABC + sabit envelope; LatencyCalibration | REVISED | 2 |
| 008 | Edge→cloud sync protokolü | DEFERRED | 8 |
| 009 | Realtime transport WebSocket + resync handshake | REVISED | 2 |
| 010 | Auth: edge operator PIN; OIDC cloud ile | REVISED | 2/8 |
| 011 | Telemetry format JSONL chunk; parquet yerel export | REVISED | 1 (contract), 4 |
| 012 | Simulator gerçek runtime embedded, SimClock, golden replay | ACTIVE | 1 |
| 013 | ML inference formatı LightGBM native; ONNX yalnızca OEM | ACTIVE | 6 |
| 014 | Model registry & rollout | DEFERRED (yerel artefact alt-kararı) | 6/8 |
| 015 | Tenant izolasyonu | DEFERRED | 10 |
| 016 | Privacy/research export: pseudonym ayrık, küçük hücre bastırma | ACTIVE | 1 (kural), sonra pipeline |
| 017 | Frontend: minimal yerel UI; tam PWA ertelendi | REVISED | 2 |
| 018–020 | Repo yapısı / CI-CD / feature flags | ACTIVE ilke | 1 |
| 021 | Adaptasyon yalnızca length/segment sınırında | ACTIVE | 1 |
| 022 | Split detection: buton/koç-tap + zorunlu doğrulama | REVISED | 1 (contract), 3 |
| 023 | Swimmer position: gap-at-wall + düşük güvenli interpolasyon; kamera reddi | ACTIVE | — |
| 024 | Donanım iletişimi kablolu (Ethernet/RS-485); D5 uzman onayı | ACTIVE | 3 |
| 025 | Retention: yerel dönem basit silme/maskeleme | REVISED | 1 (kural) |
| 026 | Local export & backup (CSV/Parquet + imzalı yedek + iki-kopya) | NEW | 2 |
| 027 | Split verification (5 kalite sınıfı, kullanım hakları) | NEW | 1 (contract), 3 |
| 028 | ML Activation Gate (G1–G7; B1–B5 baseline) | NEW | 5/6 |
| 029 | Rule-based adaptation (adaptationSource; EWMA + ölü-bant) | NEW | 5 |
| 030 | Confidence composition (quantile tek başına güven değil) | NEW | 6 |
| **031** | **Stop Pause and Ghost Alignment Policy** (re-anchor ve "incident pause"ın yerini alır) | **NEW** | **1** |
| **032** | **External Data Bootstrapping Strategy** (5 katman) | **NEW** | **1 (doküman+contract)** |
| **033** | **Deterministic identity & time** (Clock + EventIdGenerator; uuid4+seq, ULID yok) | **NEW** | **1** |

001–030'un tam metinleri Architecture v1.1'de özetlenmiştir; repo büyüdükçe bu klasöre tek tek
şablonla açılır. 031–033 bu klasörde tam metindir (Faz 1 kapsamı).
