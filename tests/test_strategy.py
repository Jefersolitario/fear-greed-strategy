"""The backtest must reproduce the audited numbers, and published history must be append-only."""
import datetime as dt
import pathlib

import numpy as np
import polars as pl
import pytest

from fng import cli, contract, data
from fng.engine import stats

ROOT = pathlib.Path(__file__).resolve().parents[1]
SNAPSHOT_END = dt.date(2026, 11, 14)


@pytest.fixture(scope="module")
def built():
    cfg = cli.load_config(ROOT / "strategies.toml")
    inputs = data.load_inputs(ROOT / "data").filter(pl.col("date") <= SNAPSHOT_END)
    daily, summary = cli.build(inputs, cfg)
    return cfg, inputs, daily, {r["strategy_id"]: r for r in summary.iter_rows(named=True)}


# buys, PnL, max drawdown from the independent audit of the original backtest (data to 14 Nov 2026)
AUDITED = {
    "fng20_hold": (350, 1_567_975, 1_895_742),
    "fng10_hold": (42, 107_780, 135_139),
    "fng20_below_2y_avg": (228, 991_848, 1_181_455),
    "fng20_mayer": (237, 1_079_517, 1_294_473),
}


@pytest.mark.parametrize("sid", AUDITED)
def test_backtest_matches_audit(built, sid):
    buys, pnl, max_dd = AUDITED[sid]
    row = built[3][sid]
    assert row["buys"] == buys
    assert row["pnl"] == pytest.approx(pnl, abs=25)
    assert row["max_dd"] == pytest.approx(max_dd, abs=25)


def test_sell_at_80_variant(built):
    row = built[3]["fng10_sell80"]
    assert row["buys"] == 42
    assert row["pnl"] == pytest.approx(24_392, abs=25)


def test_headline_ratios(built):
    row = built[3]["fng20_hold"]
    assert row["sharpe"] == pytest.approx(0.25, abs=0.01)
    assert row["sortino"] == pytest.approx(0.36, abs=0.01)
    assert row["placebo_p"] == pytest.approx(0.14, abs=0.01)


def test_daily_tables_follow_contract(built):
    _, _, daily, summary = built
    assert set(daily) == {"fng10_hold", "fng20_below_2y_avg", "fng10_sell80"}
    for sid, t in daily.items():
        t = contract.validate_daily(t)
        assert t["pnl"].sum() == pytest.approx(summary[sid]["pnl"], abs=0.01)     # daily PnL adds up to the total
        assert stats(t["pnl"].to_numpy())["max_dd"] == pytest.approx(summary[sid]["max_dd"], abs=0.01)
        assert (t["mode"] == "backtest").all()                                    # snapshot ends before paper_start


def test_filter_uses_only_yesterdays_close(built):
    """Changing today's close must not change today's decision."""
    cfg, inputs, _, _ = built
    rule = next(r["rule"] for r in cfg["rules"] if r["id"] == "fng20_below_2y_avg")
    from fng.engine import buy_mask
    close = inputs["close"].to_numpy().astype(float)
    fng = inputs["fng"].cast(pl.Float64).to_numpy()
    base = buy_mask(fng, close, rule)
    bumped = close.copy()
    bumped[-1] *= 10
    assert buy_mask(fng, bumped, rule)[-1] == base[-1]


def _extend(inputs: pl.DataFrame, days: int, fng: int, close: float) -> pl.DataFrame:
    last = inputs["date"].max()
    extra = pl.DataFrame({"date": [last + dt.timedelta(days=i + 1) for i in range(days)], "fng": [fng] * days,
                          "close": [close] * days, "close_source": ["test"] * days}, schema=data.SCHEMA)
    return pl.concat([inputs, extra])


