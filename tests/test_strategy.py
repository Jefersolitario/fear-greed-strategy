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
CMC = pl.read_csv(ROOT / "data" / "cmc_snapshot.csv", schema_overrides=data.CMC_SCHEMA)      # the frozen file only, so later live days cannot move a test


@pytest.fixture(scope="module")
def built():
    cfg = cli.load_config(ROOT / "strategies.toml")
    inputs = data.load_inputs(ROOT / "data").filter(pl.col("date") <= SNAPSHOT_END)
    daily, summary = cli.build(inputs, cfg, CMC)
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
    assert set(daily) == {"cmc_le10_sell80", "fng_le10_sell80", "fng_le15_sell80"}    # one in the portfolio, two monitored
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
    first, _ = cli.build(inputs, cfg, CMC)
    for sid, t in first.items():
        contract.publish_strategy(out, _manifest(sid), t)

    # ten more days with the index at 5 and a flat price: paper buys from paper_start only
    longer = _extend(inputs, 10, fng=5, close=60_000.0)
    second, _ = cli.build(longer, cfg, CMC)
    t = second["fng_le10_sell80"]
    paper = t.filter(pl.col("mode") == "paper")
    assert paper["date"].min() == cfg["paper_start"]
    n_paper_days = (longer["date"].max() - cfg["paper_start"]).days + 1
    assert paper["n_trades"].sum() == n_paper_days
    assert paper["pnl"][0] == pytest.approx(-1.0, abs=1e-6)          # first fill costs 10 bps of 1,000 USD
    for sid, tab in second.items():
        contract.publish_strategy(out, _manifest(sid), tab)           # only adds days: allowed

    # rewriting a published day is refused
    tampered = second["fng_le10_sell80"].with_columns(pl.when(pl.col("date") == cfg["paper_start"]).then(pl.col("pnl") + 50).otherwise(pl.col("pnl")).alias("pnl"))
    with pytest.raises(RuntimeError, match="would change"):
        contract.publish_strategy(out, _manifest("fng_le10_sell80"), tampered)


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
    """Stands in for the live APIs."""

    def __init__(self, fng: dict, closes: dict, cmc: dict | None = None):
        self.fng, self.closes, self.cmc, self.cmc_calls = fng, closes, cmc or {}, []

    def get(self, url, **kw):
        ts = lambda d: int(dt.datetime.combine(d, dt.time(), dt.timezone.utc).timestamp())
        if "alternative.me" in url:
            return _Resp({"data": [{"value": str(v), "timestamp": str(ts(d))} for d, v in self.fng.items()]})
        if "coinmarketcap" in url:                    # shaped like the real answer: newest first, the time as unix seconds in text
            self.cmc_calls.append((url, dict(kw.get("headers") or {})))
            return _Resp({"data": [{"timestamp": str(ts(d)), "value": v, "value_classification": "Extreme fear"} for d, v in sorted(self.cmc.items(), reverse=True)],
                          "status": {"error_code": "0"}})
        return _Resp([[ts(d), 0, 0, 0, c, 0] for d, c in self.closes.items()])


def _data_dir(tmp_path, cmc_through: dt.date) -> pathlib.Path:
    """A data folder holding the frozen inputs (to SNAPSHOT_END) and CoinMarketCap's values up to `cmc_through`."""
    d = tmp_path / "data"
    d.mkdir()
    (d / "inputs_snapshot.csv").write_bytes((ROOT / "data" / "inputs_snapshot.csv").read_bytes())
    CMC.filter(pl.col("date") <= cmc_through).write_csv(d / "cmc_snapshot.csv")
    return d


