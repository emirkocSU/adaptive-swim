# CLAUDE.md — Coding Agent Sözleşmesi

Bu dosya, bu repository'de çalışan her insan ve her coding agent için bağlayıcıdır.
Kanonik kaynaklar: `ARCHITECTURE.md`, `docs/adr/`. Çelişki halinde ADR'ler kazanır.

**Faz 1 = Headless Core Vertical Slice.** UI yok, cloud yok, gerçek ML yok, wearable yok,
gerçek LED yok. Çıktı tamamen programatiktir.

---

## 1. Non-negotiables

1. `swimcore` **saftır**: I/O yok, dosya yok, soket yok, DB yok, framework yok, global saat yok,
   global rastgelelik yok. Zaman ve kimlik üretimi **enjekte edilir** (§4).
2. Kritik runtime'da **LLM yok** (Gemini, Claude API, hiçbiri).
3. Canlı pacing loop **cloud'suz** çalışır. Faz 1'de cloud kodu **hiç yoktur**.
4. ML çıktısı **hiçbir zaman** ışığı/feedback'i doğrudan kontrol etmez; deterministik bounded
   SafetyController'dan geçer. Düşük güven veya düşük veri kalitesinde **abstain → koç planı**.
5. Adaptasyon yalnızca **length veya güvenli segment sınırında** uygulanır. Segment ortasında asla.
6. **Manuel split ground truth değildir** (`COACH_TAP`, `BUTTON` → `MANUAL_UNVERIFIED`).
7. **Simulator gerçek `swimcore`'u embedded çalıştırır.** İkinci bir pacing/ghost implementasyonu
   yazmak yasaktır.
8. **Synthetic veri performans kanıtı değildir.** Her zaman `synthetic=true` + senaryo/seed
   provenance taşır; gerçek veriyle kaynağı gizlenerek birleştirilemez.
9. Pace alan sözlüğü **yalnızca** şudur (sn/100 m'de **küçük sayı = hızlı**):
   `fastestAllowedPaceSecPer100M` ≤ `targetPaceSecPer100M` ≤ `slowestAllowedPaceSecPer100M`,
   ayrıca `suggestedPaceSecPer100M`, `appliedPaceSecPer100M`.
   `minPace` / `maxPace` isimleri **yasaktır** (yön belirsizliği hataya davetiye).
10. Core IP kurucuda kalır (`LICENSE-NOTES.md`).

## 2. Bağımlılık kuralları (import-linter zorunlu kılar; ihlal CI'yı kırar)

```
swimtools  →  simulator  →  persistence  →  swimcore  →  contracts
```

* `contracts` → yalnızca stdlib + pydantic.
* `swimcore` → yalnızca `contracts`. **`contracts.external_data` HARİÇ** (ADR-032 sınırı).
* `swimcore` → `persistence` | `simulator` | `swimtools` import edemez.
* `persistence` → `contracts`, `swimcore`. I/O **yalnızca burada** (yerel dosya).
* `simulator` → `contracts`, `swimcore`, `persistence`. `swimtools` import edemez.
* Ghost StopPause ve alignment mantığı **yalnızca `swimcore` içinde** yaşar.

## 3. Faz 1'de YASAK olan her şey

`cloud/` · production `ml/` · tam `coach-ui/` · React/Vite/PWA · authentication/OIDC · sync worker ·
PostgreSQL · S3/object storage · model registry · OEM tenant · partner LED sürücüsü · wearable API
entegrasyonu · Garmin/FORM/Strava/Polar connector · Raspberry Pi image · Kubernetes · MQTT ·
mikroservis · LLM · kamera konum takibi · production data scraping.

**Boş klasör veya çalışmayan placeholder paket oluşturma.** Gelecek bileşenler yalnızca
`docs/plan/deferred-map.md` içinde yaşar.

## 4. Determinizm sözleşmesi (bit-identical replay'in ön koşulu) — ADR-033

Event üretimi **asla** global saate veya global rastgeleliğe dokunmaz.

* `swimcore.ports.Clock` — `now_ms() -> int`. Üretimde `SystemMonotonicClock`, testte `SimClock`.
* `swimcore.ports.EventIdGenerator` — `next_id() -> str`. Üretimde `Uuid4EventIdGenerator`,
  testte/simulator'da `DeterministicEventIdGenerator`.
* Her ikisi de session çekirdeğine **constructor ile enjekte edilir**. `time.time()`,
  `datetime.now()`, `uuid.uuid4()`, `random.*` çağrısını `swimcore` içinde **doğrudan yazmak
  yasaktır** (`tests/architecture/test_no_io_in_swimcore.py` AST ile yakalar).
* **ULID kullanılmaz.** Kimlik = `uuid4` (opak), sıralama = session içi monotonik `seq`.
  Ek bağımlılık yok.

## 5. Persistence sözleşmesi (log-first) — ADR-003 (amended)

```
1) Event, append-only JSONL log'a TAM SATIR olarak yazılır
2) Durability: fsync
3) ANCAK ONDAN SONRA türetilmiş görünüm (projection) güncellenir
4) Projection her an log'dan deterministik fold ile yeniden kurulabilir
```

**Dürüst dayanıklılık garantisi (abartma):**

* Ani sonlanmada dosyanın **son satırı yarım kalabilir**. Bu normaldir.
* Sistem açılışta bunu **fark eder** ve **yalnızca bozuk son satırı** güvenli biçimde keser
  (`LogTailTruncated` teşhisiyle raporlar).
* Daha önce `fsync` edilmiş event'ler **değişmez ve kaybolmaz**.
* Kayıp penceresi **yalnızca son `fsync`'ten sonraki event'ler** için geçerlidir
  (`fsync_policy=batch_50ms` iken ≤ 50 ms; `per_event` iken sıfır).
* **`kill -9` testi yalnızca süreç çökmesini ölçer.** Elektrik kesintisi ve disk arızası farklı
  hata sınıflarıdır (page tearing, disk cache reordering) ve `kill -9` ile kanıtlanmaz; bunlar
  gerçek donanımda ayrıca doğrulanır. Belgede/testte bu iki sınıfı **karıştırma**.

## 6. Durma modeli — Stop Pause and Ghost Alignment (ADR-031)

**Üç durum asla karışmaz ve core durmanın nedenine KARAR VERMEZ.**

**A) Normal/büyük tempo kaybı (performans).** Ghost **ilerler**, workout clock **ilerler**, fark
korunur, veri performans analizine **dahildir**. StopPause **uygulanmaz**. Ölçmek istediğimiz şey budur.

