"""Estimation helpers: HAC slope, null-imposed block bootstrap, circular-shift placebo, expanding-window
forecasts with Clark-West, rule evaluation, stationary bootstrap, Benjamini-Hochberg / Yekutieli.
All functions take plain numpy arrays of consecutive observations (NaNs removed by the caller)."""
import numpy as np
from scipy.signal import lfilter
from scipy.stats import norm


# ----------------------------------------------------------------------------- HAC
def hac_slope(x, y, L):
    """OLS of y on [1, x]; Newey-West (Bartlett, lag L, no small-sample correction) s.e. of the slope.
    x, y: (n,) or (G, n) (row-wise regressions). Returns (b, se)."""
    scalar = (np.ndim(x) == 1)
    x = np.atleast_2d(x); y = np.atleast_2d(y)
    xd = x - x.mean(axis=1, keepdims=True)
    yd = y - y.mean(axis=1, keepdims=True)
    sxx = (xd * xd).sum(axis=1)
    b = (xd * yd).sum(axis=1) / sxx
    g = xd * (yd - b[:, None] * xd)
    S = (g * g).sum(axis=1)
    n = g.shape[1]
    for l in range(1, min(L, n - 1) + 1):
        S += 2.0 * (1.0 - l / (L + 1.0)) * (g[:, l:] * g[:, :-l]).sum(axis=1)
    se = np.sqrt(np.maximum(S, 0.0)) / sxx
    return (b[0], se[0]) if scalar else (b, se)


def hac_partial(s, y, C, L):
    """Coefficient on s in OLS of y on [1, C, s] with HAC s.e. (Frisch-Waugh: identical to the full sandwich)."""
    Z = np.column_stack([np.ones(len(s)), C])
    s_t = s - Z @ np.linalg.lstsq(Z, s, rcond=None)[0]
    y_t = y - Z @ np.linalg.lstsq(Z, y, rcond=None)[0]
    sxx = s_t @ s_t
    b = (s_t @ y_t) / sxx
    g = s_t * (y_t - b * s_t)
    S = g @ g
    for l in range(1, min(L, len(g) - 1) + 1):
        S += 2.0 * (1.0 - l / (L + 1.0)) * (g[l:] @ g[:-l])
    return b, np.sqrt(max(S, 0.0)) / sxx


def p_two_sided(t):
    return 2.0 * norm.sf(np.abs(t))


# ----------------------------------------------------------------------------- forward returns on a compacted sample
def fwd_sum(r1, h):
    """h-step forward sum of consecutive 1-step returns: out[i] = r1[i] + ... + r1[i+h-1]; length n-h+1."""
    cs = np.concatenate([[0.0], np.cumsum(r1)])
    return cs[h:] - cs[:-h]


# ----------------------------------------------------------------------------- bootstrap under the null
def ar1_fit(s):
    x0, x1 = s[:-1], s[1:]
    rho = np.cov(x0, x1, bias=True)[0, 1] / np.var(x0)
    n = len(s)
    rho_c = min(rho + (1.0 + 3.0 * rho) / n, 0.9999)      # Kendall bias correction
    c = s.mean() * (1.0 - rho_c)
    u = x1 - c - rho_c * x0
    return rho, rho_c, c, u - u.mean()