def test_live_update_appends_only_complete_days_and_refuses_restated_inputs(tmp_path):
    day = lambda k: SNAPSHOT_END + dt.timedelta(days=k)
    d = _data_dir(tmp_path, day(0))
    stored = data.load_inputs(d).filter(pl.col("date") > day(-6))
    fng = {r["date"]: r["fng"] for r in stored.iter_rows(named=True)} | {day(1): 12, day(2): 9, day(3): 30}
    closes = {r["date"]: r["close"] * 1.001 for r in stored.iter_rows(named=True)} | {day(1): 63_000.0, day(2): 61_500.0, day(3): 64_000.0}
    cmc = {day(-1): 18, day(0): 14, day(1): 13, day(2): 11, day(3): 9}

    out = data.update_live(d, today_utc=day(3), session=_Session(fng, closes, cmc))  # day(3) is still open
    assert out["date"].max() == day(2)
    assert out.filter(pl.col("date") == day(2))["fng"][0] == 9
    again = data.update_live(d, today_utc=day(3), session=_Session(fng, closes, cmc))     # idempotent
    assert again.height == out.height

    closes_bad = dict(closes) | {day(2): 61_500.0 * 1.05}
    with pytest.raises(RuntimeError, match="is stored as"):
        data.update_live(d, today_utc=day(4), session=_Session(fng, closes_bad, cmc))


def test_coinmarketcap_values_are_stored_a_day_behind_and_a_day_waits_for_them(tmp_path, monkeypatch):
    day = lambda k: SNAPSHOT_END + dt.timedelta(days=k)
    d = _data_dir(tmp_path, day(0))
    stored = data.load_inputs(d).filter(pl.col("date") > day(-6))
    fng = {r["date"]: r["fng"] for r in stored.iter_rows(named=True)} | {day(k): 12 for k in range(1, 7)}
    closes = {r["date"]: r["close"] for r in stored.iter_rows(named=True)} | {day(k): 63_000.0 for k in range(1, 7)}
    monkeypatch.delenv("CMC_API_KEY", raising=False)

    # two complete days, but CoinMarketCap has nothing for day(1) yet: day(1) is appended (it needs day(0), on file), day(2) waits
    s = _Session(fng, closes, {day(-1): 18, day(0): 14})
    assert data.update_live(d, today_utc=day(3), session=s)["date"].max() == day(1)
    assert data.load_cmc(d)["date"].max() == day(0) and not (d / "cmc_live.csv").exists()
    assert "public-api" in s.cmc_calls[0][0] and "X-CMC_PRO_API_KEY" not in s.cmc_calls[0][1]          # keyless by default
    # the value turns up: the waiting day goes in, and the value it was decided on is put on file with it. Newer ones are not yet.
    monkeypatch.setenv("CMC_API_KEY", "k")
    s = _Session(fng, closes, {day(0): 14, day(1): 13, day(2): 11, day(3): 9})
    assert data.update_live(d, today_utc=day(3), session=s)["date"].max() == day(2)
    assert data.load_cmc(d).filter(pl.col("date") > day(0)).rows() == [(day(1), 13)]
    assert "public-api" not in s.cmc_calls[0][0] and s.cmc_calls[0][1]["X-CMC_PRO_API_KEY"] == "k"     # a key is used when there is one
    # a stored value that the API later reports differently stops the run
    with pytest.raises(RuntimeError, match=f"CoinMarketCap's index for {day(1)} is stored as 13 but the API now says 15"):
        data.update_live(d, today_utc=day(4), session=_Session(fng, closes, {day(1): 15, day(2): 11, day(3): 9}))
    # waiting is fine for a day or two; after three complete days without progress the run fails and says what is missing
    quiet = _Session(fng, closes, {day(1): 13})
    assert data.update_live(d, today_utc=day(5), session=quiet)["date"].max() == day(2)
    with pytest.raises(RuntimeError, match=f"no day has been appended since {day(2)}: CoinMarketCap's index for the day before is missing"):
        data.update_live(d, today_utc=day(6), session=quiet)
    assert data._cmc_day("1795132800") == dt.date(2026, 11, 20) == data._cmc_day("2026-11-20T00:00:00.000Z")


