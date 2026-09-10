"""
Build data/processed/daily_dataset.csv from the public raw sources.

Sources
-------
1. ERCOT Native Load archive        data/raw/load_YYYY/Native_Load_YYYY.xlsx
      Hourly system load by weather zone, MW. Column 'ERCOT' is the system total.
      Timestamps are labelled "MM/DD/YYYY HH:00" as HOUR ENDING, so hour 24:00 is
      the last hour of the labelled date. The autumn DST repeat hour carries a
      " DST" suffix; that day legitimately has 25 hourly rows and the spring
      transition day has 23.

2. ERCOT Fuel Mix Report            data/raw/fuelmix/IntGenbyFuelYYYY.xlsx
      One sheet per month. Each row is (Date, Fuel, Settlement Type) with 96
      fifteen-minute columns in MWh plus a 'Total' column that equals their sum,
      i.e. Total is already daily energy in MWh. No division by 4 is required —
      and applying one is the classic way this file gets misread.

3. NOAA GHCN-Daily                  data/raw/weather_USW00013904.csv
      Austin-Bergstrom Intl. GHCN ships INTEGER TENTHS:
         TMAX, TMIN  tenths of degrees C
         PRCP        tenths of mm
         AWND        tenths of m/s
      TAVG is not reported for this station over the study window, so the daily
      mean is taken as (TMAX + TMIN) / 2, the standard degree-day convention.

Units discipline
----------------
Every conversion below is written out explicitly, because silent unit errors in
energy data are invisible in a time-series plot: the shape stays right and only
the level is wrong. The notebook's Section 2 re-derives these quantities
independently and screens them against physical bounds.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
import holidays as pyholidays

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed" / "daily_dataset.csv"

YEARS = [2022, 2023, 2024, 2025]
DEGREE_DAY_BASE_F = 65.0          # conventional base; the notebook re-estimates it
RENEWABLE_FUELS = ["Wind", "Solar"]
STORAGE_FUELS = ["WSL"]           # storage load: negative when charging


# ─────────────────────────────── load ───────────────────────────────
def parse_hour_ending(label) -> pd.Timestamp:
    """'11/06/2022 02:00 DST' -> the calendar date it belongs to.

    We only need the DATE for daily aggregation, and hour-ending 01:00..24:00 all
    belong to the labelled date, so the date part is taken verbatim.

    Excel sometimes coerces a subset of these cells to real datetimes, so the
    column arrives with mixed types and both cases have to be handled.
    """
    if isinstance(label, (pd.Timestamp, np.datetime64)):
        return pd.Timestamp(label).normalize()
    text = str(label).replace(" DST", "").strip().split()[0]
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return pd.to_datetime(text, format=fmt)
        except ValueError:
            continue
    return pd.to_datetime(text)


def load_system_load() -> pd.DataFrame:
    frames = []
    for year in YEARS:
        path = RAW / f"load_{year}" / f"Native_Load_{year}.xlsx"
        df = pd.read_excel(path)
        col = "Hour Ending" if "Hour Ending" in df.columns else df.columns[0]
        df["date"] = df[col].map(parse_hour_ending)
        if "ERCOT" not in df.columns:
            raise KeyError(f"{path.name}: no 'ERCOT' system-total column")
        frames.append(df[["date", "ERCOT"]].rename(columns={"ERCOT": "load_mw"}))
        print(f"  load {year}: {len(df):,} hourly rows")

    hourly = pd.concat(frames, ignore_index=True)
    hourly["load_mw"] = pd.to_numeric(hourly["load_mw"], errors="coerce")

    daily = hourly.groupby("date").agg(
        peak_load_mw=("load_mw", "max"),
        mean_load_mw=("load_mw", "mean"),
        # Each row is one hour at a constant MW, so MW summed over hours == MWh.
        total_load_mwh=("load_mw", "sum"),
        n_hours=("load_mw", "size"),
    )
    odd = daily[daily["n_hours"] != 24]
    if len(odd):
        print(f"  {len(odd)} day(s) without 24 hours (expected: DST transitions)")
        for d, r in odd.iterrows():
            print(f"     {d.date()}  {int(r['n_hours'])} hours")
    return daily


# ───────────────────────────── fuel mix ─────────────────────────────
def load_fuel_mix() -> pd.DataFrame:
    MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    frames = []
    for year in YEARS:
        path = RAW / "fuelmix" / f"IntGenbyFuel{year}.xlsx"
        xl = pd.ExcelFile(path)
        sheets = [s for s in xl.sheet_names if s in MONTHS]
        got = 0
        for sheet in sheets:
            df = pd.read_excel(xl, sheet_name=sheet)
            if not {"Date", "Fuel", "Total"} <= set(df.columns):
                continue
            # 'Total' should equal the sum of the 96 fifteen-minute MWh columns.
            # Verify it rather than trusting it -- but expect ONE exception per
            # year: on the autumn DST day the grid runs 25 hours = 100 intervals,
            # and the sheet only has 96 named columns, so 'Total' is larger than
            # their sum by the repeated hour. 'Total' is the authoritative figure;
            # a mismatch on any OTHER day means the file cannot be trusted.
            interval_cols = [c for c in df.columns
                             if re.fullmatch(r"\d{1,2}:\d{2}", str(c))]
            if interval_cols:
                recomputed = df[interval_cols].sum(axis=1)
                gap = (df["Total"] - recomputed).abs()
                offenders = df.loc[gap > 1.0, "Date"]
                bad_dates = sorted(pd.to_datetime(offenders).dt.normalize().unique())
                unexpected = [d for d in bad_dates
                              if not (pd.Timestamp(d).month == 11
                                      and pd.Timestamp(d).dayofweek == 6
                                      and pd.Timestamp(d).day <= 7)]
                if unexpected:
                    raise ValueError(
                        f"{path.name}/{sheet}: 'Total' != sum of interval columns on "
                        f"{[str(pd.Timestamp(d).date()) for d in unexpected]}, which are "
                        f"not DST transitions. Do not trust this file blindly.")
                if bad_dates:
                    print(f"     {sheet}: DST 25-hour day "
                          f"{pd.Timestamp(bad_dates[0]).date()} — using 'Total' "
                          f"(+{gap.max():,.0f} MWh vs. the 96 named columns)")
            frames.append(df[["Date", "Fuel", "Total"]])
            got += 1
        print(f"  fuelmix {year}: {got} monthly sheets")

    fm = pd.concat(frames, ignore_index=True)
    fm["date"] = pd.to_datetime(fm["Date"]).dt.normalize()
    fm["Total"] = pd.to_numeric(fm["Total"], errors="coerce")

    wide = fm.pivot_table(index="date", columns="Fuel", values="Total",
                          aggfunc="sum").fillna(0.0)
    out = pd.DataFrame(index=wide.index)
    out["wind_mwh"] = wide.get("Wind", 0.0)
    out["solar_mwh"] = wide.get("Solar", 0.0)
    out["renewable_mwh"] = out["wind_mwh"] + out["solar_mwh"]
    # Total generation across every reported fuel, storage included (it is
    # negative while charging, which is the correct sign for a net-generation sum).
    out["total_gen_mwh"] = wide.sum(axis=1)
    print(f"  fuels present: {sorted(wide.columns)}")
    return out


# ────────────────────────────── weather ──────────────────────────────
def load_weather() -> pd.DataFrame:
    path = RAW / "weather_USW00013904.csv"
    w = pd.read_csv(path, low_memory=False, parse_dates=["DATE"])
    w = w.rename(columns={"DATE": "date"}).set_index("date").sort_index()
    w = w.loc[f"{min(YEARS)}-01-01":f"{max(YEARS)}-12-31"]

    def tenths(col):
        return pd.to_numeric(w[col], errors="coerce") / 10.0 if col in w.columns else np.nan

    tmax_c, tmin_c = tenths("TMAX"), tenths("TMIN")          # tenths degC -> degC
    out = pd.DataFrame(index=w.index)
    out["tmax_f"] = tmax_c * 9 / 5 + 32
    out["tmin_f"] = tmin_c * 9 / 5 + 32
    # GHCN reports no TAVG for this station in the study window; the (max+min)/2
    # midpoint is the standard convention for degree-day work.
    out["tavg_f"] = (out["tmax_f"] + out["tmin_f"]) / 2
    out["prcp_mm"] = tenths("PRCP")                          # tenths mm -> mm
    out["awnd_ms"] = tenths("AWND")                          # tenths m/s -> m/s

    n_missing = out[["tmax_f", "tmin_f"]].isna().sum().sum()
    print(f"  weather: {len(out):,} days, {int(n_missing)} missing temperature values")
    if n_missing:
        out[["tmax_f", "tmin_f", "tavg_f"]] = (
            out[["tmax_f", "tmin_f", "tavg_f"]].interpolate(limit=3, limit_area="inside"))
    out["prcp_mm"] = out["prcp_mm"].fillna(0.0)
    out["awnd_ms"] = out["awnd_ms"].interpolate(limit=3, limit_area="inside")
    return out


# ─────────────────────────────── main ───────────────────────────────
def main() -> pd.DataFrame:
    print("Reading ERCOT system load ...")
    load = load_system_load()
    print("Reading ERCOT fuel mix ...")
    fuel = load_fuel_mix()
    print("Reading NOAA weather ...")
    wx = load_weather()

    df = load.join(fuel, how="inner").join(wx, how="inner").sort_index()
    df.index.name = "date"

    # ---- calendar ----
    idx = df.index
    us_holidays = pyholidays.US(years=sorted(idx.year.unique()))
    df["year"] = idx.year
    df["month"] = idx.month
    df["day_of_week"] = idx.dayofweek
    df["is_weekend"] = (idx.dayofweek >= 5).astype(int)
    df["day_of_year"] = idx.dayofyear
    df["is_holiday"] = np.array([1 if d.date() in us_holidays else 0 for d in idx])

    # ---- degree-days at the conventional base ----
    df["cdd"] = np.clip(df["tavg_f"] - DEGREE_DAY_BASE_F, 0, None)
    df["hdd"] = np.clip(DEGREE_DAY_BASE_F - df["tavg_f"], 0, None)

    # ---- renewable share, both denominators, defined explicitly ----
    df["renewable_share"] = df["renewable_mwh"] / df["total_load_mwh"]
    df["renewable_share_of_gen"] = df["renewable_mwh"] / df["total_gen_mwh"]

    # ---- autoregressive features: SHIFTED, so none can see day t ----
    y = df["peak_load_mw"]
    df["peak_load_lag1"] = y.shift(1)
    df["peak_load_lag7"] = y.shift(7)
    df["peak_load_roll7_mean"] = y.shift(1).rolling(7).mean()
    df["peak_load_roll7_std"] = y.shift(1).rolling(7).std()

    df = df.drop(columns=["n_hours"])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT)
    print(f"\nWrote {OUT}")
    print(f"  {df.shape[0]:,} days x {df.shape[1]} columns")
    print(f"  {df.index.min().date()} -> {df.index.max().date()}")
    print(f"\n  peak load      {df['peak_load_mw'].min():>10,.0f} – "
          f"{df['peak_load_mw'].max():>10,.0f} MW")
    print(f"  wind (avg MW)  {df['wind_mwh'].mean()/24:>10,.0f}")
    print(f"  solar (avg MW) {df['solar_mwh'].mean()/24:>10,.0f}")
    print(f"  renewable share of generation, by year:")
    for yr, v in df.groupby("year")["renewable_share_of_gen"].mean().items():
        print(f"     {yr}: {v:.1%}")
    return df


if __name__ == "__main__":
    main()
