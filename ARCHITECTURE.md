# ARCHITECTURE.md

Adaptive Swim Pacing Platform'un yaşayan mimari özeti. Kanonik kaynaklar: `docs/adr/`.
Bu dosya ile bir ADR çelişirse ADR kazanır.

**Durum:** Faz 1 — Headless Core Vertical Slice. UI yok, cloud yok, gerçek ML yok, wearable yok,
gerçek LED yok. Her şey programatik, deterministik, ağ erişimi olmadan.

---

## 1. Ürün tek paragrafta

Ürün bir ışık şeridi değil, bir **pacing beynidir**. Koç yapılandırılmış bir antrenman tanımlar
(workout DSL). Sistem bunu bir zaman–mesafe fonksiyonuna çevirir ve "ghost" adlı sanal bir referans
yüzücüyü havuz boyunca ilerletir. Gerçek yüzücünün duvar splitleri sisteme akar; sistem hedef ile
gerçekleşen arasındaki farkı ölçer, kaydeder ve açıklanabilir bir rapor üretir. Yeterli ve
**doğrulanmış** veri biriktiğinde bir ML modeli "bir sonraki uzunluk için sürdürülebilir tempo"
tahmini üretebilir; bu tahmin **asla** doğrudan feedback donanımını kontrol etmez — deterministik,
sınırlı bir güvenlik kontrolcüsünden geçer, geçemezse sistem koçun sabit planına döner.

## 2. Mimari çekirdek (değişmez temel)

Local-first, simulator-first **modular monolith**. Saf, donanımdan bağımsız Python `swimcore`
paketi (workout modeli, iki katmanlı validator, pace matematiği, ghost + incident mantığı,
session state, deterministik safety controller, analitik). Bu çekirdeği MVP'de iki host çalıştırır:
**headless simulator** (aynı çekirdeği embedded çalıştırır) ve **edge runtime** (laptop, asyncio,
SQLite + append-only JSONL — Faz 2). Canlı pacing loop cloud'suz. ML çıktısı ışığı kontrol etmez.
Adaptasyon yalnızca length/segment sınırında. Manuel split ground truth değildir. Cloud/tenant/
auth/registry/PWA/OEM erken fazda yok.

## 3. Faz 1 paket topolojisi

```
swimtools  →  simulator  →  persistence  →  swimcore  →  contracts
```

* `contracts` — tüm veri sözleşmeleri, enum'lar, event zarfı, JSON Schema'nın tek kaynağı. I/O yok.
* `swimcore` — saf domain. I/O yok, framework yok, duvar saati yok, global rastgelelik yok.
* `persistence` — append-only JSONL log + deterministik replay. I/O yalnızca burada.
* `simulator` — sanal yüzücü + senaryolar; gerçek `swimcore`'u embedded çalıştırır.
* `swimtools` — geliştirici/CI CLI'ları.

Bağımlılık kuralları import-linter ile CI'da zorlanır (`.importlinter`).

## 4. Determinizm sözleşmesi (ADR-033)

Bit-identical replay için event üretimi global saate/rastgeleliğe dokunmaz. `swimcore.ports.Clock`
ve `swimcore.ports.EventIdGenerator` çekirdeğe **enjekte** edilir: üretimde `SystemMonotonicClock`
+ `Uuid4EventIdGenerator`, testte/simulator'da `SimClock` + `DeterministicEventIdGenerator`.
ULID kullanılmaz; kimlik = `uuid4` (opak), sıralama = session içi monotonik `seq`.

## 5. Persistence sözleşmesi (ADR-003, log-first)

`event → append JSONL (tam satır) → fsync → sonra türetilmiş görünüm`. Dürüst garanti: ani
sonlanmada **son satır yarım kalabilir**; sistem açılışta fark eder ve yalnızca bozuk son satırı
keser (`LogTailTruncated`); daha önce `fsync` edilmiş event'ler değişmez; kayıp penceresi yalnızca
son `fsync`'ten sonrasıdır. `kill -9` yalnızca süreç çökmesini ölçer — elektrik kesintisi ve disk
arızası farklı hata sınıflarıdır ve gerçek donanımda ayrıca doğrulanır.

## 6. Ghost ve durma modeli — **Stop Pause and Ghost Alignment** (ADR-031)

En kritik davranışsal karar. Yüzücünün durması **üç ayrı duruma** ayrılır ve bunlar asla karışmaz:

### Durum A — Normal veya büyük tempo kaybı (performans)
Yüzücü yorulup yavaşlar veya ciddi tempo kaybeder. → **Ghost ilerler, fark korunur, workout clock
durmaz, veri performans analizine dahildir.** Sistem bunu incident gibi temizlemez veya gizlemez —
çünkü ölçmek istediğimiz şey tam olarak budur.

### Durum B — Koç pacing reseti
Koç, büyük tempo kaybından sonra kalan seti anlamlı kılmak için açık bir reset komutu verir. →
**Önceki kötü performans raporda kalır** (gap silinmez); yalnızca sonraki güvenli duvar sınırında
yeni bir pacing referansı başlar; **workout clock durmaz**. Bu bir LongStop değildir; performansı
analiz dışı bırakmaz.

