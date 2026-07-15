# Test Stratejisi (Faz 1)

Piramit (asagidan yukari): unit -> property -> state-machine -> replay -> simulator -> architecture
-> e2e (agi kapali). Faz 1 headless oldugu icin donanim/pilot katmanlari yoktur.

* **unit** — pace math (analitik: integral == mesafe), validator kurallari, controller karar tablosu,
  incident pause saat dusumu, split quality turetme, analitik dislama.
* **property (hypothesis, ci profili deterministik)** — segment kapsama; illegal state gecisi yok;
  controller HICBIR girdide bounds disina cikmaz; incident/reset idempotency; log satir butunlugu.
* **replay** — golden bit-identical event zinciri + rapor; frozenDurationMs dogrulamasi.
* **simulator** — normal tempo kaybi, long stop, koc-isaretli incident, cift-isaret idempotency,
  dinlenme sirasinda incident, konum bilinmeyince length analiz disi + sonraki duvarda hizalama,
  ghost paused iken session completed, coach pacing reset.
* **architecture** — import-linter + yasak dizin + swimcore saflik (AST).
* **e2e** — agi kapali uctan uca vertical slice (iki ornek antrenman -> log -> rapor).

Kural: bir degismez duserse KOD duzeltilir, test degil.
