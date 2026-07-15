# ADR-031 — Stop Pause and Ghost Alignment Policy

**Statü:** ACTIVE (bu ürün için)
**Faz:** 1
**Tarih:** 2026-07-14 (rev. 2026-07-15)
**Supersedes:** "Ghost Recovery / Re-Anchor" taslağı **ve** ilk "Incident Pause" adlandırması.

## Context

Ghost'un "yüzücü durursa her koşulda ilerlemeye devam etmesi" davranışı, dışsal/uzun kesintilerde
anlamsız bir "gap" biriktiriyordu. Önceki taslaklar önce bir re-anchor komutu, sonra "Incident
Pause" getirdi. Ancak **"incident" kelimesi core'un durmanın nedenine karar verdiğini ima ediyordu** —
oysa sistem nedeni bilmez ve bilmemeli. Bu ADR terminolojiyi nötrleştirir: genel kavram **StopPause**;
"incident" yalnızca StopPause'u başlatan bir **trigger türü**dür.

## Problem

Üç kavramsal olarak farklı durum vardır; core bunları **karıştırmamalı** ve durmanın nedenine
**karar vermemelidir**:

1. Yüzücü yorulup yavaşlar (normal veya büyük tempo kaybı) — bu ölçmek istediğimiz **performanstır**.
2. Koç, kalan seti anlamlı kılmak için **pacing reseti** ister — geçmiş silinmemeli, yalnızca ileri
   referans güvenli duvarda tazelenmeli.
3. Uzun/dışsal bir durma olur — pacing hesabını bozmamalı ama gizlenmemeli.

Fiziksel sınır: gerçek havuzda yalnızca duvar splitleri varsa sistem yüzücünün orta length'teki
**kesin konumunu bilemez**; "330. metrede durdu" gibi kesin etikete bağımlı tasarım kırılgandır.

## Considered options

1. Her durumda ghost devam (eski) — dışsal/uzun durmada metrikleri kirletir.
2. Session PAUSED — set/repetition bağlamını ve koç iş akışını bozar.
3. GhostSuspend + sonraki duvarda re-anchor — gereksiz karmaşık; basit pause/resume'un yerine geçmişti.
4. **Seçilen — StopPause + havuz-ortası ghost alignment + duvarda reconcile:** durma doğrulanınca
   mantıksal saatler durur, ghost havuz ortasında yüzücünün takip edilen noktasına hizalanır ve
   birlikte bekler; resmi workout muhasebesi **bir sonraki duvarda** reconcile edilir.

## Decision

**Üç durum kesin ayrılır. Core durmanın nedenine karar vermez.**

**A) Normal / büyük tempo kaybı (performans).** Ghost ilerler, workout clock ilerler, fark korunur,
veri performans analizine dahildir. StopPause **uygulanmaz**.

**B) Koç pacing reseti.** Ayrı manuel komut (`CoachPacingReset`). Önceki kötü performans (gap dahil)
raporda kalır; yalnızca **sonraki güvenli duvar boundary'sinde** yeni pacing referansı başlar; workout
clock **durmaz**. Bu bir StopPause **değildir**.

**C) LongStop / Incident / Coach Stop → StopPause.** Trigger türleri (`StopTrigger`):
`MANUAL_INCIDENT`, `LONG_STOP_THRESHOLD`, `COACH_STOP`, `SENSOR_STOP`. Bu trigger'lardan biri
doğrulanınca:

* **Mantıksal saatler birlikte durur:** workout clock, ghost clock, target pace schedule, rest
  countdown. **Session RUNNING kalır. Real clock çalışır.**
* Durdurma, durmanın **başladığı ana geri dönüktür** (`stopStartedAtMs`) — eşiğin aşıldığı ana değil.
  18 sn beklendiyse stop süresi 18 sn'dir.
* **Havuz ortası ghost alignment:** ghost, yüzücünün o an takip edilen noktasına hizalanır ve birlikte
  beklerler. Bu **kontrollü** bir hizalamadır ve yalnızca doğrulanmış StopPause sırasında izinlidir.
  İlk eşik-süresi ghost farkı **silinir**.
* **Duvarda reconcile:** havuz ortasında set, repetition, length sayacı, split, pace segmenti ve
  planlı dinlenme hesabı **yeniden yazılmaz**. Yüzücü bir sonraki duvara geldiğinde resmi workout
  akışı reconcile edilir: length tamamlanır, split kesinleşir, set/repetition ilerler, dinlenme ve
  pace segmentleri normal bağlamından devam eder. Sistem yüzücünün "tam kaçıncı metrede durduğunu"
  hesaplamak, saklamak veya raporlamak **zorunda değildir**.