def test_paper_book_starts_flat_and_history_is_append_only(built, tmp_path):
    cfg, inputs, _, _ = built
    out = str(tmp_path / "results")
    first, _ = cli.build(inputs, cfg)
    for sid, t in first.items():
        contract.publish_strategy(out, _manifest(sid), t)

    # ten more days with the index at 5 and a flat price: paper buys from paper_start only
    longer = _extend(inputs, 10, fng=5, close=60_000.0)
    second, _ = cli.build(longer, cfg)
    t = second["fng10_hold"]
    paper = t.filter(pl.col("mode") == "paper")
    assert paper["date"].min() == cfg["paper_start"]
    n_paper_days = (longer["date"].max() - cfg["paper_start"]).days + 1
    assert paper["n_trades"].sum() == n_paper_days
    assert paper["pnl"][0] == pytest.approx(-1.0, abs=1e-6)          # first fill costs 10 bps of 1,000 USD
    for sid, tab in second.items():
        contract.publish_strategy(out, _manifest(sid), tab)           # only adds days: allowed

    # rewriting a published day is refused
    tampered = second["fng10_hold"].with_columns(pl.when(pl.col("date") == cfg["paper_start"]).then(pl.col("pnl") + 50).otherwise(pl.col("pnl")).alias("pnl"))
    with pytest.raises(RuntimeError, match="would change"):
        contract.publish_strategy(out, _manifest("fng10_hold"), tampered)


def _manifest(sid: str) -> dict:
    return {"id": sid, "name": sid, "market": "BTC-USD spot", "currency": "USD", "days_per_year": 365,
            "backtest_start": "2018-02-01", "paper_start": "2026-11-18", "description": ""}


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


class _Session:
    """Stands in for the two live APIs."""

    def __init__(self, fng: dict, closes: dict):
        self.fng, self.closes = fng, closes

    def get(self, url, **kw):
        ts = lambda d: int(dt.datetime.combine(d, dt.time(), dt.timezone.utc).timestamp())
        if "alternative.me" in url:
            return _Resp({"data": [{"value": str(v), "timestamp": str(ts(d))} for d, v in self.fng.items()]})
        return _Resp([[ts(d), 0, 0, 0, c, 0] for d, c in self.closes.items()])


def test_live_update_appends_only_complete_days_and_refuses_restated_inputs(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    (d / "inputs_snapshot.csv").write_bytes((ROOT / "data" / "inputs_snapshot.csv").read_bytes())
    day = lambda k: SNAPSHOT_END + dt.timedelta(days=k)
    stored = data.load_inputs(d).filter(pl.col("date") > day(-6))
    fng = {r["date"]: r["fng"] for r in stored.iter_rows(named=True)} | {day(1): 12, day(2): 9, day(3): 30}
    closes = {r["date"]: r["close"] * 1.001 for r in stored.iter_rows(named=True)} | {day(1): 63_000.0, day(2): 61_500.0, day(3): 64_000.0}

    out = data.update_live(d, today_utc=day(3), session=_Session(fng, closes))       # day(3) is still open
    assert out["date"].max() == day(2)
    assert out.filter(pl.col("date") == day(2))["fng"][0] == 9
    again = data.update_live(d, today_utc=day(3), session=_Session(fng, closes))     # idempotent
    assert again.height == out.height

    closes_bad = dict(closes) | {day(2): 61_500.0 * 1.05}
    with pytest.raises(RuntimeError, match="is stored as"):
        data.update_live(d, today_utc=day(4), session=_Session(fng, closes_bad))


def test_sell_at_80_paper_book_sells_everything_and_goes_flat(built):
    cfg, inputs, _, _ = built
    up = _extend(_extend(inputs, 6, fng=5, close=60_000.0), 2, fng=85, close=66_000.0)     # 3 paper buys, then the index hits 80
    daily, _ = cli.build(up, cfg)
    paper = daily["fng10_sell80"].filter(pl.col("mode") == "paper")
    assert paper["n_trades"].to_list() == [1, 1, 1, 1, 0]                                   # three buys, one sale, then nothing to sell
    assert paper["capital"][-1] == 0                                                        # flat after the sale
    gain = 3 * 999 * (66_000 / 60_000) * 0.999 - 3_000                                      # costs on the way in and out
    assert paper["pnl"].sum() == pytest.approx(gain, abs=0.01)


def test_code_fingerprint_is_stable():
    assert cli.code_version() == cli.code_version() and len(cli.code_version()) == 10
