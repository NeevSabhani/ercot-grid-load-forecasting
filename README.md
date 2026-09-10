# Day-Ahead Peak Load Forecasting for the ERCOT Grid

**How well can you predict tomorrow's peak electricity demand in Texas — and what does being wrong
actually cost?**

**[→ Read the notebook](notebooks/ERCOT_Grid_Load_Forecasting.ipynb)** — it renders on GitHub with
every figure and output already in place.

---

## Why Texas is a special case

Most of the US runs on two enormous interconnected grids. If Ohio comes up short on a hot August
afternoon, power flows in from Michigan and nobody outside a control room finds out.

Texas opted out. ERCOT serves about 90% of the state and connects to its neighbors through a
handful of small DC ties whose combined capacity barely registers against a 60 GW load. For
practical purposes it's an electrical island: whatever Texas consumes in a second, Texas generates
in that same second.

That's what turns load forecasting into a reliability function rather than a reporting exercise. A
large gas plant needs hours of notice, so operators decide *the day before* how much capacity to
start. Guess low and you're buying in real time during a scarcity event, where ERCOT's offer cap
has sat at **$5,000/MWh since January 1, 2022**. Guess high and consumers pay for generators that
spun up for nothing.

Both mistakes cost money. They don't cost the *same* money — and that asymmetry drives the most
interesting result in the project.

## Results

Walk-forward cross-validation, 9 expanding-window folds, **810 held-out forecast days** across
2023–2025.

| | |
|---|---|
| Best model (stacked ensemble) | **2,082 MW MAE** — 3.33% MAPE |
| Peak-season MAE (Jun–Sep) | 2,380 MW |
| Persistence baseline | 2,761 MW |
| **Skill vs. persistence** | **24.6% MAE reduction** |
| Fold-to-fold SD of the leader's MAE | 396 MW |
| Prediction interval coverage (90% target) | **90.1%**, via rolling cross-conformal |

Five models compared — Ridge, SARIMAX, XGBoost, LSTM, and a stacked ensemble — against four
baselines including persistence, seasonal naive, and a weather+calendar regression.

## What came out of it

**The 65 °F degree-day convention is wrong for ERCOT.** That number comes from mid-twentieth-century
building stock and gets used mostly because everyone else uses it. Fitting the balance point from
the data puts it at **62.0 °F**. Above it, cooling costs 1,317 MW/°F; below it, heating costs
714 MW/°F. A cooling-dominated grid, where summer degrees carry the reliability risk.

**"Which model wins" often isn't a well-posed question.** The gap between the top two models is
66 MW. The fold-to-fold variation is 396 MW. Diebold–Mariano tests with Holm correction found
**4 of 15 model pairs statistically indistinguishable**. More usefully: the model with the best
annual MAE and the model with the best *peak-season* MAE are different models — so selecting on the
annual number picks the wrong one for the days that actually set reserve margins.

**Models under-forecast the hardest days.** In the top load decile the bias runs −2,084 MW. That's
the expensive direction, and it's exactly where tree models hit their extrapolation limit on a
growing system.

**Accuracy and value are different objectives.** With a 9:1 shortfall-to-excess cost ratio, the
cost-optimal forecast is the 90th percentile rather than the mean. Shifting the forecast up by
**+3,100 MW** cuts expected cost **56%** — with no improvement in MAE whatsoever. The empirical
optimum lands within 40 MW of the theoretical quantile.

**Perfect weather was doing real work.** Inject realistic day-ahead temperature error (σ = 2 °F)
and MAE rises about 11%. Any load-forecasting result quoted without stating its weather assumption
is quoting the σ=0 number.

**Solar shows up when the grid needs it. Wind mostly doesn't.** On the top 5% of load days, solar
runs at **1.55×** its average output while wind runs at 0.98×. The conditions that drive extreme
Texas load — hot, clear, still — are the same ones that produce strong solar and weak wind.

## How it's put together

Each modeling decision is earned by a diagnostic that comes before it.

| § | |
|---|---|
| 1–2 | **Data integrity audit** — calendar continuity, physical plausibility screens, leakage detection |
| 3 | **The physics** — balance-point estimation, thermal mass, calendar structure, STL, ACF/PACF, weather-normalized growth |
| 4 | **Feature engineering under a knowability rule**, with an automated leakage assertion |
| 5–6 | Operationally meaningful metrics, four baselines, expanding-window walk-forward CV |
| 7 | Five models, each explained by the structure it can and can't represent |
| 8 | Fold-level results, **Diebold–Mariano** significance testing, error diagnostics by regime |
| 9 | Sensitivity to **weather-forecast error** |
| 10 | **Conformal prediction intervals**, three variants, coverage measured rather than assumed |
| 11 | **Asymmetric reserve economics** and the cost-optimal forecast quantile |
| 12 | SHAP, partial dependence, and a sensitivity ladder |
| 13 | Renewables, net load duration curves, solar's alignment with peak |
| 14–15 | Limitations, then conclusions |

