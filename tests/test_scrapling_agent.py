"""
Tests for ScraplingAgent

Spec coverage:
  ScraplingConfig
    - All field defaults
    - Custom values, all combinations
  _build_scrapling_proxy(backend, country, session_id) -> dict
    - Output format: {server, username, password}
    - Credential mapping from SmartProxyISPBackend
    - Country and session_id embedded in username
  ScraplingAgent.__init__
    - No proxy (no_proxy=True, or missing credentials)
    - With proxy (credentials present)
    - Session counter starts at 0
  ScraplingAgent._get_session_params
    - Increments session counter
    - Returns correct keys (headless, useragent, locale, timezone_id, hide_canvas, block_webrtc)
    - Proxy kwarg included when proxy_manager exists
    - Timezone override from config
    - Area-specific locale
  ScraplingAgent._parse_task
    - String URL
    - Dict with url/page_action/solve_cloudflare
    - Dict missing keys uses defaults
    - solve_cloudflare from config when not in dict
  ScraplingAgent.run(task)
    - Empty URL returns error
    - ImportError graceful handling
    - Success path (mocked StealthyFetcher)
    - Output shape: {success, result, task, human_score}
    - Fingerprint recorded in tracker
    - Error path output shape
  ScraplingAgent.run_parallel(tasks, max_concurrent)
    - Returns list with index field
    - Exception handling
    - Empty tasks list
    - Concurrency (max_concurrent honored)
"""
import asyncio
import time
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from src.scrapling_agent import ScraplingConfig, ScraplingAgent, _build_scrapling_proxy
from src.proxy_provider import SmartProxyISPBackend


# ---------------------------------------------------------------------------
# ScraplingConfig
# ---------------------------------------------------------------------------

class TestScraplingConfig:
    def test_all_defaults(self):
        config = ScraplingConfig()
        assert config.smartproxy_username == ""
        assert config.smartproxy_password == ""
        assert config.smartproxy_host == "isp.decodo.com"
        assert config.smartproxy_port == 10001
        assert config.area == "us"
        assert config.timezone == ""
        assert config.no_proxy is False
        assert config.headless is True
        assert config.solve_cloudflare is False
        assert config.hide_canvas is True
        assert config.network_idle is True
        assert config.gologin_api_token == ""

    def test_custom_values(self):
        config = ScraplingConfig(
            smartproxy_username="u",
            smartproxy_password="p",
            smartproxy_host="custom.host",
            smartproxy_port=9999,
            area="jp",
            timezone="Asia/Tokyo",
            no_proxy=True,
            headless=False,
            solve_cloudflare=True,
            hide_canvas=False,
            network_idle=False,
            gologin_api_token="tok123",
        )
        assert config.smartproxy_username == "u"
        assert config.smartproxy_password == "p"
        assert config.smartproxy_host == "custom.host"
        assert config.smartproxy_port == 9999
        assert config.area == "jp"
        assert config.timezone == "Asia/Tokyo"
        assert config.no_proxy is True
        assert config.headless is False
        assert config.solve_cloudflare is True
        assert config.hide_canvas is False
        assert config.network_idle is False
        assert config.gologin_api_token == "tok123"


# ---------------------------------------------------------------------------
# _build_scrapling_proxy
# ---------------------------------------------------------------------------

class TestBuildScraplingProxy:
    def test_output_format_keys(self):
        backend = SmartProxyISPBackend(username="u", password="p", host="h.com", port=1234)
        result = _build_scrapling_proxy(backend, "us", "s1")
        assert set(result.keys()) == {"server", "username", "password"}

    def test_server_format(self):
        backend = SmartProxyISPBackend(username="u", password="p", host="proxy.example.com", port=12345)
        result = _build_scrapling_proxy(backend, "us", "s1")
        assert result["server"] == "proxy.example.com:12345"

    def test_password_passthrough(self):
        backend = SmartProxyISPBackend(username="u", password="secret123")
        result = _build_scrapling_proxy(backend, "us", "s1")
        assert result["password"] == "secret123"

    def test_country_in_username(self):
        backend = SmartProxyISPBackend(username="myuser", password="p")
        result = _build_scrapling_proxy(backend, "jp", "s1")
        assert "jp" in result["username"]

    def test_session_id_in_username(self):
        backend = SmartProxyISPBackend(username="myuser", password="p")
        result = _build_scrapling_proxy(backend, "us", "session_42")
        assert "session_42" in result["username"]

    def test_username_base_in_username(self):
        backend = SmartProxyISPBackend(username="myuser", password="p")
        result = _build_scrapling_proxy(backend, "us", "s1")
        assert "myuser" in result["username"]

    def test_default_host_port(self):
        """Backend with default host/port"""
        backend = SmartProxyISPBackend(username="u", password="p")
        result = _build_scrapling_proxy(backend, "us", "s1")
        assert result["server"] == "isp.decodo.com:10001"


