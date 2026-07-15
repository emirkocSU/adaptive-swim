# ADR-033 — Deterministic Identity and Time

**Statü:** ACTIVE
**Faz:** 1
**Tarih:** 2026-07-14

## Context
Simulator ve gerçek runtime aynı `swimcore`'u çalıştırır ve golden replay bit-identical event log
üretmelidir. Ancak event'ler rastgele kimlik (ör. ULID/uuid) ve gerçek duvar saati kullanırsa aynı
seed ile bile birebir aynı log **üretilemez**.

## Problem
Determinizmi bozan iki kaynak: (1) kimlik üretimi (her çağrı farklı id), (2) zaman kaynağı (duvar
saati). Ayrıca kimlik biçimi (ULID) fazladan bir bağımlılık gerektirir; sıralama için zaten session
içi bir mekanizma vardır.

## Considered options
**Kimlik.** (a) ULID kütüphanesi eklemek — sıralanabilir id ama ek bağımlılık. (b) `uuid4` + session
içi monotonik `seq` — id opak ama sıralamayı `seq` verir, ek bağımlılık yok.
**Zaman.** (a) `swimcore` içinde `time.time()`/`datetime.now()` — determinizmi bozar. (b) Enjekte
edilen `Clock` — üretimde monotonic, testte SimClock.

## Decision

**Zaman ve kimlik `swimcore`'a enjekte edilir; asla global kaynaktan alınmaz.**

```python
# swimcore/ports.py  (Protocol'ler; swimcore saf kalır)
class Clock(Protocol):
    def now_ms(self) -> int: ...

class EventIdGenerator(Protocol):
    def next_id(self) -> str: ...
```

* Üretim: `SystemMonotonicClock` (persistence/adapter katmanında), `Uuid4EventIdGenerator`.
* Test/simulator: `SimClock` (deterministik, hızlandırılabilir), `DeterministicEventIdGenerator`
  (ör. `f"{prefix}-{counter:08d}"`).
* Bunlar session çekirdeğine **constructor ile** verilir.
* **ULID kullanılmaz.** Kimlik = `uuid4` (opak, çarpışmasız), **sıralama = session içi monotonik
  `seq`** (event zarfındaki alan). Ek bağımlılık yok.
* `swimcore` içinde `time`, `datetime`, `uuid`, `random`, `secrets` import etmek **yasaktır**;
  `tests/architecture/test_no_io_in_swimcore.py` AST ile yakalar.

## Consequences
Aynı seed + aynı deterministik id üreteci + SimClock → bit-identical event log ve rapor. Üretimde
kimlikler opak `uuid4`, ama replay ve sıralama `seq`'e dayandığı için determinizm korunur (id'lerin
kendisi log'da sabittir çünkü log yeniden üretilmez, replay edilir).

## Reversibility
KOLAY. Port'lar arkasında; farklı bir id/clock implementasyonu takılabilir. ULID'e geçmek istenirse
yalnızca üretim `EventIdGenerator`'ı değişir (sözleşme aynı).

## Validation
* `test_no_io_in_swimcore.py`: `swimcore` içinde yasaklı import yok (AST).
* Golden replay: aynı seed → bit-identical log (deterministik id + SimClock).
* Property: `seq` session içinde kesintisiz monotonik artar.