def boot_null_tstats(s, r1, horizons, lags, B, block, rng, K=10, chunk=250):
    """Bootstrap distribution of the HAC t-statistic of the slope under the null of no predictability.
    s: signal (n,), r1: 1-day forward return aligned with s (n,).
      returns : r1*_t = mu + e_t * w_t, w_t = +-1 at random (wild bootstrap). Keeps the realised volatility path
                and fat tails, and makes every return unpredictable from anything dated t or earlier.
      signal  : s*_t = c + rho s*_{t-1} + u*_t (rho with Kendall bias correction),
                u*_t = sum_{k=1..K} gamma_k e*_{t-k} + v*_t.
                gamma: OLS of the actual innovation on the K previous return residuals, so the feedback from past
                price moves into the signal (the source of Stambaugh bias, strong for price-built metrics and
                spread over several days by the 2-day publication lag and the 7-day smoothing) is kept;
                v*: moving-block resample (block days) of the remainder, drawn independently of the returns.
    Returns (dict h -> array (B,) of t*, info dict)."""
    n = len(s)
    rho, rho_c, c, u = ar1_fit(s)                       # u[j] is the innovation at t = j + 1
    mu = r1.mean()
    e = r1 - mu
    t_idx = np.arange(K, n)
    Xlag = np.column_stack([e[t_idx - k] for k in range(1, K + 1)])
    uu = u[t_idx - 1]
    gamma = np.linalg.lstsq(Xlag, uu, rcond=None)[0]
    v = uu - Xlag @ gamma
    v = v - v.mean()
    m = len(v)
    nb = int(np.ceil(n / block))
    out = {h: np.empty(B) for h in horizons}
    done = 0
    while done < B:
        G = min(chunk, B - done)
        Es = e[None, :] * rng.choice(np.array([-1.0, 1.0]), size=(G, n))
        F = np.zeros((G, n))
        for k in range(1, K + 1):
            F[:, k:] += gamma[k - 1] * Es[:, :-k]
        starts = rng.integers(0, m - block + 1, size=(G, nb))
        idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(G, nb * block)[:, :n]
        s0 = s[rng.integers(0, n, size=G)]
        S, _ = lfilter([1.0], [1.0, -rho_c], c + F + v[idx], axis=1, zi=(rho_c * s0)[:, None])
        cs = np.concatenate([np.zeros((G, 1)), np.cumsum(mu + Es, axis=1)], axis=1)
        for h in horizons:
            Y = cs[:, h:] - cs[:, :-h]                  # (G, n-h+1)
            b, se = hac_slope(S[:, : n - h + 1], Y, lags[h])
            out[h][done:done + G] = b / se
        done += G
    r2_fb = 1.0 - (v @ v) / ((uu - uu.mean()) @ (uu - uu.mean()))
    return out, dict(rho=float(rho), rho_c=float(rho_c), feedback_r2=float(r2_fb))


def boot_null_tstats_pairblocks(s, r1, horizons, lags, B, block, rng, chunk=250):
    """PRE-REGISTERED DESIGN, NOT USED: kept only so that tests/test_stats.py can show why it was replaced.
    Resampling 60-day blocks of (signal innovation, return) pairs keeps, inside every block, the sample
    covariance between the accumulated innovations (the local level of a persistent signal) and the returns
    that followed, so the null of no predictability is not imposed: the bootstrap distribution is centred near
    the observed statistic and the test almost never rejects (size 0-2% at a nominal 5%).
    Original description: null-imposed bootstrap distribution of the HAC t-statistic, for every horizon.
    s: signal (n,), r1: 1-day forward return aligned with s (n,).
    Model: r1_t = mu + e_t;  s_t = c + rho s_{t-1} + u_t. Pairs (u_t, e_t), t = 1..n-1, are resampled in
    moving blocks, which keeps their lead-lag correlation, volatility clustering and residual serial correlation.
    Returns dict h -> array (B,) of t*."""
    n = len(s)
    rho, rho_c, c, u = ar1_fit(s)
    e = (r1 - r1.mean())[1:]
    m = n - 1
    nb = int(np.ceil(m / block))
    out = {h: np.empty(B) for h in horizons}
    done = 0
    while done < B:
        G = min(chunk, B - done)
        starts = rng.integers(0, m - block + 1, size=(G, nb))
        idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(G, nb * block)[:, :m]
        U, E = u[idx], e[idx]
        s0 = s[rng.integers(0, n, size=G)]
        S, _ = lfilter([1.0], [1.0, -rho_c], c + U, axis=1, zi=(rho_c * s0)[:, None])
        R1 = r1.mean() + E
        cs = np.concatenate([np.zeros((G, 1)), np.cumsum(R1, axis=1)], axis=1)
        for h in horizons:
            Y = cs[:, h:] - cs[:, :-h]                 # (G, m-h+1)
            b, se = hac_slope(S[:, : m - h + 1], Y, lags[h])
            out[h][done:done + G] = b / se
        done += G
    return out, dict(rho=rho, rho_c=rho_c)


