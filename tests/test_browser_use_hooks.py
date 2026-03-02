"""
Tests for browser_use_agent.py modifications:
  - HUMAN_BEHAVIOR_PROMPT content
  - Human timing hooks (_on_step_start, _on_step_end)
  - _harvest_agent_history with real timestamps vs fallback
  - _harvest_agent_history mixed outcome recording
  - BrowserProfile wait_between_actions
  - Agent system prompt composition
"""
import time
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from dataclasses import dataclass
from typing import Optional, Any

from src.browser_use_agent import (
    BrowserUseAgent,
    BrowserUseConfig,
    HUMAN_BEHAVIOR_PROMPT,
    CAPTCHA_SYSTEM_PROMPT,
)
from src.human_score import HumanScoreTracker


# ---------------------------------------------------------------------------
# HUMAN_BEHAVIOR_PROMPT
# ---------------------------------------------------------------------------

class TestHumanBehaviorPrompt:
    def test_prompt_exists(self):
        assert HUMAN_BEHAVIOR_PROMPT is not None
        assert len(HUMAN_BEHAVIOR_PROMPT) > 50

    def test_prompt_mentions_scroll(self):
        assert "scroll" in HUMAN_BEHAVIOR_PROMPT.lower()

    def test_prompt_mentions_action_variety(self):
        assert "vary" in HUMAN_BEHAVIOR_PROMPT.lower() or "mix" in HUMAN_BEHAVIOR_PROMPT.lower()

    def test_prompt_mentions_multiple_pages(self):
        assert "multiple pages" in HUMAN_BEHAVIOR_PROMPT.lower() or "follow links" in HUMAN_BEHAVIOR_PROMPT.lower()

    def test_prompt_mentions_pauses(self):
        assert "pause" in HUMAN_BEHAVIOR_PROMPT.lower() or "rush" in HUMAN_BEHAVIOR_PROMPT.lower()

    def test_captcha_prompt_still_exists(self):
        assert "CAPTCHA" in CAPTCHA_SYSTEM_PROMPT

    def test_combined_prompts_non_empty(self):
        combined = HUMAN_BEHAVIOR_PROMPT + CAPTCHA_SYSTEM_PROMPT
        assert len(combined) > 100


# ---------------------------------------------------------------------------
# _harvest_agent_history - real timestamps
# ---------------------------------------------------------------------------

@dataclass
class _MockAction:
    """Minimal mock for action objects"""
    _data: dict

    def model_dump(self, exclude_none=True):
        return self._data


@dataclass
class _MockModelOutput:
    action: list


@dataclass
class _MockResult:
    current_url: str = ""
    extracted_content: str = ""
    error: Optional[str] = None


@dataclass
class _MockHistoryItem:
    model_output: Optional[_MockModelOutput] = None
    result: Optional[list] = None


class _MockHistory:
    def __init__(self, items):
        self.history = items


class _MockAgent:
    def __init__(self, items):
        self.history = _MockHistory(items)


class TestHarvestAgentHistory:
    def test_with_real_timestamps(self):
        """When step_timestamps provided, uses them instead of approximation"""
        now = time.time()
        step_timestamps = [
            now,        # step 0 start
            now + 2.5,  # step 0 end
            now + 5.0,  # step 1 start
            now + 7.0,  # step 1 end
        ]

        items = [
            _MockHistoryItem(
                model_output=_MockModelOutput(action=[_MockAction({"click_element": 1})]),
                result=[_MockResult(current_url="https://example.com/1")],
            ),
            _MockHistoryItem(
                model_output=_MockModelOutput(action=[_MockAction({"input_text": "hello"})]),
                result=[_MockResult(current_url="https://example.com/2")],
            ),
        ]
        agent = _MockAgent(items)
        tracker = HumanScoreTracker()

        BrowserUseAgent._harvest_agent_history(agent, tracker, step_timestamps)

        # Check actions recorded with real timestamps
        assert len(tracker._actions) == 2
        assert abs(tracker._actions[0].timestamp - now) < 0.01
        assert abs(tracker._actions[1].timestamp - (now + 5.0)) < 0.01

        # Check dwell times computed from real timestamps
        assert len(tracker._pages) == 2
        assert abs(tracker._pages[0].dwell_sec - 2.5) < 0.1
        assert abs(tracker._pages[1].dwell_sec - 2.0) < 0.1

    def test_without_timestamps_uses_fallback(self):
        """When step_timestamps is empty/None, uses approximate timestamps"""
        items = [
            _MockHistoryItem(
                model_output=_MockModelOutput(action=[_MockAction({"scroll": None})]),
                result=[_MockResult(current_url="https://example.com/1")],
            ),
        ]
        agent = _MockAgent(items)
        tracker = HumanScoreTracker()

        BrowserUseAgent._harvest_agent_history(agent, tracker, None)

        assert len(tracker._actions) == 1
        # Fallback dwell is 3.0
        assert len(tracker._pages) == 1
        assert tracker._pages[0].dwell_sec == 3.0

    def test_empty_timestamps_list_uses_fallback(self):
        items = [
            _MockHistoryItem(
                model_output=_MockModelOutput(action=[_MockAction({"click": 1})]),
                result=[_MockResult(current_url="https://x.com")],
            ),
        ]
        agent = _MockAgent(items)
        tracker = HumanScoreTracker()

        BrowserUseAgent._harvest_agent_history(agent, tracker, [])

        assert len(tracker._actions) == 1
        assert tracker._pages[0].dwell_sec == 3.0

    def test_partial_timestamps(self):
        """More history items than timestamps: falls back for later items"""
        now = time.time()
        step_timestamps = [now, now + 2.0]  # Only for first item

        items = [
            _MockHistoryItem(
                model_output=_MockModelOutput(action=[_MockAction({"click": 1})]),
                result=[_MockResult(current_url="https://a.com")],
            ),
            _MockHistoryItem(
                model_output=_MockModelOutput(action=[_MockAction({"scroll": None})]),
                result=[_MockResult(current_url="https://b.com")],
            ),
        ]
        agent = _MockAgent(items)
        tracker = HumanScoreTracker()

        BrowserUseAgent._harvest_agent_history(agent, tracker, step_timestamps)

        assert len(tracker._actions) == 2
        # First uses real timestamp
        assert abs(tracker._actions[0].timestamp - now) < 0.01
        # Second falls back to approximation (different from now)

    def test_no_history(self):
        """Agent with no history should not crash"""
        agent = MagicMock()
        agent.history = None
        tracker = HumanScoreTracker()

        BrowserUseAgent._harvest_agent_history(agent, tracker, [])
        assert len(tracker._actions) == 0

    def test_empty_history(self):
        agent = _MockAgent([])
        tracker = HumanScoreTracker()
        BrowserUseAgent._harvest_agent_history(agent, tracker, [])
        assert len(tracker._actions) == 0