**B) Koç pacing reseti.** Ayrı `CoachPacingReset` komutu. Önceki kötü performans **raporda kalır** (gap
silinmez); yalnızca **sonraki güvenli duvar boundary'sinde** yeni pacing referansı başlar; workout
clock **durmaz**. StopPause değildir.

**C) LongStop / Incident / Coach Stop → StopPause.** Trigger türü: `MANUAL_INCIDENT |
LONG_STOP_THRESHOLD | COACH_STOP | SENSOR_STOP`. "Incident" yalnızca bir trigger'dır, core'un verdiği
bir neden kararı **değildir**.
* Mantıksal saatler **birlikte** durur: workout + ghost + pace schedule + rest countdown. **Session
  RUNNING kalır; real clock çalışır.**
* Durdurma durmanın **başladığı ana geri dönüktür** (`stopStartedAtMs`) — eşik anına değil.
* **Havuz-ortası ghost alignment:** ghost yüzücünün takip edilen noktasına hizalanır; ilk eşik-süresi
  fark silinir. Bu **kontrollü** hizalamadır ve **yalnızca doğrulanmış StopPause sırasında** izinlidir.
* **Duvarda reconcile:** set/repetition/length/split/pace segmenti/dinlenme havuz ortasında yeniden
  yazılmaz; resmi workout akışı **bir sonraki geçerli duvarda** reconcile edilir. Sistem yüzücünün
  "tam kaçıncı metrede durduğunu" hesaplamak/saklamak/raporlamak **zorunda değildir**.
* Resume: ghost aynı noktadan aynı hedef tempoyla; workout clock kaldığı saniyeden; planlı dinlenmeler
  korunur (StopPause sonraki duvardaki dinlenmeden düşülmez; dinlenme sırasında StopPause olursa
  dinlenme sayacı da durur).

