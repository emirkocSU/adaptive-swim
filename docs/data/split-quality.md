# Split Quality (five classes)

Manual splits are not ground truth. Quality is a measurement axis only; it is separate
from StopPause exclusion.

| qualityFlag | Meaning | Live pacing | ML training | Research primary |
|---|---|---|---|---|
| VERIFIED_HIGH | Independently verified (touchpad, video frame, dual-timer agreement) | yes | yes | yes |
| RELIABLE | Automatic reliable source (touchpad/timing; wearable if calibrated) | yes | yes | yes (with sensitivity) |
| MANUAL_UNVERIFIED | Coach-tap / button, unverified | yes | no (default) | no (secondary only) |
| ESTIMATED | System estimate (interpolation, late-split normalization) | yes (low confidence) | no | no |
| INVALID | Duplicate remnant, out-of-order, sanity violation | ignored | no | no |

`SIMULATED` source is always labelled separately and used only for engineering/leakage
testing.

**A StopPause never turns a split INVALID.** StopPause exclusion is carried on the length
outcome via `AnalyticsExclusionReason`, not on `Split.qualityFlag`.