# ---------------------------------------------------------------------------
# Mixed outcomes (H_C2 improvement)
# ---------------------------------------------------------------------------

class TestHarvestMixedOutcomes:
    def test_navigation_outcome(self):
        """go_to_url action records 'navigation' outcome"""
        now = time.time()
        items = [
            _MockHistoryItem(
                model_output=_MockModelOutput(action=[_MockAction({"go_to_url": "https://x.com"})]),
                result=[_MockResult(current_url="https://x.com")],
            ),
        ]
        agent = _MockAgent(items)
        tracker = HumanScoreTracker()
        BrowserUseAgent._harvest_agent_history(agent, tracker, [now, now + 1])
        assert "navigation" in tracker._outcomes

    def test_extract_outcome(self):
        """extract_content records 'partial' outcome"""
        now = time.time()
        items = [
            _MockHistoryItem(
                model_output=_MockModelOutput(action=[_MockAction({"extract_content": True})]),
                result=[_MockResult(current_url="https://x.com")],
            ),
        ]
        agent = _MockAgent(items)
        tracker = HumanScoreTracker()
        BrowserUseAgent._harvest_agent_history(agent, tracker, [now, now + 1])
        assert "partial" in tracker._outcomes

    def test_click_outcome(self):
        """Regular click records 'success' outcome"""
        now = time.time()
        items = [
            _MockHistoryItem(
                model_output=_MockModelOutput(action=[_MockAction({"click_element": 1})]),
                result=[_MockResult(current_url="https://x.com")],
            ),
        ]
        agent = _MockAgent(items)
        tracker = HumanScoreTracker()
        BrowserUseAgent._harvest_agent_history(agent, tracker, [now, now + 1])
        assert "success" in tracker._outcomes

    def test_error_outcome(self):
        """Error in result records 'failure' outcome"""
        now = time.time()
        items = [
            _MockHistoryItem(
                model_output=_MockModelOutput(action=[_MockAction({"click": 1})]),
                result=[_MockResult(current_url="https://x.com", error="Element not found")],
            ),
        ]
        agent = _MockAgent(items)
        tracker = HumanScoreTracker()
        BrowserUseAgent._harvest_agent_history(agent, tracker, [now, now + 1])
        assert "failure" in tracker._outcomes

    def test_mixed_outcomes_variety(self):
        """Multiple action types produce diverse outcomes"""
        now = time.time()
        items = [
            _MockHistoryItem(
                model_output=_MockModelOutput(action=[_MockAction({"go_to_url": "a"})]),
                result=[_MockResult(current_url="https://a.com")],
            ),
            _MockHistoryItem(
                model_output=_MockModelOutput(action=[_MockAction({"click_element": 1})]),
                result=[_MockResult(current_url="https://b.com")],
            ),
            _MockHistoryItem(
                model_output=_MockModelOutput(action=[_MockAction({"extract_content": True})]),
                result=[_MockResult(current_url="https://c.com")],
            ),
            _MockHistoryItem(
                model_output=_MockModelOutput(action=[_MockAction({"scroll": None})]),
                result=[_MockResult(current_url="https://d.com", error="timeout")],
            ),
        ]
        ts = [now + i * 3 for i in range(8)]  # 4 items * 2 timestamps each
        agent = _MockAgent(items)
        tracker = HumanScoreTracker()
        BrowserUseAgent._harvest_agent_history(agent, tracker, ts)

        outcome_set = set(tracker._outcomes)
        assert "navigation" in outcome_set
        assert "success" in outcome_set
        assert "partial" in outcome_set
        assert "failure" in outcome_set