### Durum C — LongStop / Incident / Coach Stop → StopPause
Trigger: `MANUAL_INCIDENT | LONG_STOP_THRESHOLD | COACH_STOP | SENSOR_STOP`. "Incident"
yalnızca bir trigger türüdür; core durmanın nedenine karar vermez. → **StopPause:**

* Mantıksal saatler **birlikte** durur: workout clock, ghost clock, target pace schedule, rest
  countdown. **Session RUNNING kalır; real clock çalışır.**
* Saat, durmanın **başladığı ana geri dönük** durdurulur — eşiğin aşıldığı ana değil. Yüzücü 18 sn
  beklediyse incident süresi 18 sn'dir, son 8 sn değil.
* **Havuz-ortası ghost alignment (kontrollü):** ghost yüzücünün takip edilen noktasına hizalanır;
  ilk eşik-süresi fark silinir. Bu hizalama yalnızca doğrulanmış StopPause sırasında izinlidir.
  Kontrolsüz (rastgele/mid-length) teleport yasaktır.
* Kalan mesafe, set, repetition değişmez; hedef tempo planı değişmez.
* **Duvarda reconcile:** set/repetition/length/split/pace segmenti/dinlenme havuz ortasında yeniden
  yazılmaz; resmi workout akışı bir sonraki geçerli duvarda reconcile edilir. Sistem yüzücünün "tam
  kaçıncı metrede durduğunu" hesaplamak/saklamak/raporlamak zorunda değildir.

Resume: ghost aynı noktadan, aynı hedef tempoyla devam eder; workout clock kaldığı saniyeden sürer;
planlı dinlenmeler korunur (incident, sonraki duvardaki planlı dinlenmeden düşülmez; dinlenme
sırasında incident olursa dinlenme sayacı da durur).

**Durmanın nedeni kaydedilmez.** Sistem "yoruldu / çarpıştı / gözlük" diye karar vermez. Yalnızca
`StopDetected` olayını (başlangıç, bitiş, süre, set/length, o anki sensör verileri) kaydeder ve
canlı olarak koça iletir; nedeni **koç** değerlendirir ve isterse not ekler.

### Süre muhasebesi ve length'i çöpe atmama
Her length üç süre taşır: `activeDurationSec` (stop çıkarılmış), `stoppedDurationSec`,
`elapsedDurationSec` (= toplam). Gösterim `20.00 +15.00`. Stop baş/bitiş **güvenilir** biliniyorsa
length **atılmaz**: aktif ve stop süresi ayrı tutulur, pace'ten stop çıkarılır, stop verim raporunda
gösterilir. **Yalnızca** zaman/stop bilgisi güvenilmezse (`stopStartTimeQuality`/`alignmentQuality`
düşük) length analiz dışı bırakılır (`STOP_TIME_UNRELIABLE`).

**Stop detection modu.** Manual (Faz 1): koç `MarkStopPause`; otomatik sensör varsayılmaz.
Sensor-assisted (ileride): IMU; `longStopThresholdSec=10` varsayılan hipotez; stop süresi hareketin
ilk kesildiği andan; sensör kalitesi düşükse otomatik StopPause başlatılmaz. Alanlar:
`detectionSource/detectionQuality/alignmentSource/alignmentQuality/stopStartTimeQuality`.

## 7. ML'nin rolü (gate sonrası — yalnızca yardımcı)
ML durma davranışını **kontrol etmez** (ghost'u/clock'u durdurmaz, StopPause başlatmaz); yalnızca koça
`performanceRelatedStopProbability` sunar, nabız + nabız trendi, son length'lerdeki pace düşüşü,
pace sürekliliği bozulması, stroke rate/count, SWOLF, yüksek tempoda kalma süresi, stop öncesi/
sonrası performans ve sensör kalitesine bakarak. Bu çıktı ghost'u durdurmaz, incident başlatmaz,
workout clock'u değiştirmez, kesin neden olarak kaydedilmez.

## 8. İki ayrı sonuç (rapor)
* **Aktif yüzme performansı** (durma süreleri çıkarılmış): aktif pace, hedef tempo sapması, tempo
  istikrarı, negative split, aktif yüksek-tempo süresi.
* **Antrenman verimi** (durmalar dahil): kaç kez/kaç saniye durdu, en uzun durma, hangi setlerde,
  yüksek tempoda kalınan süre ve oran, tempo düşüşünün başladığı nokta, set içi kırılma noktaları,
  nabız–pace ilişkisi, stop öncesi/sonrası fark, aktif yüzme süresi, toplam geçen süre, set/
  antrenman bazında verim, durmaların performans kaynaklı olma ihtimali.

Pacing performansı incident süresinden etkilenmez; incident yalnızca operasyonel bölümde görünür —
ama **gizlenmez**.

## 9. Üç durumun özeti

| Durum | Ghost | Workout clock | Performansa dahil? |
|---|---|---|---|
| Normal/büyük tempo kaybı | İlerler | İlerler | Evet |
| Koç pacing reseti | Duvar sınırında yeniden başlar | İlerler | Önceki kayıp dahil |
| LongStop / Incident / Coach Stop (StopPause) | Yüzücüye hizalanıp bekler | Durur (geri dönük) | Stop süresi pace hesabından çıkar, raporda görünür |
