# Faz 1 Degismezleri

Her degismez en az bir test kimligine baglanir. Commit 10'da eksiksizlik kontrol edilir.

| # | Degismez | Test kimligi (planlanan) |
|---|---|---|
| 1 | Normal/buyuk tempo kaybi (Durum A) StopPause tetiklemez; ghost + saat ilerler | unit/test_stop_pause::test_tempo_loss_does_not_pause |
| 2 | StopPause (Durum C) ghost + workout + pace + rest saatlerini BIRLIKTE durdurur | unit/test_stop_pause::test_stoppause_freezes_all_logical_clocks |
| 3 | StopPause session state'ini degistirmez (RUNNING kalir) | unit/test_session_state_machine::test_stoppause_keeps_running |
| 4 | stoppedDurationSec durmanin BASLADIGI ana geri donuktur (esik anina degil) | unit/test_stop_pause::test_stopped_duration_retroactive |
| 5 | Kontrollu havuz-ortasi hizalama yalnizca dogrulanmis StopPause'da; kontrolsuz teleport yasak | unit/test_stop_pause::test_controlled_alignment_only_in_stoppause |
| 6 | Resume ayni noktadan, ayni hedef tempoyla; workout clock kaldigi saniyeden | unit/test_stop_pause::test_resume_same_point_same_pace |
| 7 | Resmi muhasebe havuz ortasinda yeniden yazilmaz; sonraki duvarda reconcile | unit/test_stop_pause::test_reconcile_at_next_wall |
| 8 | Planli dinlenme StopPause'dan dusulmez; dinlenme sirasinda StopPause olursa sayac da durur | unit/test_stop_pause::test_rest_countdown_isolated |
| 9 | Duplicate MarkStopPause ikinci pause acmaz | property/test_stoppause_idempotency::test_duplicate_markstop |
| 10 | Duplicate ResolveStopPause ikinci saat dusumu uretmez | property/test_stoppause_idempotency::test_duplicate_resolve |
| 11 | Guvenilir stop -> length atilmaz; active/stopped ayri, pace'ten stop cikar | unit/test_analytics_exclusions::test_reliable_stop_keeps_length |
| 12 | Guvenilmez stop/time -> length analiz disi (STOP_TIME_UNRELIABLE) | unit/test_analytics_exclusions::test_unreliable_stop_excludes_length |
| 13 | StopPause, split quality'yi otomatik INVALID yapmaz | unit/test_analytics_exclusions::test_stop_does_not_invalidate_split |
| 14 | StopPause interval ML-label eligible degildir (guvenilir olsa bile) | unit/test_analytics_exclusions::test_stop_not_ml_eligible |
| 15 | Koc pacing reseti (Durum B) saati durdurmaz; gecmis gap raporda kalir | unit/test_stop_pause::test_coach_reset_keeps_clock_and_history |
| 16 | Uc sure alani tutarli: elapsed == active + stopped | unit/test_stop_pause::test_duration_accounting_consistent |
| 17 | Replay ayni StopPause + resume + stopped sonucunu bit-identical uretir | replay/test_golden_replay::test_stoppause_chain_bit_identical |
| 18 | Synthetic kayitlar her zaman source + scenario provenance tasir | simulator/test_scenarios::test_provenance_stamped |
| 19 | Race/training/Adaptive Swim kayitlari data_domain olmadan birlesemez | unit/test_external_data_contracts::test_merge_requires_data_domain |
| 20 | SafetyController hicbir girdide pace bounds disina cikamaz; simulator ikinci pacing impl. icermez | property/test_controller_bounds + architecture/test_import_rules |
