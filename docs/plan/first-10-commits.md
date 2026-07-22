# Faz 1 — Ilk 10 Commit

Her commit: kendi testleri, kendi rollback siniri (tek revert), sonunda `make ci` yesil.
Terminoloji: StopPause modeli (ADR-031). "Incident" yalnizca bir StopTrigger turudur.

1. **Repository scaffold and architecture anchors** — tooling, ADR-031(StopPause)/032/033, docs, arch
   testleri (yasak dizin + swimcore purity: import VE I/O built-in cagrisi), smoke, phase1-completeness
   plani. AC: `make ci` yesil (PENDING dahil); import-linter aktif; yasak dizin yok; swimcore purity
   gecer; negatif testler (src/ml, swimcore'da time, swimcore'da open()) build'i kirar.
2. **Core contracts and workout schema** — asagidaki Commit 2 contract plani; uretilen JSON Schema;
   golden ornekler. AC: schema-check birebir; minPace/maxPace yok; data_domain'siz birlesme yasak.
3. **Semantic workout validator** — v1.1 semantic kurallar (pace yon kurali dahil).
4. **Pace math pure functions** — 4 mode + analitik testler.
5. **Clocks and ghost math** — Clock/EventIdGenerator port'lari (ADR-033), SimClock, ghost progression,
   StopPause saat dusumu (retroaktif), havuz-ortasi KONTROLLU hizalama matematigi (kontrolsuz teleport
   yasak), duvarda reconcile.
6. **Session state machine, timing sub-state, StopPause events + safety controller** — session
   degismez; timing sub-state (ACTIVE/STOP_PAUSED); idempotent MarkStopPause/ResolveStopPause/
   CoachPacingReset; StopDetected/LongStopConfirmed/StopPauseStarted/StopPauseResolved; controller
   karar tablosu (oneri motoru yok).
7. **Append-only event log and replay** — log-first durability (son satir kesme + LogTailTruncated;
   fsync-per-command-batch; kill -9 != elektrik/disk), deterministik replay,
   StopPause/stopped-duration yeniden uretimi. SQLite Faz 2'ye. **[TAMAMLANDI — ADR-037;**
   **komut-basi-tek-satir EventBatchRecord, canonical codec, idempotent retry, tail recovery,**
   **saf `swimcore.replay`, 3 golden journal.]**
8. **Headless simulator and failure scenarios** — VirtualSwimmer, deterministik seed + deterministik
   id, StopPause senaryolari (tempo kaybi / long stop / manual stop / cift-isaret idempotency /
   dinlenme-ici stop / konum-zaman guvenilmez -> length analiz disi + duvarda reconcile /
   paused-iken-complete / coach reset).
9. **Analytics + TrainingEfficiencyMetrics + report** — uc sure alani (active/stopped/elapsed);
   guvenilir stop -> length atilmaz; guvenilmez -> analiz disi; aktif performans vs antrenman verimi
   ayrimi; TrainingEfficiencyMetrics; split-quality ayrimi; "20.00 +15.00" gosterimi.
10. **Full vertical-slice verification + phase1-completeness** — golden replay, property invariants,
    state-machine, agi kapali e2e (iki ornek antrenman), 20 degismezin test kimligine baglanmasi,
    phase1-completeness-check (hicbir PENDING kalmaz).


> **Status note (Commit 8 correction):** the authoritative Phase 1 status table lives in
> `docs/plan/phase1-commit-plan.md`. Commits 1–8 are done (Commit 8 including the ADR-039
> dataset evidence plan); Commit 9 (analytics/report) and Commit 10 (e2e vertical slice) are
> pending. See also `docs/plan/model-roadmap.md` for Phase 5A–5E.
