from __future__ import annotations

from hypothesis import settings

# Property testleri CI'da deterministik kosar (derandomize): ayni commit, ayni sonuc.
settings.register_profile("ci", max_examples=200, derandomize=True, deadline=None)
settings.register_profile("dev", max_examples=50, deadline=None)
settings.load_profile("dev")
