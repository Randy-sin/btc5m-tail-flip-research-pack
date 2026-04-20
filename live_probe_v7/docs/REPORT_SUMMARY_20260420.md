# Proactive 1c GTC Run Summary — 2026-04-20

## Decision

The article-faithful proactive 1c GTC path is **not invalidated**. The previous late-maker replay tested the wrong timing.

However, this is not yet live proof. The next step is a $1 probe to verify real queue position and User Channel fills.

## Historical replay results

| Experiment | Signals | Fills | Wins | Fill rate | Win rate after fill | ROI on risk |
|---|---:|---:|---:|---:|---:|---:|
| 5s, $1 unit, BBO queue | 411 | 129 | 10 | 31.39% | 7.75% | +407.49% |
| 5s, queue +100 shares | 411 | 74 | 4 | 18.00% | 5.41% | +396.78% |
| 5s, queue +500 shares | 411 | 28 | 1 | 6.81% | 3.57% | +295.59% |
| 5s, queue +1000 shares | 411 | 17 | 0 | 4.14% | 0.00% | -100.00% |
| 1s, $1 unit, BBO queue | 460 | 142 | 10 | 30.87% | 7.04% | +366.12% |
| 1s, queue +500 shares | 460 | 33 | 1 | 7.17% | 3.03% | +236.49% |

## Interpretation

The edge is execution-sensitive. If real 1c queue depth behaves like BBO/+100/+500, the strategy deserves small-money validation. If real queue depth behaves like +1000, the current 1c GTC version fails.

## Immediate blocker

Historical replay fills are simulated. We need actual live placement + actual User Channel fills, at tiny size, before any scaling.
