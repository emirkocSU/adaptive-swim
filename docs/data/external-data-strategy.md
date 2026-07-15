# Dis Veri Stratejisi (ADR-032)

Bes katman, kati rol ayrimiyla. Hicbiri final production model ile ayni degerde degildir.

* **L1 Race Pacing Prior** — pacing egrileri, split profilleri, simulator gercekciligi, cold-start.
  Antrenman verisi DEGILDIR.
* **L2 Wearable Sensor Pretraining** — swim/rest, turn/transition, segmentation, sensor quality,
  incident-benzeri kesinti ONERISI. Final modelin yerine gecmez.
* **L3 User-Consented Training Exports** — gercek antrenman verisi, baseline modelleri. Acik izin +
  provenance zorunlu.
* **L4 Simulator Synthetic** — edge case/replay/failure injection. Performans kaniti DEGILDIR;
  `synthetic=true` + scenario provenance zorunlu.
* **L5 Adaptive Swim Proprietary** — final model ESAS kaynagi. Iddia yalnizca bunun uzerinden
  (athlete-grouped + time-aware validation).

Gate ayrimi: pre-gate research (parser, cleaning, schema mapping, prior analizi) edge runtime'a
baglanamaz, `bounded_auto`'yu kontrol edemez, urun iddiasi olusturamaz. Production activation yalnizca
G1-G7 acikken.

`confidence = quantile interval width` YASAKTIR (ADR-030). Quantile yalnizca bir girdidir.
