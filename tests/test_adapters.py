import unittest
from pathlib import Path
from unittest.mock import patch

from pia_runtime.adapters import (
    AkshareMarketProvider,
    FixtureMarketProvider,
    ProviderCircuitOpen,
    ProviderHealth,
    ProviderRegistry,
    TushareMarketProvider,
    _board_for_symbol,
    _canonical_symbol,
)
from pia_runtime.normalization import normalize_daily_bar


class AdapterContractTest(unittest.TestCase):
    def test_calendar_dates_are_iso_and_weekday_estimates_are_partial(self):
        class Client:
            def trade_cal(self, **kwargs):
                return [{"cal_date": "20261105", "is_open": 1}]
        tushare = TushareMarketProvider.__new__(TushareMarketProvider)
        tushare.client = Client()
        rows = tushare.get_trading_calendar("2026-11-05", "2026-11-05")
        self.assertEqual(rows[0]["trade_date"], "2026-11-05")
        self.assertEqual(rows[0]["quality"], "verified")
        akshare = AkshareMarketProvider()
        akshare.sdk = object()
        estimate = akshare.get_trading_calendar("2026-11-05", "2026-11-05")[0]
        self.assertEqual(estimate["quality"], "partial")
        self.assertEqual(estimate["source_method"], "weekday_estimate")

    def test_market_data_providers_expose_market_breadth_port(self):
        provider = FixtureMarketProvider(
            Path(__file__).resolve().parent / "fixtures"
        )
        breadth = provider.get_market_breadth("2026-11-05")
        self.assertEqual(breadth["as_of"], "2026-11-05")
        self.assertIn("breadth", breadth)
        self.assertIn("index_trend", breadth)
        self.assertTrue(callable(getattr(AkshareMarketProvider(), "get_market_breadth")))
        self.assertTrue(callable(getattr(TushareMarketProvider(None), "get_market_breadth")))

    def test_fixture_index_series_supports_range_and_symbol_filter(self):
        provider = FixtureMarketProvider(
            Path(__file__).resolve().parent / "fixtures"
        )
        result = provider.get_index_series(
            "2026-11-04",
            "2026-11-05",
            symbols=["000001.SH"],
        )
        self.assertEqual(result["provider"], "fixture")
        self.assertEqual(result["quality"], "verified")
        self.assertEqual([item["symbol"] for item in result["series"]], ["000001.SH"])
        self.assertEqual(result["series"][0]["points"][0]["trade_date"], "2026-11-05")
        self.assertEqual(result["indices"][0]["symbol"], "000001.SH")
        with self.assertRaisesRegex(ValueError, "start_date"):
            provider.get_index_series("2026-11-06", "2026-11-05")

    def test_fixture_paths_cannot_escape_fixture_roots(self):
        provider = FixtureMarketProvider(
            Path(__file__).resolve().parent / "fixtures"
        )
        with self.assertRaisesRegex(ValueError, "escapes fixture directory"):
            provider.get_market_snapshot(
                "2026-11-05",
                "../replay/close-review.json",
            )
        with self.assertRaisesRegex(ValueError, "escapes fixture directory"):
            provider.get_portfolio_snapshot("../market/close-2026-11-05.json")

    def test_bse_new_codes_use_bj_symbol_and_board(self):
        self.assertEqual(_canonical_symbol("920085"), "920085.BJ")
        self.assertEqual(_board_for_symbol("920085"), "bse")

    def test_normalizer_preserves_provenance_and_is_stable(self):
        row = {
            "股票代码": "600000.SH",
            "日期": "2026-11-05",
            "开盘": "12.1",
            "最高": "12.6",
            "最低": "12.0",
            "收盘": "12.44",
            "成交量": "1000",
            "成交额": "12000",
        }
        first = normalize_daily_bar(
            row,
            provider_id="akshare",
            provider_version="fixture-1",
            adapter_version="0.1.0",
            observed_at="2026-11-05T16:10:00+08:00",
        )
        second = normalize_daily_bar(
            row,
            provider_id="akshare",
            provider_version="fixture-1",
            adapter_version="0.1.0",
            observed_at="2026-11-05T16:10:00+08:00",
        )
        self.assertEqual(first["quality"], "verified")
        self.assertEqual(first["snapshot_id"], second["snapshot_id"])
        self.assertEqual(first["provider_id"], "akshare")
        self.assertEqual(first["as_of"], "2026-11-05")

    def test_missing_required_fields_are_unavailable(self):
        result = normalize_daily_bar(
            {"代码": "600000.SH", "日期": "2026-11-05"},
            provider_id="akshare",
        )
        self.assertEqual(result["quality"], "unavailable")
        self.assertIn("close", result["normalization_warnings"])

    def test_provider_registry_prefers_requested_provider_then_fallbacks(self):
        class Provider:
            def __init__(self, provider_id, status):
                self.provider_id = provider_id
                self.status = status

            def health(self):
                return ProviderHealth(
                    provider_id=self.provider_id,
                    status=self.status,
                    capabilities=["market_snapshot"],
                    supports_replay=False,
                    requires_credentials=False,
                )

        chain = ProviderRegistry([
            Provider("fixture", "healthy"),
            Provider("akshare", "capability_disabled"),
            Provider("tushare", "healthy"),
        ]).select_chain(
            "market_snapshot",
            preferred_provider_id="akshare",
        )

        self.assertEqual([provider.provider_id for provider in chain], ["tushare", "fixture"])

    def test_provider_registry_retries_transient_errors_with_backoff(self):
        class Provider:
            provider_id = "flaky"

            def __init__(self):
                self.calls = 0

            def health(self):
                return ProviderHealth(
                    provider_id=self.provider_id,
                    status="healthy",
                    capabilities=["market_snapshot"],
                    supports_replay=False,
                    requires_credentials=False,
                )

            def get_market_snapshot(self, as_of):
                self.calls += 1
                if self.calls < 3:
                    raise TimeoutError("upstream timeout")
                return {"as_of": as_of, "source": self.provider_id}

        delays = []
        provider = Provider()
        registry = ProviderRegistry(
            [provider],
            retry_attempts=3,
            retry_backoff_seconds=0.1,
            sleep=delays.append,
        )
        result = registry.call(provider, "get_market_snapshot", "2026-11-05")

        self.assertEqual(result["source"], "flaky")
        self.assertEqual(provider.calls, 3)
        self.assertEqual(delays, [0.1, 0.2])
        self.assertEqual(registry.health()[0]["runtime"]["retry_count"], 2)

    def test_provider_registry_opens_circuit_after_repeated_failures(self):
        class Provider:
            provider_id = "offline"

            def health(self):
                return ProviderHealth(
                    provider_id=self.provider_id,
                    status="healthy",
                    capabilities=["market_snapshot"],
                    supports_replay=False,
                    requires_credentials=False,
                )

            def get_market_snapshot(self, as_of):
                raise ConnectionError("connection reset")

        provider = Provider()
        registry = ProviderRegistry(
            [provider],
            retry_attempts=1,
            circuit_failure_threshold=2,
            circuit_reset_seconds=60,
            sleep=lambda _: None,
        )
        for _ in range(2):
            with self.assertRaises(ConnectionError):
                registry.call(provider, "get_market_snapshot", "2026-11-05")
        with self.assertRaises(ProviderCircuitOpen):
            registry.call(provider, "get_market_snapshot", "2026-11-05")

        health = registry.health()[0]
        self.assertEqual(health["status"], "circuit_open")
        self.assertEqual(health["runtime"]["failed_calls"], 2)

    def test_akshare_mapping_preserves_live_quality_and_capabilities(self):
        class Frame:
            def __init__(self, rows):
                self.rows = rows

            def to_dict(self, orient="records"):
                return self.rows

        class FakeSdk:
            __version__ = "fake-akshare"

            @staticmethod
            def stock_zh_a_spot_em():
                return Frame([{
                    "代码": "600000",
                    "名称": "浦发银行",
                    "涨跌幅": 1.2,
                    "最新价": 12.4,
                    "成交额": 100000000,
                }])

            @staticmethod
            def stock_board_industry_name_em():
                return Frame([{"板块名称": "银行", "涨跌幅": 0.5}])

            @staticmethod
            def fund_etf_spot_em():
                return Frame([{
                    "代码": "510300",
                    "名称": "沪深300ETF",
                    "最新价": 4.2,
                    "涨跌幅": 0.6,
                    "成交额": 420000000,
                }])

            @staticmethod
            def tool_trade_date_hist_sina():
                return Frame([{"trade_date": "2026-11-06"}])

            @staticmethod
            def stock_financial_analysis_indicator(symbol, start_year):
                return Frame([{"报告期": "2026-09-30", "净资产收益率": 0.12}])

            @staticmethod
            def stock_news_em(symbol):
                return Frame([{"新闻标题": "Update", "发布时间": "2026-11-06", "文章来源": "source"}])

            @staticmethod
            def stock_notice_report(symbol, date):
                return Frame([{"代码": "600000", "公告标题": "Filing", "公告日期": date}])

            @staticmethod
            def stock_info_a_code_name():
                return Frame([{"代码": "600000", "名称": "浦发银行"}])

            @staticmethod
            def stock_info_sh_name_code(symbol):
                return Frame([{
                    "证券代码": "600000",
                    "上市日期": "1999-11-10",
                }])

            @staticmethod
            def stock_info_sz_name_code(symbol):
                return Frame([])

            @staticmethod
            def stock_info_bj_name_code():
                return Frame([])

        provider = AkshareMarketProvider()
        provider.sdk = FakeSdk
        provider._etf_listing_metadata = {}
        snapshot = provider.get_market_snapshot("2026-11-06")

        self.assertEqual(snapshot["source"], "akshare")
        self.assertEqual(snapshot["quality"], "partial")
        self.assertEqual(snapshot["instruments"][0]["symbol"], "600000.SH")
        self.assertEqual(snapshot["instruments"][1]["asset_type"], "etf")
        self.assertEqual(provider.get_trading_calendar("2026-11-06", "2026-11-06")[0]["is_open"], True)
        self.assertEqual(provider.get_fundamentals("600000.SH")["quality"], "verified")
        self.assertEqual(provider.search_news("600000.SH")[0]["quality"], "verified")
        self.assertEqual(len(provider.search_filings("600000.SH", "2026-11-06")), 1)
        self.assertEqual(provider.get_universe()[0]["board"], "main")
        self.assertEqual(provider.get_universe()[0]["exchange"], "SSE")
        self.assertEqual(provider.get_universe()[0]["listed_at"], "1999-11-10")
        self.assertEqual(provider.get_universe()[1]["asset_type"], "etf")

    def test_akshare_company_profile_uses_provider_metadata(self):
        class Frame:
            def __init__(self, rows):
                self.rows = rows

            def to_dict(self, orient="records"):
                return self.rows

        class FakeSdk:
            __version__ = "fake-akshare"

            @staticmethod
            def stock_profile_cninfo(symbol):
                return Frame([{
                    "公司名称": "上海浦东发展银行股份有限公司",
                    "A股简称": "浦发银行",
                    "所属市场": "上交所",
                    "所属行业": "货币金融服务",
                    "上市日期": "1999-11-10",
                }])

        provider = AkshareMarketProvider()
        provider.sdk = FakeSdk
        profile = provider.get_company_profile("600000.SH", as_of="2026-11-05")

        self.assertEqual(profile["name"], "浦发银行")
        self.assertEqual(profile["industry"], "货币金融服务")
        self.assertEqual(profile["listed_at"], "1999-11-10")
        self.assertEqual(profile["source"], "akshare")
        self.assertEqual(profile["quality"], "verified")

    def test_tushare_company_profile_uses_stock_basic_metadata(self):
        class FakeClient:
            def stock_basic(self, **kwargs):
                self.kwargs = kwargs
                return [{
                    "ts_code": "600000.SH",
                    "name": "浦发银行",
                    "exchange": "SSE",
                    "industry": "银行",
                    "list_date": "19991110",
                }]

        provider = TushareMarketProvider("token")
        provider.sdk = object()
        provider.client = FakeClient()
        profile = provider.get_company_profile("600000.SH", as_of="2026-11-05")

        self.assertEqual(profile["name"], "浦发银行")
        self.assertEqual(profile["industry"], "银行")
        self.assertEqual(profile["listed_at"], "1999-11-10")
        self.assertEqual(profile["source"], "tushare")
        self.assertEqual(profile["quality"], "verified")

    def test_akshare_etf_listing_dates_merge_exchange_sources(self):
        class Frame:
            def __init__(self, rows):
                self.rows = rows

            def to_dict(self, orient="records"):
                return self.rows

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return (
                    '{"pageHelp":{"data":[{"FUND_CODE":"510300",'
                    '"LISTING_DATE":"2012-05-28"}]}}'
                ).encode()

        class FakeSdk:
            __version__ = "fake-akshare"

            @staticmethod
            def stock_zh_a_spot_em():
                return Frame([])

            @staticmethod
            def stock_info_a_code_name():
                return Frame([])

            @staticmethod
            def fund_etf_spot_em():
                return Frame([
                    {"代码": "510300", "名称": "沪深300ETF", "最新价": 4.2},
                    {"代码": "159001", "名称": "深证ETF", "最新价": 1.1},
                ])

            @staticmethod
            def fund_etf_scale_szse():
                return Frame([{
                    "基金代码": "159001",
                    "上市日期": "2013-01-09",
                }])

        provider = AkshareMarketProvider()
        provider.sdk = FakeSdk
        with patch(
            "pia_runtime.adapters.urllib.request.urlopen",
            return_value=FakeResponse(),
        ):
            rows = provider.get_universe()

        by_symbol = {row["symbol"]: row for row in rows}
        self.assertEqual(by_symbol["510300.SH"]["listed_at"], "2012-05-28")
        self.assertEqual(by_symbol["510300.SH"]["exchange"], "SSE")
        self.assertEqual(by_symbol["159001.SZ"]["listed_at"], "2013-01-09")
        self.assertEqual(by_symbol["159001.SZ"]["exchange"], "SZSE")

    def test_fundamentals_choose_latest_report_period(self):
        class Frame:
            def to_dict(self, orient="records"):
                return [
                    {"报告期": "2024-12-31", "净资产收益率(%)": 8.0},
                    {"报告期": "2026-09-30", "净资产收益率(%)": 12.0},
                ]

        class FakeSdk:
            __version__ = "fake-akshare"

            @staticmethod
            def stock_financial_analysis_indicator(symbol, start_year):
                return Frame()

        provider = AkshareMarketProvider()
        provider.sdk = FakeSdk
        result = provider.get_fundamentals("600000.SH")
        self.assertEqual(result["as_of"], "2026-09-30")
        self.assertEqual(result["metrics"]["净资产收益率(%)"], 12.0)

    def test_live_snapshot_maps_indices_and_computes_volatility(self):
        class Frame:
            def __init__(self, rows):
                self.rows = rows

            def to_dict(self, orient="records"):
                return self.rows

        class FakeSdk:
            __version__ = "fake-akshare"

            @staticmethod
            def stock_zh_a_spot_em():
                return Frame([
                    {"代码": "600000", "名称": "浦发银行", "涨跌幅": 1.2, "最新价": 12.4, "成交额": 100000000},
                    {"代码": "000001", "名称": "平安银行", "涨跌幅": -0.8, "最新价": 10.1, "成交额": 90000000},
                ])

            @staticmethod
            def stock_board_industry_name_em():
                return Frame([])

            @staticmethod
            def stock_zh_index_spot_em(symbol="沪深重要指数"):
                return Frame([{"代码": "000001", "名称": "上证指数", "最新价": 3000, "涨跌幅": 0.5}])

            @staticmethod
            def tool_trade_date_hist_sina():
                return Frame([{"trade_date": "2026-11-06"}])

        provider = AkshareMarketProvider()
        provider.sdk = FakeSdk
        provider._etf_listing_metadata = {}
        snapshot = provider.get_market_snapshot("2026-11-06")
        self.assertEqual(snapshot["indices"][0]["symbol"], "000001.SH")
        self.assertGreater(snapshot["volatility"], 0)
        self.assertEqual(snapshot["point_in_time_scope"], "latest")

    def test_akshare_index_series_preserves_date_range_and_provenance(self):
        class Frame:
            def to_dict(self, orient="records"):
                return [
                    {"date": "2026-11-04", "open": 2990, "high": 3010, "low": 2980, "close": 3000, "volume": 10},
                    {"date": "2026-11-05", "open": 3000, "high": 3040, "low": 2995, "close": 3030, "volume": 12},
                ]

        class FakeSdk:
            __version__ = "fake-akshare"

            @staticmethod
            def stock_zh_index_daily_em(symbol, start_date, end_date):
                return Frame()

        provider = AkshareMarketProvider()
        provider.sdk = FakeSdk
        result = provider.get_index_series(
            "2026-11-04",
            "2026-11-05",
            symbols=["000001.SH"],
        )
        self.assertEqual(result["source"], "akshare")
        self.assertEqual(result["quality"], "verified")
        self.assertEqual(result["series"][0]["points"][1]["trade_date"], "2026-11-05")
        self.assertEqual(result["series"][0]["points"][1]["source"], "akshare")

    def test_historical_snapshot_uses_date_scoped_bars(self):
        class Frame:
            def __init__(self, rows):
                self.rows = rows

            def to_dict(self, orient="records"):
                return self.rows

        class FakeSdk:
            __version__ = "fake-akshare"

            @staticmethod
            def stock_zh_a_hist(symbol, period, start_date, end_date, adjust):
                return Frame([
                    {
                        "日期": "2026-11-04",
                        "开盘": 10.0,
                        "最高": 10.5,
                        "最低": 9.8,
                        "收盘": 10.0,
                        "成交量": 1000,
                        "成交额": 10000,
                        "涨跌幅": -1.0,
                    },
                    {
                        "日期": "2026-11-05",
                        "开盘": 10.0,
                        "最高": 10.8,
                        "最低": 9.9,
                        "收盘": 10.4,
                        "成交量": 1200,
                        "成交额": 12000,
                        "涨跌幅": 4.0,
                    },
                ])

            @staticmethod
            def fund_etf_hist_em(symbol, period, start_date, end_date, adjust):
                return Frame([
                    {
                        "日期": "2026-11-05",
                        "开盘": 4.0,
                        "最高": 4.2,
                        "最低": 3.9,
                        "收盘": 4.1,
                        "成交量": 2200,
                        "成交额": 22000,
                        "涨跌幅": 2.5,
                    },
                ])

            @staticmethod
            def stock_zh_index_daily_em(symbol, start_date, end_date):
                return Frame([
                    {"date": "2026-11-04", "close": 3000.0},
                    {"date": "2026-11-05", "close": 3030.0},
                ])

            @staticmethod
            def stock_board_industry_name_em():
                return Frame([{"板块名称": "银行"}])

            @staticmethod
            def stock_board_industry_hist_em(
                symbol, start_date, end_date, period, adjust
            ):
                return Frame([{"日期": "2026-11-05", "涨跌幅": 1.2}])

        provider = AkshareMarketProvider()
        provider.sdk = FakeSdk
        provider.get_universe = lambda: [
            {
                "symbol": "600000.SH",
                "name": "浦发银行",
                "asset_type": "stock",
                "board": "main",
                "exchange": "SSE",
                "listed_at": "1999-11-10",
                "active": True,
            },
            {
                "symbol": "000001.SZ",
                "name": "平安银行",
                "asset_type": "stock",
                "board": "main",
                "exchange": "SZSE",
                "listed_at": "1991-04-03",
                "active": True,
            },
            {
                "symbol": "510300.SH",
                "name": "沪深300ETF",
                "asset_type": "etf",
                "board": "etf",
                "exchange": "SSE",
                "listed_at": "2012-05-28",
                "active": True,
            },
        ]

        snapshot = provider.get_market_snapshot("2026-11-05")

        self.assertEqual(snapshot["point_in_time_scope"], "historical")
        self.assertEqual(snapshot["quality"], "verified")
        self.assertEqual(snapshot["as_of"], "2026-11-05")
        self.assertEqual(snapshot["historical_coverage"]["ratio"], 1.0)
        self.assertEqual(
            {row["symbol"] for row in snapshot["instruments"]},
            {"600000.SH", "000001.SZ", "510300.SH"},
        )
        self.assertEqual(
            next(
                row["close"]
                for row in snapshot["instruments"]
                if row["symbol"] == "600000.SH"
            ),
            10.4,
        )
        self.assertEqual(snapshot["indices"][0]["change_pct"], 1.0)

    def test_akshare_etf_daily_bars_use_etf_history_endpoint(self):
        class Frame:
            def to_dict(self, orient="records"):
                return [{
                    "日期": "2026-11-05",
                    "开盘": 4.0,
                    "最高": 4.2,
                    "最低": 3.9,
                    "收盘": 4.1,
                    "成交量": 2200,
                    "成交额": 22000,
                }]

        class FakeSdk:
            __version__ = "fake-akshare"

            @staticmethod
            def fund_etf_hist_em(**kwargs):
                self_kwargs.update(kwargs)
                return Frame()

        self_kwargs = {}
        provider = AkshareMarketProvider()
        provider.sdk = FakeSdk
        rows = provider.get_daily_bars(
            "510300.SH",
            "2026-11-05",
            "2026-11-05",
        )

        self.assertEqual(self_kwargs["symbol"], "510300")
        self.assertEqual(rows[0]["symbol"], "510300.SH")
        self.assertEqual(rows[0]["quality"], "verified")

    def test_tushare_etf_daily_bars_use_fund_daily(self):
        class Frame:
            def to_dict(self, orient="records"):
                return [{
                    "ts_code": "510300.SH",
                    "trade_date": "20261105",
                    "open": 4.0,
                    "high": 4.2,
                    "low": 3.9,
                    "close": 4.1,
                    "vol": 2200,
                    "amount": 22000,
                }]

        class FakeClient:
            def fund_daily(self, **kwargs):
                self.kwargs = kwargs
                return Frame()

        provider = TushareMarketProvider("token")
        provider.sdk = type("FakeSdk", (), {"__version__": "fake-tushare"})
        provider.client = FakeClient()
        rows = provider.get_daily_bars(
            "510300.SH",
            "2026-11-05",
            "2026-11-05",
        )

        self.assertEqual(provider.client.kwargs["ts_code"], "510300.SH")
        self.assertEqual(rows[0]["symbol"], "510300.SH")
        self.assertEqual(rows[0]["quality"], "verified")

    def test_tushare_universe_includes_etfs_and_preserves_provenance(self):
        class Frame:
            def __init__(self, rows):
                self.rows = rows

            def to_dict(self, orient="records"):
                return self.rows

        class FakeClient:
            def stock_basic(self, **kwargs):
                return Frame([{
                    "ts_code": "600000.SH",
                    "symbol": "600000",
                    "name": "浦发银行",
                    "list_date": "1999-11-10",
                }])

            def fund_basic(self, **kwargs):
                return Frame([{
                    "ts_code": "510300.SH",
                    "name": "沪深300ETF",
                    "listing_date": "2012-05-28",
                }])

        provider = TushareMarketProvider("token")
        provider.sdk = type("FakeSdk", (), {"__version__": "fake-tushare"})
        provider.client = FakeClient()

        universe = provider.get_universe()

        self.assertEqual([row["asset_type"] for row in universe], ["stock", "etf"])
        self.assertEqual(universe[1]["board"], "etf")
        self.assertEqual(universe[0]["symbol"], "600000.SH")
        self.assertEqual(universe[0]["exchange"], "SSE")
        self.assertEqual(universe[0]["listed_at"], "1999-11-10")
        self.assertEqual(universe[1]["listed_at"], "2012-05-28")

    def test_tushare_snapshot_maps_indices_and_sectors(self):
        class Frame:
            def __init__(self, rows):
                self.rows = rows

            def to_dict(self, orient="records"):
                return self.rows

        class FakeClient:
            def stock_basic(self, **kwargs):
                return Frame([{
                    "ts_code": "600000.SH",
                    "symbol": "600000",
                    "name": "浦发银行",
                    "list_date": "1999-11-10",
                }])

            def daily_basic(self, **kwargs):
                return Frame([
                    {"ts_code": "600000.SH", "close": 12.4, "pct_chg": 1.2, "amount": 100000},
                    {"ts_code": "000001.SZ", "close": 10.1, "pct_chg": -0.8, "amount": 90000},
                ])

            def fund_daily(self, **kwargs):
                return Frame([
                    {"ts_code": "510300.SH", "close": 4.2, "pct_chg": 0.6, "amount": 420000},
                ])

            def index_daily(self, **kwargs):
                return Frame([{
                    "ts_code": kwargs["ts_code"],
                    "trade_date": kwargs["trade_date"],
                    "close": 3000,
                    "pct_chg": 0.5,
                }])

            def sw_daily(self, **kwargs):
                return Frame([{
                    "ts_code": "801010.SI",
                    "name": "农林牧渔",
                    "pct_chg": 0.4,
                }])

        provider = TushareMarketProvider("token")
        provider.sdk = type("FakeSdk", (), {"__version__": "fake-tushare"})
        provider.client = FakeClient()

        snapshot = provider.get_market_snapshot("2026-11-06")

        self.assertEqual(snapshot["source"], "tushare")
        self.assertEqual(len(snapshot["indices"]), 5)
        self.assertEqual(snapshot["indices"][0]["symbol"], "000001.SH")
        self.assertEqual(snapshot["sectors"][0]["name"], "农林牧渔")
        self.assertEqual(snapshot["quality"], "verified")
        stock = next(item for item in snapshot["instruments"] if item["symbol"] == "600000.SH")
        self.assertEqual(stock["name"], "浦发银行")
        self.assertGreater(stock["listed_days"], 9000)
        self.assertTrue(any(item["asset_type"] == "etf" for item in snapshot["instruments"]))

    def test_akshare_snapshot_keeps_full_instrument_universe(self):
        class Frame:
            def __init__(self, rows):
                self.rows = rows

            def to_dict(self, orient="records"):
                return self.rows

        class FakeSdk:
            __version__ = "fake-akshare"

            @staticmethod
            def stock_zh_a_spot_em():
                return Frame([
                    {
                        "代码": f"{600000 + index:06d}",
                        "名称": f"Instrument {index}",
                        "涨跌幅": 0.1,
                        "最新价": 10.0,
                        "成交额": 1000000,
                    }
                    for index in range(2001)
                ])

            @staticmethod
            def stock_board_industry_name_em():
                return Frame([])

            @staticmethod
            def stock_zh_index_spot_em(symbol="沪深重要指数"):
                return Frame([{"代码": "000001", "名称": "上证指数", "最新价": 3000, "涨跌幅": 0.5}])

        provider = AkshareMarketProvider()
        provider.sdk = FakeSdk
        provider._etf_listing_metadata = {}
        snapshot = provider.get_market_snapshot("2026-11-06")

        self.assertEqual(len(snapshot["instruments"]), 2001)

    def test_tushare_news_requests_symbol_scoped_rows(self):
        class Frame:
            def to_dict(self, orient="records"):
                return [{
                    "ts_code": "600000.SH",
                    "title": "Quarterly update",
                    "datetime": "2026-11-06 10:00:00",
                    "source": "sina",
                    "content": "Update",
                }]

        class FakeClient:
            def news(self, **kwargs):
                self.kwargs = kwargs
                return Frame()

        provider = TushareMarketProvider("token")
        provider.sdk = type("FakeSdk", (), {"__version__": "fake-tushare"})
        provider.client = FakeClient()

        rows = provider.search_news("600000.SH")

        self.assertEqual(rows[0]["quality"], "verified")
        self.assertTrue(rows[0]["symbol_verified"])
        self.assertEqual(provider.client.kwargs["ts_code"], "600000.SH")

    def test_tushare_news_filters_future_rows_without_symbol_codes(self):
        class Frame:
            def to_dict(self, orient="records"):
                return [
                    {
                        "title": "Future update",
                        "datetime": "2026-11-06 10:00:00",
                        "source": "sina",
                        "content": "Future",
                    },
                    {
                        "title": "Historical update",
                        "datetime": "2026-11-04 10:00:00",
                        "source": "sina",
                        "content": "Historical",
                    },
                ]

        class FakeClient:
            def news(self, **kwargs):
                return Frame()

        provider = TushareMarketProvider("token")
        provider.sdk = type("FakeSdk", (), {"__version__": "fake-tushare"})
        provider.client = FakeClient()

        rows = provider.search_news("600000.SH", as_of="2026-11-05")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Historical update")