def test_coinmarketcap_rule_trades_on_the_value_of_the_day_before(built):
    cfg, inputs, daily, summary = built
    rule = next(r for r in cfg["rules"] if r["id"] == "cmc_le10_sell80")
    assert rule["role"] == "portfolio" and rule["backtest_start"] == dt.date(2023, 6, 30) and rule["paper_start"] == dt.date(2026, 11, 21)
    t = daily["cmc_le10_sell80"]
    value = dict(CMC.rows())
    buys = t.filter((pl.col("n_trades") > 0) & (pl.col("capital") > 0))["date"].to_list()
    assert buys and all(value[b - dt.timedelta(days=1)] <= 10 for b in buys)                 # every buy follows a day at 10 or lower
    assert sum(value[b] > 10 for b in buys) >= 2                                              # and some fall on a day that is itself above 10
    assert t["date"].min() == dt.date(2025, 11, 23)                                           # 22 Nov 2025 was the first day at 10; bought the day after
    row = summary["cmc_le10_sell80"]                                                          # to 14 Nov 2026: the research run on the same data
    assert (row["buys"], row["start"]) == (10, dt.date(2025, 11, 23)) and row["pnl"] == pytest.approx(900, abs=1)
    sold = t.filter((pl.col("n_trades") > 0) & (pl.col("capital") == 0))["date"].to_list()
    assert sold == [dt.date(2026, 8, 25)] and value[dt.date(2026, 8, 24)] >= 80
    assert cli.build(inputs, cfg)[0]["cmc_le10_sell80"].height == 0                           # without the values the rule never trades


def test_a_rule_added_later_cannot_get_paper_days_that_were_already_published(built, tmp_path):
    cfg, inputs, _, _ = built
    out = str(tmp_path / "results")
    longer = _extend(inputs, 9, fng=5, close=60_000.0)                                        # to 23 Nov; CoinMarketCap's values end on 20 Nov
    daily, _ = cli.build(longer, cfg, CMC)
    new = daily["cmc_le10_sell80"]
    paper = new.filter(pl.col("mode") == "paper")
    assert paper["date"].to_list() == [dt.date(2026, 11, 21), dt.date(2026, 11, 22), dt.date(2026, 11, 23)] and paper["n_trades"].to_list() == [1, 0, 0]
    assert new.filter(pl.col("date") == dt.date(2026, 11, 20))["mode"][0] == "backtest"       # the day before its paper start is not a paper day
    # the rule reaches the results while they stand at 20 Nov: its first paper day is still to come
    contract.publish_strategy(out, _manifest("cmc_le10_sell80"), new.filter(pl.col("date") <= dt.date(2026, 11, 20)), through=dt.date(2026, 11, 20))
    contract.publish_strategy(out, _manifest("cmc_le10_sell80"), new.filter(pl.col("date") <= dt.date(2026, 11, 21)), through=dt.date(2026, 11, 20))
    contract.publish_strategy(out, _manifest("cmc_le10_sell80"), new, through=dt.date(2026, 11, 21))      # a run that catches up two days
    # the same rule arriving after 22 Nov was already published is refused, and told what to do
    late = str(tmp_path / "late")
    with pytest.raises(RuntimeError, match="cmc_le10_sell80: paper days from 2026-11-21 to 2026-11-22 would be added .* set its paper_start to 2026-11-23 or later"):
        contract.publish_strategy(late, _manifest("cmc_le10_sell80"), new, through=dt.date(2026, 11, 22))
    contract.publish_strategy(late, _manifest("cmc_le10_sell80"), new, through=dt.date(2026, 11, 22), allow_restate=True)
    assert contract.published_through(late) is None
    contract.publish_index(late, "test", ["cmc_le10_sell80"], pl.DataFrame({"strategy_id": ["x"]}), "now", "2026-11-23")
    assert contract.published_through(late) == dt.date(2026, 11, 23)