# ---------------------------------------------------------------------------
# Page visit extraction from history
# ---------------------------------------------------------------------------

class TestHarvestPageVisits:
    def test_url_from_current_url(self):
        items = [
            _MockHistoryItem(
                model_output=_MockModelOutput(action=[_MockAction({"click": 1})]),
                result=[_MockResult(current_url="https://visited.com/page")],
            ),
        ]
        agent = _MockAgent(items)
        tracker = HumanScoreTracker()
        BrowserUseAgent._harvest_agent_history(agent, tracker)
        assert tracker._pages[0].url == "https://visited.com/page"

    def test_url_from_extracted_content_fallback(self):
        """If current_url is missing (no attribute), falls back to extracted_content"""

        @dataclass
        class _ResultNoUrl:
            extracted_content: str = ""
            error: Optional[str] = None

        items = [
            _MockHistoryItem(
                model_output=_MockModelOutput(action=[_MockAction({"click": 1})]),
                result=[_ResultNoUrl(extracted_content="https://fallback.com/data")],
            ),
        ]
        agent = _MockAgent(items)
        tracker = HumanScoreTracker()
        BrowserUseAgent._harvest_agent_history(agent, tracker)
        assert "fallback.com" in tracker._pages[0].url

    def test_clicked_flag_for_click_actions(self):
        """click_element, click, input_text should set clicked=True"""
        for action_name in ["click_element", "click", "input_text"]:
            items = [
                _MockHistoryItem(
                    model_output=_MockModelOutput(action=[_MockAction({action_name: 1})]),
                    result=[_MockResult(current_url="https://x.com")],
                ),
            ]
            agent = _MockAgent(items)
            tracker = HumanScoreTracker()
            BrowserUseAgent._harvest_agent_history(agent, tracker)
            assert tracker._pages[0].clicked is True, f"Expected clicked=True for {action_name}"

    def test_clicked_flag_false_for_scroll(self):
        items = [
            _MockHistoryItem(
                model_output=_MockModelOutput(action=[_MockAction({"scroll": None})]),
                result=[_MockResult(current_url="https://x.com")],
            ),
        ]
        agent = _MockAgent(items)
        tracker = HumanScoreTracker()
        BrowserUseAgent._harvest_agent_history(agent, tracker)
        assert tracker._pages[0].clicked is False

    def test_completed_true_when_no_error(self):
        items = [
            _MockHistoryItem(
                model_output=_MockModelOutput(action=[_MockAction({"click": 1})]),
                result=[_MockResult(current_url="https://x.com")],
            ),
        ]
        agent = _MockAgent(items)
        tracker = HumanScoreTracker()
        BrowserUseAgent._harvest_agent_history(agent, tracker)
        assert tracker._pages[0].completed is True

    def test_completed_false_when_error(self):
        items = [
            _MockHistoryItem(
                model_output=_MockModelOutput(action=[_MockAction({"click": 1})]),
                result=[_MockResult(current_url="https://x.com", error="not found")],
            ),
        ]
        agent = _MockAgent(items)
        tracker = HumanScoreTracker()
        BrowserUseAgent._harvest_agent_history(agent, tracker)
        assert tracker._pages[0].completed is False

    def test_no_page_visit_when_no_url(self):
        """If result has no URL, no page visit is recorded"""
        items = [
            _MockHistoryItem(
                model_output=_MockModelOutput(action=[_MockAction({"wait": None})]),
                result=[_MockResult()],
            ),
        ]
        agent = _MockAgent(items)
        tracker = HumanScoreTracker()
        BrowserUseAgent._harvest_agent_history(agent, tracker)
        assert len(tracker._pages) == 0

    def test_action_name_extraction_from_dict(self):
        """Action as plain dict (not model_dump object)"""
        items = [
            _MockHistoryItem(
                model_output=_MockModelOutput(action=[{"navigate": "https://x.com"}]),
                result=[_MockResult(current_url="https://x.com")],
            ),
        ]
        agent = _MockAgent(items)
        tracker = HumanScoreTracker()
        BrowserUseAgent._harvest_agent_history(agent, tracker)
        assert tracker._actions[0].action_type == "navigate"

    def test_unknown_action_when_no_model_output(self):
        items = [
            _MockHistoryItem(
                model_output=None,
                result=[_MockResult(current_url="https://x.com")],
            ),
        ]
        agent = _MockAgent(items)
        tracker = HumanScoreTracker()
        BrowserUseAgent._harvest_agent_history(agent, tracker)
        assert tracker._actions[0].action_type == "unknown"

    def test_graceful_on_malformed_history(self):
        """Should not raise even with weird history items"""
        agent = _MockAgent([MagicMock(model_output=None, result=None)])
        tracker = HumanScoreTracker()
        BrowserUseAgent._harvest_agent_history(agent, tracker)
        # Should record 'unknown' action and not crash
        assert len(tracker._actions) == 1
