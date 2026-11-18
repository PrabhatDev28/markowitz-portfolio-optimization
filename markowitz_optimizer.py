"""
Markowitz Portfolio Optimization
--------------------------------
Finds the best mix of stocks using Modern Portfolio Theory:
  - Maximum Sharpe ratio portfolio (best return per unit of risk)
  - Minimum volatility portfolio (lowest risk)
  - Efficient frontier

Change the settings in the "Settings" cell to experiment.
Not financial advice - this is a learning project.
"""

# %% Imports
import os

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import yfinance as yf
from scipy.optimize import minimize

# %% Settings
TICKERS = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ITC.NS", "SUNPHARMA.NS"]
HISTORY_PERIOD = "5y"      # how much past data to use: "1y", "3y", "5y", "10y"
RISK_FREE_RATE = 0.07      # annual risk-free rate (about 7% for Indian govt bonds)
NUM_PORTFOLIOS = 10000     # random portfolios for the scatter cloud
MAX_WEIGHT = 1.0           # cap per stock (e.g. 0.4 = max 40%); must be >= 1/number of stocks
TRADING_DAYS = 252         # trading days in a year
SEED = 42
# Set USE_DEMO_DATA=1 to run on made-up data (only for testing without internet)
USE_DEMO_DATA = os.getenv("USE_DEMO_DATA", "0") == "1"

np.random.seed(SEED)


# %% Load prices
def load_prices(tickers, period):
    """Download adjusted closing prices from Yahoo Finance."""
    if USE_DEMO_DATA:
        days = 252 * 5
        n = len(tickers)
        A = np.random.randn(n, n) * 0.004
        cov = A @ A.T + np.eye(n) * 0.0001
        rets = np.random.multivariate_normal(np.linspace(0.0003, 0.0009, n), cov, size=days)
        idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days)
        return pd.DataFrame(100 * np.cumprod(1 + rets, axis=0), index=idx, columns=tickers)

    data = yf.download(tickers, period=period, auto_adjust=True, progress=False)["Close"]
    data = data[tickers].dropna()
    if data.empty:
        raise ValueError("No data downloaded. Check the tickers and your internet connection.")
    return data


prices = load_prices(TICKERS, HISTORY_PERIOD)
print(f"Downloaded {len(prices)} days of prices for {len(TICKERS)} stocks")

# %% Returns, expected return and risk
daily_returns = prices.pct_change().dropna()
mean_returns = daily_returns.mean() * TRADING_DAYS      # annual expected return
cov_matrix = daily_returns.cov() * TRADING_DAYS         # annual covariance matrix
n_assets = len(TICKERS)


def portfolio_stats(weights):
    """Return (expected return, volatility, Sharpe ratio) for a set of weights."""
    ret = float(weights @ mean_returns.values)
    vol = float(np.sqrt(weights @ cov_matrix.values @ weights))
    sharpe = (ret - RISK_FREE_RATE) / vol
    return ret, vol, sharpe


# %% Random portfolios (Monte Carlo cloud)
random_ret = np.zeros(NUM_PORTFOLIOS)
random_vol = np.zeros(NUM_PORTFOLIOS)
random_sharpe = np.zeros(NUM_PORTFOLIOS)

for i in range(NUM_PORTFOLIOS):
    w = np.random.random(n_assets)
    w /= w.sum()
    random_ret[i], random_vol[i], random_sharpe[i] = portfolio_stats(w)

# %% Optimization (SLSQP, long-only, weights sum to 1)
bounds = tuple((0, MAX_WEIGHT) for _ in range(n_assets))
sum_to_one = {"type": "eq", "fun": lambda w: np.sum(w) - 1}
start = np.repeat(1 / n_assets, n_assets)

max_sharpe = minimize(lambda w: -portfolio_stats(w)[2], start,
                      method="SLSQP", bounds=bounds, constraints=[sum_to_one])
min_vol = minimize(lambda w: portfolio_stats(w)[1], start,
                   method="SLSQP", bounds=bounds, constraints=[sum_to_one])

w_sharpe = max_sharpe.x
w_minvol = min_vol.x
w_equal = start

# %% Efficient frontier
frontier_vol = []
frontier_ret = np.linspace(portfolio_stats(w_minvol)[0], mean_returns.max() * 0.98, 50)

for target in frontier_ret:
    constraints = [sum_to_one,
                   {"type": "eq", "fun": lambda w, t=target: portfolio_stats(w)[0] - t}]
    res = minimize(lambda w: portfolio_stats(w)[1], start,
                   method="SLSQP", bounds=bounds, constraints=constraints)
    frontier_vol.append(res.fun if res.success else np.nan)

# %% Results table
summary = pd.DataFrame(
    [portfolio_stats(w) for w in (w_sharpe, w_minvol, w_equal)],
    index=["Max Sharpe", "Min Volatility", "Equal Weight"],
    columns=["Expected return", "Volatility", "Sharpe ratio"],
)
weights_table = pd.DataFrame(
    {"Max Sharpe": w_sharpe, "Min Volatility": w_minvol, "Equal Weight": w_equal},
    index=TICKERS,
)

print("\n=== Portfolio comparison (annual) ===")
print(summary.round(3).to_string())
print("\n=== Optimal weights ===")
print((weights_table * 100).round(1).astype(str).add("%").to_string())

# %% Plots
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

# Left: efficient frontier
sc = ax1.scatter(random_vol, random_ret, c=random_sharpe, cmap="viridis", s=8, alpha=0.6)
fig.colorbar(sc, ax=ax1, label="Sharpe ratio")
ax1.plot(frontier_vol, frontier_ret, "r--", linewidth=2, label="Efficient frontier")

ax1.scatter(summary.loc["Max Sharpe", "Volatility"], summary.loc["Max Sharpe", "Expected return"],
            marker="*", color="gold", edgecolor="black", s=350, label="Max Sharpe", zorder=5)
ax1.scatter(summary.loc["Min Volatility", "Volatility"], summary.loc["Min Volatility", "Expected return"],
            marker="D", color="red", edgecolor="black", s=100, label="Min volatility", zorder=5)

asset_vol = np.sqrt(np.diag(cov_matrix.values))
ax1.scatter(asset_vol, mean_returns.values, marker="o", color="black", s=40, label="Individual stocks")
for name, x, y in zip(TICKERS, asset_vol, mean_returns.values):
    ax1.annotate(name.replace(".NS", ""), (x, y), textcoords="offset points", xytext=(5, 5), fontsize=8)

ax1.set_title(f"Efficient Frontier ({NUM_PORTFOLIOS:,} random portfolios)")
ax1.set_xlabel("Volatility (annual risk)")
ax1.set_ylabel("Expected return (annual)")
ax1.legend(loc="lower right")

# Right: weights comparison
weights_table.plot(kind="bar", ax=ax2, width=0.8)
ax2.set_title("Portfolio Weights by Strategy")
ax2.set_ylabel("Weight")
ax2.set_xticklabels([t.replace(".NS", "") for t in TICKERS], rotation=45, ha="right")
ax2.legend()

plt.tight_layout()
plt.savefig("portfolio_results.png", dpi=150, bbox_inches="tight")
plt.show()