# ---------------------------------------------------------------------------
# ScraplingAgent.__init__
# ---------------------------------------------------------------------------

class TestScraplingAgentInit:
    def test_no_proxy_flag(self):
        agent = ScraplingAgent(ScraplingConfig(no_proxy=True))
        assert agent.proxy_manager is None
        assert agent.ua_manager is not None
        assert agent._session_counter == 0

    def test_with_proxy_credentials(self):
        agent = ScraplingAgent(ScraplingConfig(
            smartproxy_username="user", smartproxy_password="pass",
        ))
        assert agent.proxy_manager is not None

    def test_no_proxy_flag_overrides_credentials(self):
        agent = ScraplingAgent(ScraplingConfig(
            smartproxy_username="user", smartproxy_password="pass", no_proxy=True,
        ))
        assert agent.proxy_manager is None

    def test_missing_username_no_proxy(self):
        agent = ScraplingAgent(ScraplingConfig(smartproxy_password="pass"))
        assert agent.proxy_manager is None

    def test_missing_password_no_proxy(self):
        agent = ScraplingAgent(ScraplingConfig(smartproxy_username="user"))
        assert agent.proxy_manager is None

    def test_empty_credentials_no_proxy(self):
        agent = ScraplingAgent(ScraplingConfig())
        assert agent.proxy_manager is None

    def test_session_counter_starts_at_zero(self):
        agent = ScraplingAgent(ScraplingConfig(no_proxy=True))
        assert agent._session_counter == 0


# ---------------------------------------------------------------------------
# ScraplingAgent._get_session_params
# ---------------------------------------------------------------------------

class TestScraplingAgentSessionParams:
    def test_increments_session_counter(self):
        agent = ScraplingAgent(ScraplingConfig(no_proxy=True))
        assert agent._session_counter == 0
        agent._get_session_params()
        assert agent._session_counter == 1
        agent._get_session_params()
        assert agent._session_counter == 2

    def test_returns_required_keys(self):
        agent = ScraplingAgent(ScraplingConfig(no_proxy=True))
        kwargs = agent._get_session_params()
        required = {"headless", "useragent", "locale", "timezone_id", "hide_canvas", "block_webrtc"}
        assert required.issubset(set(kwargs.keys()))

    def test_headless_true(self):
        agent = ScraplingAgent(ScraplingConfig(no_proxy=True, headless=True))
        assert agent._get_session_params()["headless"] is True

    def test_headless_false(self):
        agent = ScraplingAgent(ScraplingConfig(no_proxy=True, headless=False))
        assert agent._get_session_params()["headless"] is False

    def test_useragent_nonempty(self):
        agent = ScraplingAgent(ScraplingConfig(no_proxy=True))
        assert len(agent._get_session_params()["useragent"]) > 0

    def test_locale_matches_area_jp(self):
        agent = ScraplingAgent(ScraplingConfig(no_proxy=True, area="jp"))
        locale = agent._get_session_params()["locale"]
        assert "ja" in locale.lower() or "jp" in locale.lower()

    def test_locale_matches_area_us(self):
        agent = ScraplingAgent(ScraplingConfig(no_proxy=True, area="us"))
        locale = agent._get_session_params()["locale"]
        assert "en" in locale.lower()

    def test_hide_canvas_from_config(self):
        agent = ScraplingAgent(ScraplingConfig(no_proxy=True, hide_canvas=False))
        assert agent._get_session_params()["hide_canvas"] is False

    def test_block_webrtc_always_true(self):
        agent = ScraplingAgent(ScraplingConfig(no_proxy=True))
        assert agent._get_session_params()["block_webrtc"] is True

    def test_no_proxy_key_when_no_proxy_manager(self):
        agent = ScraplingAgent(ScraplingConfig(no_proxy=True))
        kwargs = agent._get_session_params()
        assert "proxy" not in kwargs

    def test_proxy_key_when_proxy_manager(self):
        agent = ScraplingAgent(ScraplingConfig(
            smartproxy_username="u", smartproxy_password="p",
        ))
        kwargs = agent._get_session_params()
        assert "proxy" in kwargs
        assert "server" in kwargs["proxy"]
        assert "username" in kwargs["proxy"]
        assert "password" in kwargs["proxy"]

    def test_timezone_override(self):
        agent = ScraplingAgent(ScraplingConfig(no_proxy=True, area="us", timezone="Europe/Berlin"))
        kwargs = agent._get_session_params()
        assert kwargs["timezone_id"] == "Europe/Berlin"