* **Resume:** ghost aynı noktadan aynı hedef tempoyla devam eder; workout clock kaldığı saniyeden;
  planlı dinlenmeler korunur (StopPause, sonraki duvardaki dinlenmeden düşülmez; dinlenme sırasında
  StopPause olursa dinlenme sayacı da durur).

**Kontrollü vs kontrolsüz hizalama (kural).**
> Controlled mid-length ghost alignment is allowed **only** during confirmed StopPause.
> Official workout accounting is reconciled at the next valid wall boundary.

Yani **kontrolsüz** teleport (rastgele/mid-length atlama, konum tahminine dayalı ani sıçrama)
yasaktır; **kontrollü** havuz-ortası hizalama (doğrulanmış StopPause'da yüzücünün takip edilen
noktasına) izinlidir.

**Nedeni kaydedilmez.** Sistem "yoruldu / çarpıştı / gözlük" kararı vermez; yalnızca durmayı, süresini
ve bağlamını kaydeder ve koça iletir. Nedeni **koç** değerlendirir, isterse sonradan not ekler.

## Stop detection: kaynak ve kalite (mod ayrımı)

Otomatik durma algılaması ancak **güvenilir stop detection sinyali** varsa çalışır.

* **Manual mode (Faz 1/MVP varsayılanı):** koç `MarkStopPause` / STOP-RESUME komutu verir; stop süresi
  koç komutundan hesaplanır; otomatik sensör **varsayılmaz**.
* **Sensor-assisted mode (ileride):** wearable/IMU hareketten durmayı algılayabilir.
  `longStopThresholdSec = 10` **varsayılan hipotezdir** (koç değiştirebilir). Sistem 10 sn'de karar
  verse bile stop süresi **hareketin ilk kesildiği andan** hesaplanır. Sensör kalitesi düşükse
  otomatik StopPause **başlatılmaz** veya düşük güvenle raporlanır.

## Commands

```
MarkStopPause(trigger, occurredAtMs?, notes?, clientCommandId)
    trigger ∈ {MANUAL_INCIDENT, LONG_STOP_THRESHOLD, COACH_STOP, SENSOR_STOP}
    occurredAtMs verilmezse durmanin algilandigi an; retroaktif dondurmede stopStartedAtMs kullanilir.

ResolveStopPause(resumedAtMs, clientCommandId)
    Yuzucu devam etti. stoppedDurationSec = resumedAtMs - stopStartedAtMs.

CoachPacingReset(reason, clientCommandId)         # DURUM B — ayri komut, StopPause DEGIL
    Sonraki guvenli duvarda yeni pacing referansi; workout clock durmaz; gecmis gap raporda kalir.
```

Tüm komutlar **idempotent**tir: aynı `clientCommandId` ikinci StopPause açmaz, saati ikinci kez
düşmez, ikinci reset uygulamaz. Açık bir StopPause varken ikinci `MarkStopPause` yeni pause açmaz.

## Events

```
StopDetected      {stopStartedAtMs, setIndex, lengthIndex, sensorSnapshot?,
                   detectionSource: COACH|SENSOR|ESTIMATOR|THRESHOLD,
                   detectionQuality: HIGH|MEDIUM|LOW|UNKNOWN,
                   stopStartTimeQuality: HIGH|MEDIUM|LOW|UNKNOWN}
LongStopConfirmed {stopStartedAtMs, confirmedAtMs, trigger, longStopThresholdSec}
StopPauseStarted  {stopPauseId, trigger, stopStartedAtMs, atLengthIndex,
                   alignedGhostDistanceM?, alignmentSource: SENSOR|COACH|ESTIMATE|NONE,
                   alignmentQuality: HIGH|MEDIUM|LOW|UNKNOWN, notes?}
StopPauseResolved {stopPauseId, resumedAtMs, stoppedDurationSec,
                   reconciledAtWallLengthIndex?, affectedLengthIndices[],
                   lengthAnalyzable: bool, analyticsEligible, mlLabelEligible}
CoachPacingReset  {resetId, requestedAtMs, effectiveBoundaryLengthIndex, reason}
```

