"""Checks of the estimation helpers.
 1. hac_slope / hac_partial reproduce statsmodels' HAC (Bartlett, no small-sample correction).
 2. expanding_forecast reproduces a brute-force loop.
 3. Size and power of the null-imposed block bootstrap on simulated data with a persistent signal whose
    innovations are correlated with returns (Stambaugh setting), 30-day overlapping returns.
 4. BH on a known example.
Run: .venv/bin/python -I tests/test_stats.py        (add the argument `fast` to skip part 3, about 6 minutes)"""
import os, sys, time
import numpy as np
import statsmodels.api as sm
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
from stats import (hac_slope, hac_partial, fwd_sum, boot_null_tstats, boot_null_tstats_pairblocks, expanding_forecast, clark_west, bh, by,
                   bh_adjust, placebo_shift_tstats, p_two_sided)

rng = np.random.default_rng(7)
# ---- 1
n = 1500
x = np.cumsum(rng.normal(size=n)) * 0.05 + rng.normal(size=n)
C = rng.normal(size=(n, 3)) + 0.3 * x[:, None]
y = 0.1 * x + rng.normal(size=n) * (1 + 0.5 * np.abs(x)) + 0.2 * C[:, 0]
for L in (5, 12, 58):
    b, se = hac_slope(x, y, L)
    ref = sm.OLS(y, sm.add_constant(x)).fit(cov_type="HAC", cov_kwds=dict(maxlags=L, use_correction=False))
    assert abs(b - ref.params[1]) < 1e-10 and abs(se - ref.bse[1]) < 1e-10, (L, b, ref.params[1], se, ref.bse[1])
    b2, se2 = hac_partial(x, y, C, L)
    ref2 = sm.OLS(y, sm.add_constant(np.column_stack([C, x]))).fit(cov_type="HAC", cov_kwds=dict(maxlags=L, use_correction=False))
    assert abs(b2 - ref2.params[-1]) < 1e-10 and abs(se2 - ref2.bse[-1]) < 1e-9, (L, b2, ref2.params[-1], se2, ref2.bse[-1])
    # the vectorised placebo path (with and without controls) must reproduce the same statistics at shift 0
    for CC, tref in ((None, b / se), (C, b2 / se2)):
        xs = np.roll(x, -100)                      # placebo rolls it back by k = 100
        ks, out = placebo_shift_tstats(xs, {1: y}, {1: L}, step=10**9, margin=100, C=CC)
        assert ks.tolist() == [100] and abs(out[1][0] - tref) < 1e-8, (L, out[1][0], tref)
print("1 OK: HAC slope and partial slope equal statsmodels (lags 5, 12, 58)")

# ---- 2
h = 7
yy = fwd_sum(rng.normal(size=600 + h - 1), h)
X = rng.normal(size=(600, 2)); X[50:60, 0] = np.nan; yy[100:105] = np.nan
fh = expanding_forecast(X, yy, h, min_train=100)
for i in (150, 300, 599):
    j = np.arange(0, i - h + 1)
    ok = np.isfinite(yy[j]) & np.isfinite(X[j]).all(axis=1)
    Z = np.column_stack([np.ones(ok.sum()), X[j][ok]])
    beta = np.linalg.lstsq(Z, yy[j][ok], rcond=None)[0]
    assert abs(fh[i] - (beta[0] + X[i] @ beta[1:])) < 1e-8, (i, fh[i])
fm = expanding_forecast(None, yy, h, min_train=100)
assert abs(fm[300] - np.nanmean(yy[: 300 - h + 1])) < 1e-10
assert np.isnan(fh[:100 + h - 1]).all()
print("2 OK: expanding forecasts equal a brute-force refit and use only rows j <= i - h")