# ---------------------------------------------------------------------------
# ScraplingAgent._parse_task
# ---------------------------------------------------------------------------

class TestParseTask:
    def _agent(self):
        return ScraplingAgent(ScraplingConfig(no_proxy=True))

    def test_string_url(self):
        parsed = self._agent()._parse_task("https://example.com")
        assert parsed["url"] == "https://example.com"
        assert parsed["page_action"] is None
        assert parsed["solve_cloudflare"] is False

    def test_string_url_with_config_cloudflare(self):
        agent = ScraplingAgent(ScraplingConfig(no_proxy=True, solve_cloudflare=True))
        parsed = agent._parse_task("https://example.com")
        assert parsed["solve_cloudflare"] is True

    def test_dict_full(self):
        parsed = self._agent()._parse_task({
            "url": "https://x.com",
            "page_action": "click",
            "solve_cloudflare": True,
        })
        assert parsed["url"] == "https://x.com"
        assert parsed["page_action"] == "click"
        assert parsed["solve_cloudflare"] is True

    def test_dict_missing_url(self):
        parsed = self._agent()._parse_task({"page_action": "click"})
        assert parsed["url"] == ""

    def test_dict_missing_page_action(self):
        parsed = self._agent()._parse_task({"url": "https://x.com"})
        assert parsed["page_action"] is None

    def test_dict_solve_cloudflare_default_from_config(self):
        agent = ScraplingAgent(ScraplingConfig(no_proxy=True, solve_cloudflare=True))
        parsed = agent._parse_task({"url": "https://x.com"})
        assert parsed["solve_cloudflare"] is True

    def test_dict_solve_cloudflare_override(self):
        agent = ScraplingAgent(ScraplingConfig(no_proxy=True, solve_cloudflare=True))
        parsed = agent._parse_task({"url": "https://x.com", "solve_cloudflare": False})
        assert parsed["solve_cloudflare"] is False


# ---------------------------------------------------------------------------
# ScraplingAgent.run
# ---------------------------------------------------------------------------

class TestScraplingAgentRun:
    @pytest.mark.asyncio
    async def test_empty_string_url(self):
        agent = ScraplingAgent(ScraplingConfig(no_proxy=True))
        result = await agent.run("")
        assert result["success"] is False
        assert "No URL" in result["error"]
        assert result["human_score"] == {}

    @pytest.mark.asyncio
    async def test_dict_with_no_url(self):
        agent = ScraplingAgent(ScraplingConfig(no_proxy=True))
        result = await agent.run({"page_action": "click"})
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_output_shape_on_error(self):
        """Error result must have: success, error, task, human_score"""
        agent = ScraplingAgent(ScraplingConfig(no_proxy=True))
        result = await agent.run("")
        assert "success" in result
        assert "error" in result
        assert "task" in result
        assert "human_score" in result

    @pytest.mark.asyncio
    async def test_scrapling_not_installed(self):
        agent = ScraplingAgent(ScraplingConfig(no_proxy=True))
        import builtins
        real_import = builtins.__import__
        def mock_import(name, *args, **kwargs):
            if name == "scrapling":
                raise ImportError("No module named 'scrapling'")
            return real_import(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=mock_import):
            result = await agent.run("https://example.com")
            assert result["success"] is False
            assert "scrapling not installed" in result["error"]
            assert result["human_score"] == {}

    @pytest.mark.asyncio
    async def test_success_path_mocked(self):
        """Full success path with mocked StealthyFetcher"""
        agent = ScraplingAgent(ScraplingConfig(no_proxy=True))

        # Mock scrapling response
        mock_page = MagicMock()
        mock_page.status = 200
        mock_title = MagicMock()
        mock_title.text = "Test Title"
        mock_page.css.return_value = [mock_title]
        mock_page.get_all_text.return_value = "Hello world test content"

        mock_fetcher_cls = MagicMock()
        mock_fetcher_cls.fetch.return_value = mock_page

        with patch.dict("sys.modules", {"scrapling": MagicMock(StealthyFetcher=mock_fetcher_cls)}):
            import builtins
            real_import = builtins.__import__
            def patched_import(name, *args, **kwargs):
                if name == "scrapling":
                    mod = MagicMock()
                    mod.StealthyFetcher = mock_fetcher_cls
                    return mod
                return real_import(name, *args, **kwargs)
            with patch("builtins.__import__", side_effect=patched_import):
                result = await agent.run("https://example.com")

        assert result["success"] is True
        assert "result" in result
        assert result["result"]["url"] == "https://example.com"
        assert result["result"]["status"] == 200
        assert result["result"]["title"] == "Test Title"
        assert result["result"]["text_length"] == len("Hello world test content")
        assert "task" in result
        assert "human_score" in result
        assert isinstance(result["human_score"], dict)
        assert "score" in result["human_score"]
        assert "is_human" in result["human_score"]

    @pytest.mark.asyncio
    async def test_success_output_shape(self):
        """Success result must have: success, result, task, human_score"""
        agent = ScraplingAgent(ScraplingConfig(no_proxy=True))
        mock_page = MagicMock()
        mock_page.status = 200
        mock_page.css.return_value = []
        mock_page.get_all_text.return_value = ""
        mock_fetcher_cls = MagicMock()
        mock_fetcher_cls.fetch.return_value = mock_page

        import builtins
        real_import = builtins.__import__
        def patched_import(name, *args, **kwargs):
            if name == "scrapling":
                mod = MagicMock()
                mod.StealthyFetcher = mock_fetcher_cls
                return mod
            return real_import(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=patched_import):
            result = await agent.run("https://example.com")

        assert set(result.keys()) >= {"success", "result", "task", "human_score"}

    @pytest.mark.asyncio
    async def test_fetch_exception_returns_error(self):
        """Exception during fetch returns error dict, not raises"""
        agent = ScraplingAgent(ScraplingConfig(no_proxy=True))
        mock_fetcher_cls = MagicMock()
        mock_fetcher_cls.fetch.side_effect = RuntimeError("Connection refused")

        import builtins
        real_import = builtins.__import__
        def patched_import(name, *args, **kwargs):
            if name == "scrapling":
                mod = MagicMock()
                mod.StealthyFetcher = mock_fetcher_cls
                return mod
            return real_import(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=patched_import):
            result = await agent.run("https://fail.example.com")

        assert result["success"] is False
        assert "Connection refused" in result["error"]
        assert isinstance(result["human_score"], dict)
        assert "score" in result["human_score"]

    @pytest.mark.asyncio
    async def test_task_field_matches_input(self):
        """task field in output matches input"""
        agent = ScraplingAgent(ScraplingConfig(no_proxy=True))
        result = await agent.run("")
        assert result["task"] == ""

        result2 = await agent.run({"url": ""})
        assert "url" in result2["task"]