def test_sell_at_80_paper_book_sells_everything_and_goes_flat(built):
    cfg, inputs, _, _ = built
    up = _extend(_extend(inputs, 6, fng=5, close=60_000.0), 2, fng=85, close=66_000.0)     # 3 paper buys, then the index hits 80
    daily, _ = cli.build(up, cfg)
    paper = daily["fng_le10_sell80"].filter(pl.col("mode") == "paper")
    assert paper["n_trades"].to_list() == [1, 1, 1, 1, 0]                                   # three buys, one sale, then nothing to sell
    assert paper["capital"][-1] == 0                                                        # flat after the sale
    gain = 3 * 999 * (66_000 / 60_000) * 0.999 - 3_000                                      # costs on the way in and out
    assert paper["pnl"].sum() == pytest.approx(gain, abs=0.01)


def test_code_fingerprint_is_stable():
    assert cli.code_version() == cli.code_version() and len(cli.code_version()) == 10


def test_dropping_a_strategy_removes_its_files_but_never_a_paper_record(built, tmp_path):
    cfg, inputs, daily, _ = built
    out = str(tmp_path / "results")
    t = daily["fng_le10_sell80"]
    for sid in ("old_rule", "fng_le10_sell80"):
        contract.publish_strategy(out, _manifest(sid), t)
    contract.publish_index(out, "test", ["old_rule", "fng_le10_sell80"], pl.DataFrame({"strategy_id": ["x"]}), "now", "2026-11-14")
    assert contract.prune_removed(out, ["fng_le10_sell80"]) == ["old_rule"]
    assert not (tmp_path / "results" / "old_rule").exists() and (tmp_path / "results" / "fng_le10_sell80" / "daily.parquet").exists()

    live = t.with_columns(pl.when(pl.col("date") == t["date"].max()).then(pl.lit("paper")).otherwise(pl.col("mode")).alias("mode"))
    contract.publish_strategy(out, _manifest("old_rule"), live)
    contract.publish_index(out, "test", ["old_rule", "fng_le10_sell80"], pl.DataFrame({"strategy_id": ["x"]}), "now", "2026-11-14")
    with pytest.raises(RuntimeError, match="paper or live days"):
        contract.prune_removed(out, ["fng_le10_sell80"])


def test_an_index_of_exactly_10_buys_only_under_the_inclusive_rule(built):
    cfg, inputs, _, summary = built
    from fng.engine import buy_mask
    rules = {r["id"]: r["rule"] for r in cfg["rules"]}
    fng = inputs["fng"].cast(pl.Float64).to_numpy()
    close = inputs["close"].to_numpy().astype(float)
    strict, incl = buy_mask(fng, close, rules["fng10_sell80"]), buy_mask(fng, close, rules["fng_le10_sell80"])
    at_10 = fng == 10
    assert at_10.sum() > 0 and incl[at_10].all() and not strict[at_10].any()
    assert (incl & ~at_10 == strict).all()                    # the two rules differ on those days and nowhere else
    row = summary["fng_le10_sell80"]                          # audit sensitivity run: 69 buys, about +$41.6K
    assert row["buys"] == 69
    assert row["pnl"] == pytest.approx(41_600, abs=150)


def test_monitoring_rule_is_published_with_its_role(built):
    cfg, _, daily, summary = built
    roles = {r["id"]: r["role"] for r in cfg["rules"]}
    assert roles["cmc_le10_sell80"] == "portfolio" and roles["fng_le10_sell80"] == "monitor"       # since 21 Nov 2026
    assert roles["fng_le15_sell80"] == "monitor" and roles["fng20_hold"] == "tested"
    assert summary["fng_le15_sell80"]["role"] == "monitor"
    assert summary["fng_le15_sell80"]["buys"] == 244
    assert summary["fng_le15_sell80"]["pnl"] == pytest.approx(153_811, abs=25)


