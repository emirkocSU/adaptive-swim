# Synthetic Veri Kurallari (ADR-032, L4)

* Her synthetic kayit `synthetic=true` + senaryo/seed provenance tasir.
* Sportif performans kaniti DEGILDIR; production accuracy iddiasinda kullanilmaz.
* Gercek pilot verisiyle kaynagi gizlenerek ayni tabloda birlestirilemez.
* Kullanim: controller edge case, replay, abstain, bad/delayed split, incident stop, sensor dropout,
  state machine + failure injection testleri.