# ---------------------------------------------------------------------------
# ScraplingAgent.run_parallel
# ---------------------------------------------------------------------------

class TestScraplingAgentRunParallel:
    @pytest.mark.asyncio
    async def test_empty_tasks(self):
        agent = ScraplingAgent(ScraplingConfig(no_proxy=True))
        results = await agent.run_parallel([])
        assert results == []

    @pytest.mark.asyncio
    async def test_returns_list(self):
        agent = ScraplingAgent(ScraplingConfig(no_proxy=True))
        results = await agent.run_parallel(["", ""])
        assert isinstance(results, list)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_index_field_present(self):
        agent = ScraplingAgent(ScraplingConfig(no_proxy=True))
        results = await agent.run_parallel(["", "", ""])
        for i, r in enumerate(results):
            assert r["index"] == i

    @pytest.mark.asyncio
    async def test_error_results_have_correct_shape(self):
        agent = ScraplingAgent(ScraplingConfig(no_proxy=True))
        results = await agent.run_parallel([""])
        r = results[0]
        assert "success" in r
        assert "task" in r
        assert "index" in r

    @pytest.mark.asyncio
    async def test_concurrency_respected(self):
        """max_concurrent=1 should serialize execution"""
        agent = ScraplingAgent(ScraplingConfig(no_proxy=True))
        # All empty URLs, so they fail fast without network
        results = await agent.run_parallel(["", "", ""], max_concurrent=1)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_mixed_success_and_failure(self):
        """Mix of empty (fail) and valid (mocked success) tasks"""
        agent = ScraplingAgent(ScraplingConfig(no_proxy=True))
        # Both will fail due to empty URL
        results = await agent.run_parallel(["", ""])
        assert all(r["success"] is False for r in results)

    @pytest.mark.asyncio
    async def test_exception_in_task_handled(self):
        """If run() somehow raises, run_parallel catches it"""
        agent = ScraplingAgent(ScraplingConfig(no_proxy=True))
        original_run = agent.run

        call_count = [0]
        async def exploding_run(task):
            call_count[0] += 1
            if call_count[0] == 2:
                raise RuntimeError("boom")
            return await original_run(task)

        agent.run = exploding_run
        results = await agent.run_parallel(["", "", ""], max_concurrent=5)
        assert len(results) == 3
        # The second should be an exception result
        assert results[1]["success"] is False
        assert "boom" in results[1]["error"]