# ----------------------------------------------------------------------------- circular-shift placebo
def placebo_shift_tstats(s, y_by_h, lags, step=7, margin=90, C=None):
    """t-statistics with the signal circularly shifted by k = margin, margin+step, ..., n-margin.
    y_by_h: dict h -> (n_h,) forward returns aligned with s[:n_h]. If C (n, p) is given, the controls stay
    aligned with the returns and only the signal is shifted (partial regression)."""
    n = len(s)
    ks = np.arange(margin, n - margin + 1, step)
    Sh = np.stack([np.roll(s, k) for k in ks])          # (K, n)
    out = {}
    for h, y in y_by_h.items():
        nh = len(y)
        if C is None:
            b, se = hac_slope(Sh[:, :nh], np.broadcast_to(y, (len(ks), nh)), lags[h])
            out[h] = b / se
        else:
            Z = np.column_stack([np.ones(nh), C[:nh]])
            Q, _ = np.linalg.qr(Z)
            Xs = Sh[:, :nh] - (Sh[:, :nh] @ Q) @ Q.T
            yt = y - Q @ (Q.T @ y)
            sxx = (Xs * Xs).sum(axis=1)
            b = (Xs @ yt) / sxx
            g = Xs * (yt[None, :] - b[:, None] * Xs)
            S = (g * g).sum(axis=1)
            L = lags[h]
            for l in range(1, min(L, nh - 1) + 1):
                S += 2.0 * (1.0 - l / (L + 1.0)) * (g[:, l:] * g[:, :-l]).sum(axis=1)
            out[h] = b / (np.sqrt(np.maximum(S, 0.0)) / sxx)
    return ks, out


# ----------------------------------------------------------------------------- expanding-window forecasts
def expanding_forecast(X, y, h, min_train):
    """Forecast y[i] at day i from OLS of y on [1, X] estimated on rows j <= i - h with all values present.
    X: (n, p) (p may be 0 -> historical mean), y: (n,), both on a consecutive daily grid, NaN allowed.
    Returns yhat (n,) (NaN where not available)."""
    n = len(y)
    Z = np.column_stack([np.ones(n)] + ([X] if X is not None and X.size else []))
    ok = np.isfinite(y) & np.isfinite(Z).all(axis=1)
    Zc = np.where(ok[:, None], Z, 0.0); yc = np.where(ok, y, 0.0)
    p = Z.shape[1]
    XtX = np.cumsum(Zc[:, :, None] * Zc[:, None, :], axis=0)     # (n, p, p) inclusive
    Xty = np.cumsum(Zc * yc[:, None], axis=0)
    cnt = np.cumsum(ok)
    yhat = np.full(n, np.nan)
    i = np.arange(h, n)
    j = i - h
    use = (cnt[j] >= max(min_train, p + 2)) & np.isfinite(Z[i]).all(axis=1)
    ii, jj = i[use], j[use]
    if ii.size:
        A = XtX[jj] + 1e-12 * np.eye(p)[None]
        beta = np.linalg.solve(A, Xty[jj][:, :, None])[:, :, 0]
        yhat[ii] = (Z[ii] * beta).sum(axis=1)
    return yhat


def clark_west(y, f_small, f_big, L):
    """OOS R2 of the bigger model against the smaller one and the Clark-West (2007) one-sided p-value."""
    ok = np.isfinite(y) & np.isfinite(f_small) & np.isfinite(f_big)
    y, a, b = y[ok], f_small[ok], f_big[ok]
    if len(y) < 50:
        return np.nan, np.nan, np.nan, int(len(y))
    e1, e2 = y - a, y - b
    r2 = 1.0 - (e2 @ e2) / (e1 @ e1)
    f = e1 ** 2 - (e2 ** 2 - (a - b) ** 2)
    fd = f - f.mean()
    S = fd @ fd
    for l in range(1, min(L, len(f) - 1) + 1):
        S += 2.0 * (1.0 - l / (L + 1.0)) * (fd[l:] @ fd[:-l])
    se = np.sqrt(max(S, 0.0)) / len(f)
    t = f.mean() / se if se > 0 else np.nan
    return r2, t, float(norm.sf(t)) if np.isfinite(t) else np.nan, int(len(y))


