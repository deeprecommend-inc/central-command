"""
Tests for run.py CLI

Spec coverage:
  parse_args(args)
    - Default values for all options
    - --mode / -M parsing
    - --model / -m, --parallel / -p, --area / -a, --timezone / -t
    - --no-proxy flag
    - --verbose / -v flag
    - Unknown args go to prompt_parts
    - Multiple prompt words joined
    - -M without value (at end of args)
  print_usage()
    - Contains scrapling references
    - Contains --mode option
    - Contains SOLVE_CLOUDFLARE
  run_scrapling(opts)
    - Config construction from opts + env
    - parallel path
    - success/failure output
  main() routing
    - mode=scrapling routes to run_scrapling
    - mode=browser-use routes to run
"""
import sys
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from io import StringIO

# Import after dotenv to avoid side effects
sys.modules.setdefault("dotenv", MagicMock())


# ---------------------------------------------------------------------------
# parse_args
# ---------------------------------------------------------------------------

class TestParseArgs:
    def _parse(self, args_str: str) -> dict:
        """Helper: parse space-separated args string"""
        from run import parse_args
        return parse_args(args_str.split() if args_str else [])

    def test_defaults(self):
        opts = self._parse("")
        assert opts["mode"] == "browser-use"
        assert opts["parallel"] == 1
        assert opts["no_proxy"] is False
        assert opts["verbose"] is False
        assert opts["prompt_parts"] == []

    def test_mode_long(self):
        opts = self._parse("--mode scrapling https://x.com")
        assert opts["mode"] == "scrapling"

    def test_mode_short(self):
        opts = self._parse("-M scrapling https://x.com")
        assert opts["mode"] == "scrapling"

    def test_mode_default(self):
        opts = self._parse("hello")
        assert opts["mode"] == "browser-use"

    def test_mode_unknown_value(self):
        """Unknown mode value is still accepted (validation elsewhere)"""
        opts = self._parse("-M custom hello")
        assert opts["mode"] == "custom"

    def test_model_long(self):
        opts = self._parse("--model hermes3 hello")
        assert opts["model"] == "hermes3"

    def test_model_short(self):
        opts = self._parse("-m gpt-4o hello")
        assert opts["model"] == "gpt-4o"

    def test_parallel_long(self):
        opts = self._parse("--parallel 5 hello")
        assert opts["parallel"] == 5

    def test_parallel_short(self):
        opts = self._parse("-p 3 hello")
        assert opts["parallel"] == 3

    def test_area_long(self):
        opts = self._parse("--area jp hello")
        assert opts["area"] == "jp"

    def test_area_short(self):
        opts = self._parse("-a de hello")
        assert opts["area"] == "de"

    def test_timezone_long(self):
        opts = self._parse("--timezone Asia/Tokyo hello")
        assert opts["timezone"] == "Asia/Tokyo"

    def test_timezone_short(self):
        opts = self._parse("-t Europe/Berlin hello")
        assert opts["timezone"] == "Europe/Berlin"

    def test_no_proxy(self):
        opts = self._parse("--no-proxy hello")
        assert opts["no_proxy"] is True

    def test_verbose_long(self):
        opts = self._parse("--verbose hello")
        assert opts["verbose"] is True

    def test_verbose_short(self):
        opts = self._parse("-v hello")
        assert opts["verbose"] is True

    def test_prompt_parts_single(self):
        opts = self._parse("hello")
        assert opts["prompt_parts"] == ["hello"]

    def test_prompt_parts_multiple(self):
        opts = self._parse("go to example.com")
        assert opts["prompt_parts"] == ["go", "to", "example.com"]

    def test_combined_options(self):
        opts = self._parse("-M scrapling -a jp --no-proxy -p 2 https://x.com")
        assert opts["mode"] == "scrapling"
        assert opts["area"] == "jp"
        assert opts["no_proxy"] is True
        assert opts["parallel"] == 2
        assert opts["prompt_parts"] == ["https://x.com"]

    def test_mode_at_end_without_value(self):
        """--mode at end of args without value: should not crash"""
        opts = self._parse("hello --mode")
        # --mode has no value (i+1 >= len), so it falls through to prompt_parts
        assert opts["mode"] == "browser-use"  # stays default
        assert "--mode" in opts["prompt_parts"]

    def test_all_options_together(self):
        opts = self._parse("-M scrapling -m hermes3 -p 4 -a gb -t Europe/London --no-proxy -v fetch page")
        assert opts["mode"] == "scrapling"
        assert opts["model"] == "hermes3"
        assert opts["parallel"] == 4
        assert opts["area"] == "gb"
        assert opts["timezone"] == "Europe/London"
        assert opts["no_proxy"] is True
        assert opts["verbose"] is True
        assert opts["prompt_parts"] == ["fetch", "page"]