def test_the_job_end_to_end_over_the_first_two_days_of_the_coinmarketcap_rule(tmp_path, monkeypatch):
    """The command the workflow runs, for 21 and 22 Nov 2026, with stand-ins for the sources and the clock."""
    import json
    monkeypatch.delenv("CMC_API_KEY", raising=False)
    d, out = tmp_path / "data", tmp_path / "results"
    d.mkdir()
    start = data.load_inputs(ROOT / "data").filter(pl.col("date") <= dt.date(2026, 11, 20))      # the state the rule was merged into
    start.write_csv(d / "inputs_snapshot.csv")
    CMC.write_csv(d / "cmc_snapshot.csv")
    day = lambda n: dt.date(2026, 11, n)
    run = ["run", "--data", str(d), "--out", str(out)]
    paper = lambda sid: pl.read_parquet(out / sid / "daily.parquet").filter(pl.col("mode") == "paper")
    assert cli.main(run) == 0 and paper("cmc_le10_sell80").height == 0
    roles = {s: json.loads((out / s / "manifest.json").read_text())["role"] for s in json.loads((out / "index.json").read_text())["strategies"]}
    assert roles == {"cmc_le10_sell80": "portfolio", "fng_le10_sell80": "monitor", "fng_le15_sell80": "monitor"}
    assert json.loads((out / "cmc_le10_sell80" / "manifest.json").read_text())["paper_start"] == "2026-11-21"

    tail = start.filter(pl.col("date") >= day(15))
    fng = {r["date"]: r["fng"] for r in tail.iter_rows(named=True)} | {day(21): 12, day(22): 9}
    closes = {r["date"]: r["close"] for r in tail.iter_rows(named=True)} | {day(21): 57_000.0, day(22): 58_140.0}
    cmc = {day(19): 10, day(20): 8, day(21): 7, day(22): 6}

    # 21 Nov: CoinMarketCap's value of the 20th was 8, so its rule buys; Alternative.me's value of the 21st is 12, so that rule does not
    assert cli.main([*run, "--fetch"], session=_Session(fng, closes, cmc), today_utc=day(22)) == 0
    first = paper("cmc_le10_sell80")
    assert first.rows() == [(day(21), "paper", pytest.approx(-1.0), pytest.approx(999.0), 1)]
    assert paper("fng_le10_sell80").filter(pl.col("date") == day(21))["n_trades"].to_list() == [0]
    assert not (d / "cmc_live.csv").exists()                                                      # the value it used was already on file
    # 22 Nov: the value of the 21st was 7, another buy; that value is now put on file
    assert cli.main([*run, "--fetch"], session=_Session(fng, closes, cmc), today_utc=day(23)) == 0
    two = paper("cmc_le10_sell80")
    assert two["n_trades"].to_list() == [1, 1] and two["pnl"][1] == pytest.approx(999 * (58_140 / 57_000 - 1) - 1, abs=0.01)
    assert paper("fng_le10_sell80").filter(pl.col("date") == day(22))["n_trades"].to_list() == [1]    # Alternative.me's 9 buys too
    assert data.load_cmc(d).filter(pl.col("date") > day(20)).rows() == [(day(21), 7)]
    assert cli.main([*run, "--fetch"], session=_Session(fng, closes, cmc), today_utc=day(23)) == 0     # a repeated run changes nothing
    assert paper("cmc_le10_sell80").equals(two)

    # a rule that reaches the configuration after those two days were published cannot claim them as paper days
    config = tmp_path / "strategies.toml"
    config.write_text((ROOT / "strategies.toml").read_text() + '\n[[strategy]]\nid = "cmc_le15_sell80"\nname = "x"\nindex = "cmc"\nthreshold = 15\ninclusive = true\n'
                      'sell_all_at = 80\npaper = true\nbacktest_start = "2023-06-30"\npaper_start = "2026-11-21"\n')
    with pytest.raises(RuntimeError, match="cmc_le15_sell80: paper days from 2026-11-21 to 2026-11-22 would be added .* set its paper_start to 2026-11-23 or later"):
        cli.main([*run, "--config", str(config)])
