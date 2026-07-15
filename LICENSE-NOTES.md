# Lisans Notlari

## Mevcut durum

**Proprietary — All Rights Reserved.**

Bu repository'deki tum kaynak kod, tasarim belgeleri, semalar ve mimari kararlar telif hakkiyla
korunmaktadir. Yazili izin olmadan kopyalanamaz, dagitilamaz, turev calisma uretilemez veya ticari
olarak kullanilamaz.

## Bu bir placeholder'dir

Yukaridaki ifade **baslangic konumudur** ve hukuki danismanlik sonrasinda degistirilebilir.
Kararlastirilmasi gerekenler: core pacing engine (`swimcore`) IP'sinin kurucuda kalmasi ile
partner/OEM lisanslama ayrimi; akademik yayin haklari; anonimlestirilmis veri uzerinde model
gelistirme hakkinin sozlesmede korunmasi; olasi acik kaynak bilesenlerin ayri lisansi.

**Bu dosya hukuki gorus degildir.** Uzman incelemesi gereklidir.

## Ucuncu taraf bagimliliklari
Faz 1 runtime bagimliligi: `pydantic`. Gelistirme: pytest, hypothesis, ruff, mypy, import-linter,
pytest-socket. Yeni runtime bagimliligi ADR gerektirir.

## Dis veri kaynaklari
Hicbir dis veri kaynagi icin erisim/indirme/ticari kullanim/yeniden dagitim hakki **varsayilmaz**.
Her kaynak `DataSourceRegistryEntry` ile kayitlanir; belirsiz durumlar `TBD_VERIFICATION_REQUIRED`.
Ayrinti: `docs/adr/ADR-032-external-data-bootstrapping.md`.
