import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def generate_forecast_day(date="2026-04-29", seed=42):
    np.random.seed(seed)

    timestamps = pd.date_range(
        start=f"{date} 00:00:00",
        periods=96,
        freq="15min"
    )

    hours = np.array([t.hour + t.minute / 60 for t in timestamps])

    # Base electricity price shape
    base_price = (
        55
        + 18 * np.sin((hours - 7) * np.pi / 12)
        + 45 * np.exp(-((hours - 19) ** 2) / 5)
    )

    # Solar effect: depresses midday prices
    solar_effect = -28 * np.exp(-((hours - 13) ** 2) / 7)

    # Small morning bump
    morning_bump = 12 * np.exp(-((hours - 8) ** 2) / 3)

    # Random market noise
    noise = np.random.normal(0, 4.5, size=96)

    # Median forecast
    p50 = base_price + solar_effect + morning_bump + noise
    p50 = np.clip(p50, -10, 300)

    # Uncertainty: wider during volatile periods
    uncertainty = (
        7
        + 13 * np.exp(-((hours - 19) ** 2) / 5)
        + 6 * np.exp(-((hours - 13) ** 2) / 8)
    )

    p10 = np.clip(p50 - uncertainty, -50, None)
    p90 = np.clip(p50 + uncertainty, None, 400)

    df = pd.DataFrame({
        "timestamp": timestamps,
        "hour": hours,
        "p10_eur_mwh": p10,
        "p50_eur_mwh": p50,
        "p90_eur_mwh": p90,
        "uncertainty_band": p90 - p10,
    })

    return df


def plot_forecast_band(df):
    plt.figure(figsize=(14, 6))

    plt.fill_between(
        df["timestamp"],
        df["p10_eur_mwh"],
        df["p90_eur_mwh"],
        alpha=0.25,
        label="P10–P90 uncertainty band"
    )

    plt.plot(df["timestamp"], df["p50_eur_mwh"], linewidth=2, label="P50 forecast")
    plt.plot(df["timestamp"], df["p10_eur_mwh"], linestyle="--", linewidth=1, label="P10")
    plt.plot(df["timestamp"], df["p90_eur_mwh"], linestyle="--", linewidth=1, label="P90")

    plt.title("Synthetic Day-Ahead Price Forecast")
    plt.xlabel("Time")
    plt.ylabel("Price (€/MWh)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.show()


def plot_charge_discharge_zones(df):
    low_threshold = df["p50_eur_mwh"].quantile(0.25)
    high_threshold = df["p50_eur_mwh"].quantile(0.75)

    charge = df["p50_eur_mwh"] <= low_threshold
    discharge = df["p50_eur_mwh"] >= high_threshold

    plt.figure(figsize=(14, 6))

    plt.plot(df["timestamp"], df["p50_eur_mwh"], linewidth=2, label="P50 forecast")

    plt.scatter(
        df.loc[charge, "timestamp"],
        df.loc[charge, "p50_eur_mwh"],
        marker="v",
        s=60,
        label="Candidate charge intervals"
    )

    plt.scatter(
        df.loc[discharge, "timestamp"],
        df.loc[discharge, "p50_eur_mwh"],
        marker="^",
        s=60,
        label="Candidate discharge intervals"
    )

    plt.axhline(low_threshold, linestyle="--", linewidth=1, label="Charge threshold")
    plt.axhline(high_threshold, linestyle="--", linewidth=1, label="Discharge threshold")

    plt.title("Candidate Charge / Discharge Intervals")
    plt.xlabel("Time")
    plt.ylabel("Price (€/MWh)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    df = generate_forecast_day(date="2026-04-29", seed=42)

    print(df.head())
    print(df.describe())

    df.to_csv("synthetic_forecast_day.csv", index=False)

    plot_forecast_band(df)
    plot_charge_discharge_zones(df)