### Three things most load-forecasting write-ups skip

**It audits the input file instead of trusting it.** Physical-plausibility screens check implied
capacity factors and load factors against known bounds. This caught a real defect: an earlier
version of the pipeline undercounted the ERCOT fuel mix by roughly 4×, reporting renewable share at
8–10% when the true figure is 31–38%. Nothing crashed and no chart looked wrong — the shape was
right and only the level was off, which is precisely why a plot can't catch this class of bug.

**It enforces its own leakage rule in code.** §4.4 rebuilds the feature matrix on truncated history
and asserts nothing changed. It caught a leak introduced *while the notebook was being written* — a
full-sample quantile used as a heat-wave threshold. Full-sample statistics used to define a feature
don't look like lags. They look like preprocessing. They leak just the same.

**It measures its own optimism.** Replacing same-day renewable generation (unknowable at forecast
time) with lagged values costs 361 MW of MAE — 16.4%. That gap gets quantified rather than quietly
avoided.

## Data

All public. Raw files are gitignored; `scripts/build_dataset.py` rebuilds the processed dataset
from them.

| Source | What it gives | Years |
|---|---|---|
| [ERCOT Hourly Load Data Archive](https://www.ercot.com/gridinfo/load/load_hist) | Hourly system load by weather zone | 2022–2025 |
| [ERCOT Fuel Mix Report](https://www.ercot.com/gridinfo/generation) | 15-minute generation by fuel type | 2022–2025 |
| [NOAA GHCN-Daily](https://www.ncei.noaa.gov/cdo-web/) `USW00013904` | Austin-Bergstrom Intl. — daily temperature, precipitation, wind | 2022–2025 |

Units are where this data bites. The `IntGenbyFuel` sheets carry 96 fifteen-minute MWh columns
*and* a `Total` column that's already their daily sum — mix them up and you're off by a factor of
four. GHCN ships integer tenths (tenths of °C, tenths of mm, tenths of m/s). `build_dataset.py`
writes every conversion out explicitly and validates `Total` against the interval columns, allowing
the one legitimate exception per year: the 25-hour autumn DST day, where 96 named columns can't
hold the repeated hour.

## Running it

```bash
pip install -r requirements.txt

# Put raw files under data/raw/ as described in data/raw/README.md, then:
python scripts/build_dataset.py          # -> data/processed/daily_dataset.csv

jupyter lab notebooks/ERCOT_Grid_Load_Forecasting.ipynb
```

About 10 minutes end to end on CPU. The LSTM (3 seeds × 9 folds with early stopping) is roughly 6
of that; set `RUN_CV = False` in §7.6 to skip the cross-validation loop.

## Limitations

Spelled out at greater length in §14 of the notebook:

- **One weather station** for an eight-zone grid. A load-weighted multi-zone temperature is the
  highest-value data upgrade available.
- **Daily resolution** hides the intra-day problems that matter most — the evening net-load ramp,
  the migrating peak hour, the duck curve. The source ERCOT files are already hourly, so this is a
  rebuild rather than new data.
- **2022–2025 excludes Winter Storm Uri.** Nothing here characterizes extreme winter tail risk, and
  the conformal intervals would be badly miscalibrated for such an event.
- **Cost parameters in §11 are assumptions.** Only the $5,000/MWh offer cap is externally
  documented; the conclusion comes from a sensitivity sweep across cost ratios rather than a point
  estimate.
- **Conditional coverage is the open problem.** The intervals hit 90.1% marginal coverage but only
  72.2% on the highest-load quintile — under-protected on exactly the days that matter.

## What I'd do next

1. Rebuild at hourly resolution with load-weighted multi-zone temperature.
2. Train directly on the pinball loss at the cost-optimal quantile instead of shifting post hoc.
3. Extend the record to 2015 to fit an extreme-value model for winter tail risk.
4. Add humidity — AC load responds to latent as well as sensible heat.
5. Swap the trend feature for ERCOT interconnection-queue data, which a tree model can use where it
   can't extrapolate a time index.

## Layout

```
├── notebooks/
│   └── ERCOT_Grid_Load_Forecasting.ipynb   # the analysis, outputs included
├── scripts/
│   └── build_dataset.py                    # raw sources -> processed daily dataset
├── data/
│   ├── raw/                                # gitignored; see data/raw/README.md
│   └── processed/
│       └── daily_dataset.csv               # 1,461 days x 26 columns
├── requirements.txt
└── README.md
```
