# Domain Sozluk

* **Ghost** — workout planindan turetilen sanal referans yuzucu; hedef zaman-mesafe fonksiyonunu izler.
* **Length** — havuzun tek gecisi (25 m veya 50 m); duvar-duvar arasi.
* **Split** — bir length'in duvar zamani kaydi; source + qualityFlag tasir.
* **Gap** — ghost ile gercek yuzucu arasindaki fark (duvar aninda kesin: gap-at-wall).
* **Pace (sn/100 m)** — KUCUK sayi = HIZLI. Bu yuzden `fastestAllowedPaceSecPer100M` sayisal olarak
  `slowestAllowedPaceSecPer100M`'den kucuktur.
* **Normal / buyuk tempo kaybi (Durum A)** — yuzucu yorulup yavaslar; ghost ILERLER, performansa dahil.
  StopPause uygulanmaz.
* **Koc pacing reseti (Durum B)** — koc kalan seti tazeler; gecmis gap raporda kalir; saat durmaz.
  StopPause DEGILDIR.
* **StopPause (Durum C)** — LongStop/Incident/Coach Stop trigger'i dogrulaninca: workout/ghost/pace/rest
  saatleri BIRLIKTE durur; session RUNNING kalir; ghost yuzucuye KONTROLLU hizalanir; resmi muhasebe
  sonraki duvarda reconcile edilir.
* **StopTrigger** — StopPause'u baslatan tur: MANUAL_INCIDENT | LONG_STOP_THRESHOLD | COACH_STOP |
  SENSOR_STOP. "Incident" bir trigger turudur; core'un verdigi neden karari DEGILDIR.
* **Kontrollu vs kontrolsuz hizalama** — kontrolsuz teleport (rastgele/mid-length sicrama) yasaktir;
  kontrollu havuz-ortasi hizalama yalnizca dogrulanmis StopPause'da izinlidir.
* **Uc sure alani** — activeDurationSec (stop cikarilmis), stoppedDurationSec, elapsedDurationSec (toplam).
* **StopDetected** — nedensiz durma olayi kaydi (detectionSource/quality ile); nedeni koc degerlendirir,
  ML yalnizca yardimci olasilik (performanceRelatedStopProbability).
* **Aktif yuzme performansi** — stop sureleri cikarilmis metrikler.
* **Antrenman verimi** — durmalar dahil, nabiz/tempo devamliligi dahil sezon-sonu degerlendirmesi
  (TrainingEfficiencyMetrics).