**Kontrolsüz vs kontrollü hizalama.** Yasak olan şey **kontrolsüz** teleport'tur (rastgele/mid-length
atlama, konum tahminine dayalı ani sıçrama). **Kontrollü** havuz-ortası hizalama (doğrulanmış
StopPause'da yüzücünün takip edilen noktasına) **izinlidir**. Resmi muhasebe duvarda reconcile edilir.

**Stop detection modu.** *Manual (Faz 1 varsayılanı):* koç `MarkStopPause`/STOP-RESUME komutu; otomatik
sensör **varsayılmaz**. *Sensor-assisted (ileride):* IMU hareketten durma; `longStopThresholdSec = 10`
**varsayılan hipotez**; 10 sn'de karar verilse bile stop süresi **hareketin ilk kesildiği andan**
hesaplanır; sensör kalitesi düşükse otomatik StopPause başlatılmaz veya düşük güvenle raporlanır.
Sözleşme alanları: `detectionSource`, `detectionQuality`, `alignmentSource`, `alignmentQuality`,
`stopStartTimeQuality`.

**Süre muhasebesi (üç alan).** `activeDurationSec` (stop çıkarılmış), `stoppedDurationSec`,
`elapsedDurationSec` (= active + stopped). Gösterim: `20.00 +15.00`, toplam gerektiğinde `35.00`.

**Length'i otomatik çöpe atma YOK.** Stop baş/bitiş **güvenilir** biliniyorsa length atılmaz: aktif +
stop süresi ayrı tutulur, pace'ten stop çıkarılır, stop verim raporunda görünür (`lengthAnalyzable =
true`). **Yalnızca** zaman/stop bilgisi güvenilmezse length analiz dışı (`STOP_TIME_UNRELIABLE`).

**Nedeni kaydedilmez.** Core "yoruldu/çarpıştı" demez; durmayı + süresini + bağlamını kaydeder, koça
iletir. Neden **koç**un, olasılık **ML**'in (yalnızca yardımcı; §7).

**Ortak değişmezler.** StopPause session state'ini değiştirmez (RUNNING kalır); `SessionPaused` (koç,
tüm seansı dondurur) ile **karıştırma**. Komutlar idempotent; StopPause `Split.qualityFlag`'i **asla**
INVALID yapmaz; dışlama ayrı eksende (`AnalyticsExclusionReason`). `affectedLengthIndices`:
başladığı in-progress length dahil, reconcile duvarının length'i dahil, sonrası temiz.

## 7. External data sınırı (ADR-032)

* `contracts.external_data` **plan-level**dir; `swimcore` onu import **edemez**.
* Race verisi (L1) antrenman verisi **değildir**; wearable pretraining (L2) final pacing modelinin
  yerine **geçmez**; synthetic (L4) kanıt **değildir**. Final iddia yalnızca Adaptive Swim
  proprietary verisi (L5) üzerinde athlete-grouped + time-aware validation ile kurulur.
* `data_domain` olmadan hiçbir kaynak birleştirilemez. Missingness korunur; **sahte doldurma yok**.
* Hiçbir kaynak için erişim/lisans/ticari kullanım hakkı **varsayılmaz**
  (`TBD_VERIFICATION_REQUIRED`). ToS'u aşan scraping planlanmaz.
* `confidence = quantile interval width` **yasaktır** (ADR-030). Quantile yalnızca bir girdidir.

## 8. Komutlar

```
make setup             # venv + dev bağımlılıkları
make lint              # ruff check + format --check
make typecheck         # mypy --strict
make test-unit
make test-property     # hypothesis (ci profili: deterministik)
make test-replay       # golden replay bit-identity
make test-simulator    # senaryo matrisi
make test-architecture # import-linter + yasak dizin/IO taraması
make schema-check      # üretilen JSON Schema == commit'lenen (aksi halde fail)
make e2e-headless      # ağ kapalı uçtan uca
make ci                # HEPSİ. Her commit sonunda yeşil olmak ZORUNDA.
```

## 9. Forbidden shortcuts

* `swimcore`'a I/O eklemek (dosya, soket, DB, subprocess).
* `contracts/schemas/*.json`'ı **elle** düzenlemek. Şema yalnızca `make schema-check` /
  `swimtools.gen_schemas` ile üretilir; elle düzenleme CI'da yakalanır.
* Simulator'a ikinci bir pacing/ghost matematiği yazmak.
* Incident dışlamasını `qualityFlag = INVALID` ile modellemek.
* Ghost'u mid-length teleport ettirmek veya konum tahminine göre yeniden konumlandırmak.
* `time.time()` / `uuid4()` / `random` çağrısını domain koduna gömmek.
* Testleri "yeşil olsun diye" zayıflatmak; bir değişmez düşerse **kod düzeltilir, test değil**.
* Boş `ml/`, `cloud/`, `ui/`, `adapters/` klasörü açmak.

## 10. Çalışma ritmi

Her commit: (a) tek konuya odaklı, (b) kendi testleriyle gelir, (c) `make ci` yeşil bırakır,
(d) tek `git revert` ile geri alınabilir. Commit sonunda raporla: değişen dosyalar, koşan testler,
açık riskler, sonraki küçük iş.