# ---- 3
def simulate(n, rho, corr, b, rng, lag=1, garch=False):
    """Persistent signal; its innovation at t is correlated (corr) with the return that ended `lag` days earlier."""
    z = rng.normal(size=(n + lag, 2))
    if garch:
        sig2 = np.empty(n + lag); sig2[0] = 1.0; e = np.empty(n + lag)
        for t in range(n + lag):
            if t:
                sig2[t] = 0.05 + 0.10 * e[t - 1] ** 2 + 0.85 * sig2[t - 1]
            e[t] = np.sqrt(sig2[t]) * z[t, 1]
        e = e * 0.03
        shock = z[:, 1]
    else:
        vol = np.exp(0.3 * np.sin(np.arange(n + lag) / 50.0))
        e = z[:, 1] * vol * 0.03
        shock = z[:, 1]
    r_past = e                                     # r_past[t]: return over [t-1, t] in units used below
    u = corr * np.roll(shock, lag - 1) + np.sqrt(1 - corr ** 2) * z[:, 0]   # innovation at t loads on the return ending at t-(lag-1)
    s = np.empty(n + lag); s[0] = 0.0
    for t in range(1, n + lag):
        s[t] = rho * s[t - 1] + np.sqrt(1 - rho ** 2) * u[t]
    r1 = b * s[:-1] + r_past[1:]                   # return over [t, t+1]
    return s[lag:-1] if lag > 0 else s[:-1], r1[lag:]

H, LAGS = (1, 7, 30), {1: 5, 7: 12, 30: 58}
t0 = time.time()
cases = (("A size: Stambaugh feedback lag 1, corr -0.6, rho 0.985", dict(rho=0.985, corr=-0.6, b=0.0, lag=1), 300),
         ("B size: feedback lag 2, corr -0.8, rho 0.995, GARCH returns", dict(rho=0.995, corr=-0.8, b=0.0, lag=2, garch=True), 300),
         ("C size: exogenous signal, rho 0.97, GARCH returns", dict(rho=0.97, corr=0.0, b=0.0, lag=1, garch=True), 300),
         ("D power: as A with b = 0.003 per day per sd", dict(rho=0.985, corr=-0.6, b=0.003, lag=1), 100))
FAST = len(sys.argv) > 1 and sys.argv[1] == "fast"      # skip the 5-minute simulation
for label, kw, nsim in ([] if FAST else cases):
    rej = {k: {h: 0 for h in H} for k in ("new", "old", "hac")}
    for i in range(nsim):
        s, r1 = simulate(2000, rng=rng, **kw)
        dist, _ = boot_null_tstats(s, r1, H, LAGS, 399, 60, rng, chunk=200)
        dold, _ = boot_null_tstats_pairblocks(s, r1, H, LAGS, 399, 60, rng, chunk=200)
        for h in H:
            y = fwd_sum(r1, h)
            b, se = hac_slope(s[: len(y)], y, LAGS[h])
            t = b / se
            rej["hac"][h] += p_two_sided(t) < 0.05
            rej["new"][h] += (1 + (np.abs(dist[h]) >= abs(t)).sum()) / 400 < 0.05
            rej["old"][h] += (1 + (np.abs(dold[h]) >= abs(t)).sum()) / 400 < 0.05
    print(f"3{label}: rejection rate at nominal 5% ({nsim} sims, {time.time()-t0:.0f}s)")
    for k, name in (("new", "bootstrap used (wild returns + feedback)"), ("old", "pre-registered pair-block bootstrap"), ("hac", "HAC with normal critical values")):
        print(f"     {name:42s} " + "  ".join(f"h={h}: {rej[k][h]/nsim:.3f}" for h in H))

# ---- 4
p = np.array([0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216, 0.222, 0.251, 0.269, 0.275, 0.34, 0.341, 0.384, 0.569, 0.594, 0.696, 0.762, 0.94, 0.942, 0.975, 0.986])
# with the standard '<=' rule the 6th value (0.060 <= 6/25*0.25) is rejected too
assert bh(p, 0.05).sum() == 1 and bh(p, 0.25).sum() == 6 and by(p, 0.05).sum() == 0
assert abs(bh_adjust(p)[0] - 0.025) < 1e-12
print("4 OK: Benjamini-Hochberg / Yekutieli on a textbook example")
