# Day-Ahead Peak Load Forecasting for the ERCOT Grid

Forecasting tomorrow's peak electricity demand on the Texas grid — and asking what a forecast
error is actually worth.

**[→ Read the notebook](notebooks/ERCOT_Grid_Load_Forecasting.ipynb)** (renders on GitHub with all
figures and outputs)

---

## The problem

ERCOT runs an electric grid for ~27 million people with only small DC ties to its neighbors. It
cannot import its way out of a shortfall, so whatever Texas consumes in a second, Texas must
generate in that second. Operators commit generation *the day before*, because large thermal units
need hours of notice.

That makes the day-ahead load forecast a reliability function with asymmetric stakes: commit too
little and you buy energy in real time at prices capped at **$5,000/MWh** (the ERCOT system-wide
offer cap since January 1, 2022); commit too much and consumers pay for idle capacity.

**Question:** given everything knowable by mid-afternoon today, how accurately can tomorrow's ERCOT
peak be predicted — and how much of the remaining error is irreducible?

## Headline results

Walk-forward cross-validation, 9 expanding-window folds, **810 held-out forecast days** (2023–2025).

| | |
|---|---|
| Best model (stacked ensemble) | **2,082 MW MAE** — 3.33% MAPE |
| Peak-season MAE (Jun–Sep) | 2,380 MW |
| Persistence baseline | 2,761 MW |
| **Skill vs. persistence** | **24.6% MAE reduction** |
| Fold-to-fold SD of leader's MAE | 396 MW |
| Prediction interval coverage (90% target) | **90.1%** via rolling cross-conformal |

Five models compared — Ridge, SARIMAX, XGBoost, LSTM, and a stacked ensemble — against four
baselines including persistence, seasonal naive, and a weather+calendar regression.

## What the analysis found

**The 65 °F degree-day convention is wrong for ERCOT.** Fitting the balance point from the data
puts it at **62.0 °F**. Cooling costs **1,317 MW/°F** above it; heating **714 MW/°F** below —
a cooling-dominated grid where summer degrees carry the reliability risk.

**"Which model wins" is often not a well-posed question.** The gap between the top two models
(66 MW) is smaller than the fold-to-fold variation (396 MW). Diebold–Mariano tests with
Holm correction found **4 of 15 model pairs statistically indistinguishable**. The overall winner
and the *peak-season* winner are different models — selecting on annual MAE picks the wrong one
for the days that set reserve margins.

**Models systematically under-forecast the highest-load days** by 2,084 MW in the top decile —
the expensive direction, and exactly where tree models cannot extrapolate a growing trend.

**Accuracy is not value.** With an assumed 9:1 shortfall-to-excess cost ratio, the cost-optimal
forecast is the 90th percentile, not the mean. Shifting the forecast up by **+3,100 MW** cuts
expected cost **56%** — with *no* improvement in MAE. The empirical optimum lands within 40 MW of
the theoretical quantile.

**Perfect weather is doing real work.** Injecting realistic day-ahead temperature forecast error
(σ = 2 °F) raises MAE ~11%. Any load-forecasting result quoted without stating its weather
assumption is quoting the σ=0 number.

**Solar shows up when the grid needs it; wind does not.** On the top 5% of load days, solar runs at
**1.55×** its average output while wind runs at 0.98×. The conditions that drive extreme Texas load
— hot, clear, still — are the same ones that produce strong solar and weak wind.

## Method

Each modeling decision is earned by a diagnostic that precedes it.

| § | |
|---|---|
| 1–2 | **Data integrity audit** — calendar continuity, physical plausibility screens, target-leakage detection |
| 3 | **The physics** — balance-point estimation, thermal mass, calendar structure, STL, ACF/PACF, weather-normalized growth |
| 4 | **Feature engineering under a knowability rule**, with an automated leakage assertion |
| 5–6 | Operationally meaningful metrics, four baselines, expanding-window walk-forward CV |
| 7 | Five models, each explained in terms of the structure it can and cannot represent |
| 8 | Results across folds + **Diebold–Mariano** significance testing + error diagnostics by regime |
| 9 | Sensitivity to **weather-forecast error** |
| 10 | **Conformal prediction intervals** with measured coverage (three variants) |
| 11 | **Asymmetric reserve economics** and the cost-optimal forecast quantile |
| 12 | SHAP attribution, partial dependence, and a sensitivity ladder |
| 13 | Renewables, net load duration curves, and solar's alignment with peak |
| 14–15 | Limitations and conclusions |

