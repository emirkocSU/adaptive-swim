# ADR-032 — External Data Bootstrapping Strategy

**Statü:** ACTIVE (Faz 1'de yalnızca doküman + plan-level contract; pipeline sonraki research epic)
**Faz:** 1 (doküman/contract), sonra ayrı research epic
**Tarih:** 2026-07-14

## Context
ML ve simulator çalışmaları yalnızca kendi donanımından gelecek veriyi beklememelidir. Ancak dış
kaynaklar final production adaptive model ile aynı değerde/amaçta kabul edilemez. Rolleri katı
ayrılmalıdır.

## Problem
Dış veriyi kullanmak istiyoruz (cold-start, simulator gerçekçiliği, baseline hazırlığı) ama (a) race
verisini training verisi sanmak, (b) synthetic'i performans kanıtı yapmak, (c) lisanssız/izinsiz
kullanmak, (d) gate'i zayıflatmak risklerinden kaçınmalıyız.

## Considered options
1. Sadece kendi verisi — cold-start yavaş, simulator az gerçekçi.
2. Dış veriyi serbestçe karıştır — bilimsel ve hukuki felaket.
3. **Seçilen — katı rol taksonomisi (5 katman) + provenance registry + gate ayrımı.**

## Decision — Data role taxonomy

| Katman | Rol | Kesin sınır |
|---|---|---|
| L1 Race Pacing Prior | Mesafe/stile göre pacing eğrileri, split-index etkisi, split profilleri, simulator gerçekçiliği, cold-start prior | **Antrenman verisi değildir.** Ghost feedback tepkisi, koç hedefi uyumu, bounded adaptation, dinlenme yapısı, incident etkisi bundan öğretilemez |
| L2 Wearable Sensor Pretraining | swim/rest ayrımı, turn/transition detection, lap segmentation, sensor quality scoring, incident-**benzeri** kesinti *önerisi*, split reliability tahmini | Final pacing modelinin yerine geçmez |
| L3 User-Consented Training Exports | Gerçek antrenman length/lap, stroke count/rate, pace, rest, SWOLF, HR trend, next-length **baseline**, pilot öncesi training-context feature pipeline | Açık izin + provenance + amaç zorunlu |
| L4 Simulator Synthetic | Controller edge case, replay, abstain, bad/delayed split, incident stop, sensor dropout, state machine + failure injection | Performans kanıtı **değildir**; kaynağı gizlenerek gerçek veriyle birleştirilemez; her zaman `synthetic=true` + scenario provenance |
| L5 Adaptive Swim Proprietary | **Final production adaptive model için esas kaynak** | Final model bununla fine-tune + athlete-grouped/time-aware validate; **iddia yalnızca bunun üzerinden** |

## Consequences

**Gate ile ilişki.** v1.1'deki G1–G7 ML Activation Gate **korunur**. İki faaliyet ayrılır:
*Pre-gate research* (kaynak araştırması, lisans/erişim doğrulama, parser prototipi, cleaning, schema
mapping, normalized research schema, pacing prior analizi, simulator kalibrasyonu, non-production
baseline, wearable task-specific araştırma) — edge runtime'a bağlanamaz, `bounded_auto`'yu kontrol
edemez, production artefact paketleyemez, ürün performansı iddiası oluşturamaz. *Production
activation* (production feature pipeline, training, calibrated uncertainty, shadow, suggest-only,
bounded-auto eligibility, versiyonlu artefact) yalnızca gate açıkken.

**Confidence.** `confidence = quantile interval width` **yasaktır** (ADR-030). Quantile yalnızca bir
girdidir.

**Provenance & lisans.** Her kaynak `DataSourceRegistryEntry` (18 alan) ile kayıtlanır. Belirsiz
erişim/lisans → `TBD_VERIFICATION_REQUIRED`. ToS'u aşan scraping planlanmaz.

**Normalized research schema.** Provider-bağımsız `NormalizedSwimmingRecord`; `data_domain`
(`ELITE_RACE | TRAINING_EXPORT | WEARABLE_SENSOR | ADAPTIVE_SWIM_SESSION | SYNTHETIC_SIMULATION`)
**olmadan birleştirme yasak**; missingness korunur, sahte doldurma yok.

**Repository sınırı.** Faz 1'de: bu ADR + external data strategy dokümanı + DataSourceRegistry
sözleşme taslağı + normalized research schema taslağı + provenance/synthetic kuralları. Faz 1'de
**oluşturulmaz**: production `ml/`, model registry, production inference, Garmin/FORM/Strava/Polar
entegrasyonu, data lake, scraper, cloud storage, wearable NN, production pacing model. Boş `ml/`,
`cloud/` veya provider adapter klasörü **açılmaz**. `contracts.external_data`, `swimcore` tarafından
import **edilemez** (import-linter forbidden).

## Reversibility
KOLAY (doküman/contract seviyesi). Gerçek pipeline ayrı research epic'inde, ayrı reversibility ile.

## Validation
* `swimcore → contracts.external_data` import'u import-linter ile reddedilir.
* `NormalizedSwimmingRecord` birleştirmesi `data_domain` olmadan test ile reddedilir.
* External-data contract'larında production-eligibility alanı **yoktur** (test).