`stoppedDurationSec` event payload'ında saklanır → replay, mantıksal saat düşümünü kayan nokta yeniden
hesabı yapmadan birebir uygular; fold yine de yeniden hesaplayıp **doğrular**, uyuşmazlıkta
`ReplayMismatch` fırlatır.

## State changes

Session state machine **değişmez** (RUNNING kalır). Ayrı, küçük bir **ghost/workout timing sub-state**:

```
ACTIVE
  ├── kisa durma (< longStopThresholdSec) ve devam    → ACTIVE (saat durmaz; Durum A)
  ├── MarkStopPause / durma >= threshold (güvenilir)   → STOP_PAUSED (Durum C)
  └── CoachPacingReset                                 → ACTIVE (Durum B; saat durmaz, referans
                                                            sonraki duvarda)
STOP_PAUSED
  ├── ResolveStopPause / yuzucu devam etti             → ACTIVE (saat kaldigi yerden)
  └── SessionCompleted / SessionAborted                → terminal cleanup (pause kapatilir)
```

State verisi: `longStopThresholdSec`, `stopStartedAtMs?`, `openStopPauseId?`, `cumulativeStoppedMs`,
`alignedGhostDistanceM?`. STOP_PAUSED iken workout/ghost/pace/rest saatleri donuktur; real clock akar.

## Consequences

**Süre muhasebesi (üç alan).** Her length ve seans üç süreyi ayrı taşır:

```
activeDurationSec   — aktif yüzme süresi (stop çıkarılmış)
stoppedDurationSec  — StopPause süresi
elapsedDurationSec  — gerçek geçen süre = active + stopped
```

Ekran/rapor gösterimi: `20.00 +15.00` (20.00 aktif, +15.00 stop); gerektiğinde toplam `35.00` ayrıca.

**Length'i otomatik çöpe atma YOK.** Stop başlangıcı ve bitişi **güvenilir** biliniyorsa length tamamen
atılmaz: aktif süre ve stop süresi ayrı tutulur, pace hesabından stop süresi çıkarılır, stop süresi
verim raporunda ayrıca gösterilir (`lengthAnalyzable = true`). **Yalnızca** zaman/stop bilgisi
güvenilir değilse (`stopStartTimeQuality` düşük veya `alignmentQuality` düşük) length analiz dışı
bırakılır (`lengthAnalyzable = false`, `exclusionReason = STOP_TIME_UNRELIABLE`). `Split.qualityFlag`
StopPause nedeniyle **asla** INVALID yapılmaz.

**ML (gate sonrası, yalnızca yardımcı).** ML durma davranışını **kontrol etmez**; ghost'u durdurmaz,
clock'u durdurmaz, StopPause başlatmaz. Yalnızca koça bir çıktı sunar:
`performanceRelatedStopProbability`. Girdiler: nabız + trend, pace sürekliliği, pace düşüşü, stroke
rate/count, SWOLF, yüksek tempoda kalma süresi, stop öncesi/sonrası performans, önceki splitler,
sensör kalitesi.

**affectedLengthIndices sınır anlamı.** StopPause'un başladığı **in-progress length dahil**; reconcile
edildiği duvarın kapattığı length **dahil**; o duvardan **sonra başlayan** length **temizdir**. Yüzücü
duvardayken başlayıp aynı duvarda reconcile edilen StopPause hiçbir length'i dışlamaz (`[]`).

## Reversibility

ORTA. Timing sub-state ve event'ler eklemedir; session sözleşmesi kırılmaz. Ancak süre muhasebesi ve
"saat durdurma" semantiği geri alınırsa geçmiş raporlar yeniden yorumlanır; Faz 1'de kilitlenir. Eski
re-anchor ve "Incident Pause" adlandırmaları bu ADR ile supersede edilmiştir.

## Validation

* Değişmez testleri (`docs/testing/invariants.md`): A'da ghost durmaz; C'de saatler birlikte durur;
  frozen süre geri dönük; kontrollü hizalama yalnızca StopPause'da; duvarda reconcile; idempotency;
  StopPause ≠ INVALID; güvenilir stop → length atılmaz, güvenilmez → analiz dışı; üç süre alanı.
* Simulator senaryoları: normal tempo kaybı; eşik-aşımı long stop; koç-işaretli stop; iki kez işaret
  (idempotency); dinlenme sırasında stop; konum/zaman güvenilmez → length analiz dışı + duvarda
  reconcile; paused iken session completed; coach pacing reset.
* Golden replay: StopPause + resume zinciri bit-identical; `stoppedDurationSec` doğrulaması.