### Three things this project does that most load-forecasting write-ups skip

1. **It audits the input file before trusting it.** Physical-plausibility screens compare implied
   capacity factors and load factors against known bounds. This caught a real defect: an earlier
   version of the pipeline undercounted the ERCOT fuel mix by ~4×, reporting renewable share at
   8–10% when the true figure is 31–38%.

2. **It enforces its own leakage rule in code.** §4.4 rebuilds the feature matrix on truncated
   history and asserts nothing changed. It caught a leak introduced *while writing the notebook* —
   a full-sample quantile used as a heat-wave threshold. Full-sample statistics used to define a
   feature are the most common way leakage enters a careful pipeline, because they don't look like
   lags.

3. **It measures its own optimism.** Replacing same-day renewable generation (unknowable at
   forecast time) with lagged values costs 361 MW of MAE — 16.4%. That gap is quantified rather
   than quietly avoided.

## Data

All sources public. Raw files are gitignored; `scripts/build_dataset.py` rebuilds the processed
dataset from them.

| Source | Contents | Coverage |
|---|---|---|
| [ERCOT Hourly Load Data Archive](https://www.ercot.com/gridinfo/load/load_hist) | Hourly system load by weather zone | 2022–2025 |
| [ERCOT Fuel Mix Report](https://www.ercot.com/gridinfo/generation) | 15-minute generation by fuel type | 2022–2025 |
| [NOAA GHCN-Daily](https://www.ncei.noaa.gov/cdo-web/) `USW00013904` | Austin-Bergstrom Intl. — daily temperature, precipitation, wind | 2022–2025 |

**Unit discipline matters here.** The `IntGenbyFuel` sheets carry 96 fifteen-minute MWh columns
*and* a `Total` column that is already their daily sum; mixing them up costs a factor of four.
GHCN ships integer tenths (tenths of °C, tenths of mm, tenths of m/s). `build_dataset.py` writes
every conversion out explicitly and validates `Total` against the interval columns, allowing the
one legitimate exception per year — the 25-hour autumn DST day.

## Running it

```bash
pip install -r requirements.txt

# Place raw files under data/raw/ as described in data/raw/README.md, then:
python scripts/build_dataset.py          # -> data/processed/daily_dataset.csv

jupyter lab notebooks/ERCOT_Grid_Load_Forecasting.ipynb
```

Full notebook runtime is roughly 10 minutes on CPU; the LSTM (3 seeds × 9 folds with early
stopping) is about 6 of that. Set `RUN_CV = False` in §7.6 to skip the cross-validation loop.

## Limitations

Stated plainly, and at greater length in §14 of the notebook:

- **One weather station** for an eight-zone grid. A load-weighted multi-zone temperature is the
  highest-value data upgrade available.
- **Daily resolution** hides the intra-day problems that matter most — the evening net-load ramp,
  the migrating peak hour, the duck curve. The source ERCOT files are already hourly.
- **2022–2025 excludes Winter Storm Uri.** Nothing here characterizes extreme winter tail risk,
  and the conformal intervals would be badly miscalibrated for such an event.
- **Cost parameters in §11 are illustrative.** Only the $5,000/MWh offer cap is externally
  documented; conclusions are drawn from a sensitivity sweep across cost ratios, not a point
  estimate.
- **Conditional coverage is the open problem.** The intervals achieve 90.1% marginal coverage but
  only 72.2% on the highest-load quintile.

## Next steps

1. Rebuild at hourly resolution with load-weighted multi-zone temperature.
2. Train directly on the pinball loss at the cost-optimal quantile rather than shifting post hoc.
3. Extend the record to 2015 to fit an extreme-value model for winter tail risk.
4. Add humidity (heat index / wet-bulb) — AC load responds to latent as well as sensible heat.
5. Replace the trend feature with ERCOT interconnection-queue data, which a tree model can use
   where it cannot extrapolate a time index.

## Repository layout

```
├── notebooks/
│   └── ERCOT_Grid_Load_Forecasting.ipynb   # the analysis, with outputs
├── scripts/
│   └── build_dataset.py                    # raw sources -> processed daily dataset
├── data/
│   ├── raw/                                # gitignored; see data/raw/README.md
│   └── processed/
│       └── daily_dataset.csv               # 1,461 days x 26 columns
├── requirements.txt
└── README.md
```
