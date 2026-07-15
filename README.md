# Adaptive Swim Pacing Platform

Yüzücünün hedef temposunu suyun içinde **görünür** kılan, koçun planını bozmadan uygulayan
offline-first pacing platformu. Çekirdek ürün bir ışık şeridi değil, bir **pacing beynidir**:
workout DSL → pace matematiği → ghost clock → deterministik güvenlik kontrolcüsü → analitik.

**Şu an neredeyiz:** Faz 1 — *Headless Core Vertical Slice*.
UI yok, cloud yok, gerçek ML yok, wearable yok, gerçek LED yok. Her şey programatik, deterministik
ve ağ erişimi olmadan koşar.

## 60 saniyede sanal seans (Faz 1 tamamlandığında)

```bash
make setup
make ci
python -m swimtools.run_scenario --workout 10x100_even --scenario long_stop --seed 42
#   -> out/events/<sessionId>.jsonl   (append-only event log)
#   -> out/reports/<sessionId>.md     (aktif performans + antrenman verimi + stop ozeti)
python -m swimtools.replay_check out/events/<sessionId>.jsonl   # bit-identical replay
```

### Windows / WSL kurulum notu
`Makefile` POSIX kabuk komutlari kullanir. Windows'ta **WSL2** (Ubuntu) onerilir; `make setup && make
ci` orada dogrudan calisir. WSL kullanmadan calismak isteyenler icin `make` hedeflerinin karsiligi:
`python -m venv .venv`, `pip install -e ".[dev]"`, `ruff check src tests`, `mypy`,
`lint-imports --config .importlinter`, `pytest`. (Ayri bir `scripts/setup.ps1` gerekiyorsa Commit
2'de eklenebilir; Faz 1 CI Linux'ta kosar.)

## Repository haritasi

| Paket | Gorev | I/O? |
|---|---|---|
| `src/contracts` | Tum veri sozlesmeleri, enum'lar, event zarfi, JSON Schema'nin tek kaynagi | Hayir |
| `src/swimcore` | **Saf domain**: validator, pace math, ghost + incident, session state, safety controller, analitik | **Hayir** |
| `src/persistence` | Append-only JSONL log + deterministik replay | Evet (yerel dosya) |
| `src/simulator` | Sanal yuzucu + senaryolar; **gercek `swimcore`'u embedded calistirir** | Dolayli |
| `src/swimtools` | Gelistirici/CI CLI'lari (sema uretimi, senaryo kosumu, replay dogrulama) | Evet |

Bagimlilik yonu tek: `swimtools -> simulator -> persistence -> swimcore -> contracts`.
`swimcore` hicbir seye bagimli degildir ve I/O yapmaz. import-linter bunu CI'da zorlar.

## Durma modeli — Stop Pause and Ghost Alignment (ADR-031)

Uc durum asla karismaz: (A) normal/buyuk tempo kaybi -> ghost ilerler, performansa dahil;
(B) koc pacing reseti -> gecmis performans raporda kalir, referans sonraki duvarda tazelenir;
(C) LongStop/Incident/Coach Stop -> StopPause: mantiksal saatler birlikte durur, ghost yuzucuye
kontrollu hizalanip bekler, resmi muhasebe sonraki duvarda reconcile edilir; stop suresi pace
hesabindan cikar ama raporda gorunur. Core durmanin nedenine karar vermez.

## Belgeler
* `ARCHITECTURE.md` — yasayan mimari ozeti
* `CLAUDE.md` — **kodlama sozlesmesi** (baglayici)
* `docs/adr/` — ADR-031 (incident pause), ADR-032 (external data), ADR-033 (deterministic id & time)
* `docs/domain/`, `docs/data/`, `docs/testing/`, `docs/plan/`

## Lisans
`LICENSE-NOTES.md` — *Proprietary, All Rights Reserved* (hukuki inceleme sonrasi revize edilebilir).
