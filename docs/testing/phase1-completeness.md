# Faz 1 Eksiksizlik Kontrolu (phase1-completeness-check)

`make ci` icinde eksik test suite'leri Commit 1-9 boyunca PENDING olarak raporlanabilir. Ancak
**Commit 10'da hicbir PENDING kalmamalidir.** Bu, `swimtools/completeness_check.py` (Commit 10'da
eklenir) ile mekanik olarak dogrulanir ve `make ci`'a `phase1-completeness` hedefi olarak baglanir.

## Kontrol kurallari (Commit 10)
1. Su dizinlerin tumu var ve en az bir test icerir: `tests/unit`, `tests/property`, `tests/replay`,
   `tests/simulator`, `tests/architecture`, `tests/e2e`.
2. `swimtools/gen_schemas.py` var ve `make schema-check` PENDING donmez (gercek dogrulama yapar).
3. `docs/testing/invariants.md`'deki 20 degismezin her birinin test kimligi gercek bir teste cozulur
   (kimlik -> dosya::fonksiyon eslemesi bos donmez).
4. Makefile'daki hicbir hedef "PENDING:" satiri basmaz.

## Neden Commit 10
Erken commitlerde PENDING kabul edilebilir (her commit yesil kalir). Commit 10 bu gecici durumu
kapatir; boylece "yesil CI" Faz 1 sonunda gercekten eksiksiz demektir.
