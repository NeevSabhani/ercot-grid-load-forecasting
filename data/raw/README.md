# Raw data

These files are not committed — they are large and freely available from the sources below.
Download them into this directory using the layout shown, then run:

```bash
python scripts/build_dataset.py
```

## Expected layout

```
data/raw/
├── load_2022/Native_Load_2022.xlsx
├── load_2023/Native_Load_2023.xlsx
├── load_2024/Native_Load_2024.xlsx
├── load_2025/Native_Load_2025.xlsx
├── fuelmix/
│   ├── IntGenbyFuel2022.xlsx
│   ├── IntGenbyFuel2023.xlsx
│   ├── IntGenbyFuel2024.xlsx
│   └── IntGenbyFuel2025.xlsx
└── weather_USW00013904.csv
```

## Where to get them

**ERCOT hourly load** — https://www.ercot.com/gridinfo/load/load_hist
Download "Native Load YYYY" for each year and unzip into `load_YYYY/`.
Hourly system load by weather zone, MW. Timestamps are *hour ending*, so `24:00` is the last
hour of the labelled date. The autumn DST repeat hour carries a ` DST` suffix; that day has 25
hourly rows and the spring transition day has 23. Both are correct.

**ERCOT fuel mix** — https://www.ercot.com/gridinfo/generation
"Fuel Mix Report" — the current year as a single file, prior years bundled in
`FuelMixReport_PreviousYears.zip`. One sheet per month.

> **The trap:** each row has 96 fifteen-minute MWh columns *and* a `Total` column that is already
> their sum. `Total` is daily energy in MWh — do not divide it by 4, and do not sum the interval
> columns expecting a different answer. `build_dataset.py` validates the two against each other
> and permits exactly one exception per year: the 25-hour autumn DST day, where the sheet's 96
> named columns cannot hold the repeated hour and `Total` is the authoritative figure.

**NOAA weather** — https://www.ncei.noaa.gov/cdo-web/
Daily Summaries for station `USW00013904` (Austin-Bergstrom Intl. Airport), 2022–2025, as CSV.

> **The trap:** GHCN ships integer tenths. `TMAX`/`TMIN` are tenths of °C, `PRCP` is tenths of mm,
> `AWND` is tenths of m/s. `TAVG` is not reported for this station over this window, so the daily
> mean is taken as `(TMAX + TMIN) / 2` — the standard degree-day convention.