# ----------------------------------------------------------------------------- trading rule
def rule_positions(s, q, theta):
    """1 when q*(s - theta) > 0, 0 otherwise; missing signal -> flat."""
    return np.where(np.isfinite(s) & (q * (s - theta) > 0), 1.0, 0.0)


def rule_returns(pos, r_simple, cost, prev_pos=0.0):
    """Daily net simple returns: position held over the day times the day's return, minus cost on changes."""
    turn = np.abs(np.diff(np.concatenate([[prev_pos], pos])))
    return pos * r_simple - cost * turn, turn


def perf(net, ann=365):
    n = len(net)
    if n == 0:
        return dict(cagr=np.nan, sharpe=np.nan, maxdd=np.nan, vol=np.nan)
    eq = np.cumprod(1.0 + net)
    cagr = eq[-1] ** (ann / n) - 1.0
    sd = net.std(ddof=1)
    sharpe = net.mean() / sd * np.sqrt(ann) if sd > 0 else 0.0
    peak = np.maximum.accumulate(np.concatenate([[1.0], eq]))
    maxdd = float((np.concatenate([[1.0], eq]) / peak - 1.0).min())
    return dict(cagr=float(cagr), sharpe=float(sharpe), maxdd=maxdd, vol=float(sd * np.sqrt(ann)))


def sharpe_rows(X, ann=365):
    sd = X.std(axis=1, ddof=1)
    return np.where(sd > 0, X.mean(axis=1) / np.where(sd > 0, sd, 1.0) * np.sqrt(ann), 0.0)


def stationary_bootstrap_idx(n, B, mean_block, rng):
    """Politis-Romano stationary bootstrap indices, shape (B, n)."""
    p = 1.0 / mean_block
    idx = np.empty((B, n), dtype=np.int64)
    idx[:, 0] = rng.integers(0, n, size=B)
    jump = rng.random((B, n)) < p
    newstart = rng.integers(0, n, size=(B, n))
    for t in range(1, n):
        idx[:, t] = np.where(jump[:, t], newstart[:, t], (idx[:, t - 1] + 1) % n)
    return idx


# ----------------------------------------------------------------------------- multiple testing
def bh(p, q):
    """Benjamini-Hochberg rejections (boolean array) at level q; NaN p-values are never rejected."""
    p = np.asarray(p, float)
    ok = np.isfinite(p)
    rej = np.zeros(p.shape, bool)
    m = int(ok.sum())
    if m == 0:
        return rej
    order = np.argsort(np.where(ok, p, np.inf))[:m]
    thr = q * np.arange(1, m + 1) / m
    below = p[order] <= thr
    if below.any():
        kmax = np.nonzero(below)[0].max()
        rej[order[: kmax + 1]] = True
    return rej


def by(p, q):
    p = np.asarray(p, float)
    m = int(np.isfinite(p).sum())
    return bh(p, q / np.sum(1.0 / np.arange(1, m + 1))) if m else np.zeros(p.shape, bool)


def bh_adjust(p):
    """BH-adjusted p-values (q-values)."""
    p = np.asarray(p, float)
    ok = np.isfinite(p)
    out = np.full(p.shape, np.nan)
    m = int(ok.sum())
    if m == 0:
        return out
    order = np.argsort(np.where(ok, p, np.inf))[:m]
    adj = p[order] * m / np.arange(1, m + 1)
    adj = np.minimum.accumulate(adj[::-1])[::-1]
    out[order] = np.minimum(adj, 1.0)
    return out