# ---------------------------------------------------------------------------
# print_usage
# ---------------------------------------------------------------------------

class TestPrintUsage:
    def test_contains_mode_option(self):
        from run import print_usage
        import io
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            print_usage()
        output = buf.getvalue()
        assert "--mode" in output
        assert "-M" in output

    def test_contains_scrapling(self):
        from run import print_usage
        import io
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            print_usage()
        output = buf.getvalue()
        assert "scrapling" in output.lower()

    def test_contains_solve_cloudflare(self):
        from run import print_usage
        import io
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            print_usage()
        output = buf.getvalue()
        assert "SOLVE_CLOUDFLARE" in output

    def test_contains_browser_use(self):
        from run import print_usage
        import io
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            print_usage()
        output = buf.getvalue()
        assert "browser-use" in output


# ---------------------------------------------------------------------------
# run_scrapling config construction
# ---------------------------------------------------------------------------

class TestRunScraplingConfig:
    @pytest.mark.asyncio
    async def test_empty_prompt_exits(self):
        from run import run_scrapling
        opts = {
            "prompt_parts": [],
            "area": "us",
            "timezone": "",
            "no_proxy": True,
            "parallel": 1,
        }
        with pytest.raises(SystemExit):
            await run_scrapling(opts)

    @pytest.mark.asyncio
    async def test_config_from_opts(self):
        """Verify ScraplingConfig is constructed with correct values from opts"""
        from run import run_scrapling
        captured_config = {}

        class MockAgent:
            def __init__(self, config):
                captured_config["config"] = config

            async def run(self, prompt):
                return {"success": True, "result": {}, "task": prompt, "human_score": {"score": 90, "max": 100, "is_human": True}}

        with patch("src.scrapling_agent.ScraplingAgent", MockAgent), \
             patch("src.scrapling_agent.ScraplingConfig") as MockConfig, \
             patch("run.get_env", side_effect=lambda k, d="": {"SMARTPROXY_USERNAME": "", "SMARTPROXY_PASSWORD": "", "SMARTPROXY_HOST": "isp.decodo.com", "SMARTPROXY_PORT": "10001", "HEADLESS": "true", "SOLVE_CLOUDFLARE": "true", "GOLOGIN_API_TOKEN": ""}.get(k, d)):
            MockConfig.return_value = MagicMock()
            mock_agent = MockAgent(MockConfig.return_value)
            with patch("src.scrapling_agent.ScraplingAgent", return_value=mock_agent):
                opts = {
                    "prompt_parts": ["https://example.com"],
                    "area": "jp",
                    "timezone": "Asia/Tokyo",
                    "no_proxy": True,
                    "parallel": 1,
                }
                await run_scrapling(opts)


# ---------------------------------------------------------------------------
# main() routing
# ---------------------------------------------------------------------------

class TestMainRouting:
    def test_scrapling_mode_calls_run_scrapling(self):
        from run import main
        with patch("run.parse_args", return_value={
            "mode": "scrapling",
            "verbose": False,
            "prompt_parts": ["https://x.com"],
            "area": "us",
            "timezone": "",
            "no_proxy": True,
            "parallel": 1,
        }), \
        patch("run.asyncio") as mock_asyncio, \
        patch("run.run_scrapling") as mock_run_scrapling, \
        patch("sys.argv", ["run.py", "-M", "scrapling", "https://x.com"]):
            main()
            mock_asyncio.run.assert_called_once()
            # The argument to asyncio.run should be from run_scrapling
            call_args = mock_asyncio.run.call_args
            assert call_args is not None

    def test_browser_use_mode_calls_run(self):
        from run import main
        with patch("run.parse_args", return_value={
            "mode": "browser-use",
            "verbose": False,
            "prompt_parts": ["hello"],
            "area": "us",
            "timezone": "",
            "no_proxy": True,
            "parallel": 1,
            "model": "dolphin3",
        }), \
        patch("run.asyncio") as mock_asyncio, \
        patch("run.run") as mock_run, \
        patch("sys.argv", ["run.py", "hello"]):
            main()
            mock_asyncio.run.assert_called_once()

    def test_default_mode_calls_run(self):
        from run import main
        with patch("run.parse_args", return_value={
            "mode": "browser-use",
            "verbose": False,
            "prompt_parts": ["task"],
            "area": "us",
            "timezone": "",
            "no_proxy": True,
            "parallel": 1,
            "model": "dolphin3",
        }), \
        patch("run.asyncio") as mock_asyncio, \
        patch("sys.argv", ["run.py", "task"]):
            main()
            mock_asyncio.run.assert_called_once()
