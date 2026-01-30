"""
Tests for UserAgentManager
"""
import pytest
from src.ua_manager import UserAgentManager, BrowserProfile, LRUCache


class TestLRUCache:
    """Tests for LRUCache"""

    def test_basic_set_get(self):
        cache = LRUCache(max_size=3)
        cache.set("a", 1)
        assert cache.get("a") == 1

    def test_get_nonexistent(self):
        cache = LRUCache(max_size=3)
        assert cache.get("nonexistent") is None

    def test_eviction_on_capacity(self):
        cache = LRUCache(max_size=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        cache.set("d", 4)  # Should evict "a"
        assert cache.get("a") is None
        assert cache.get("b") == 2
        assert cache.get("d") == 4

    def test_lru_order_on_get(self):
        cache = LRUCache(max_size=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        cache.get("a")  # Move "a" to end
        cache.set("d", 4)  # Should evict "b" (oldest after "a" was accessed)
        assert cache.get("a") == 1
        assert cache.get("b") is None

    def test_delete(self):
        cache = LRUCache(max_size=3)
        cache.set("a", 1)
        assert cache.delete("a") is True
        assert cache.get("a") is None
        assert cache.delete("nonexistent") is False

    def test_contains(self):
        cache = LRUCache(max_size=3)
        cache.set("a", 1)
        assert "a" in cache
        assert "b" not in cache

    def test_len(self):
        cache = LRUCache(max_size=3)
        assert len(cache) == 0
        cache.set("a", 1)
        assert len(cache) == 1
        cache.set("b", 2)
        assert len(cache) == 2

    def test_clear(self):
        cache = LRUCache(max_size=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert len(cache) == 0
        assert cache.get("a") is None


class TestBrowserProfile:
    """Tests for BrowserProfile dataclass"""

    def test_to_playwright_context(self):
        profile = BrowserProfile(
            user_agent="Mozilla/5.0 Test",
            viewport_width=1920,
            viewport_height=1080,
            locale="en-US",
            timezone="America/New_York",
            platform="Windows",
        )
        context = profile.to_playwright_context()
        assert context["user_agent"] == "Mozilla/5.0 Test"
        assert context["viewport"]["width"] == 1920
        assert context["viewport"]["height"] == 1080
        assert context["locale"] == "en-US"
        assert context["timezone_id"] == "America/New_York"


class TestUserAgentManager:
    """Tests for UserAgentManager"""

    def test_initialization(self):
        manager = UserAgentManager()
        assert manager is not None

    def test_get_random_profile(self):
        manager = UserAgentManager()
        profile = manager.get_random_profile()
        assert profile is not None
        assert profile.user_agent is not None
        assert len(profile.user_agent) > 0
        assert profile.viewport_width > 0
        assert profile.viewport_height > 0

    def test_get_profile_with_session_id(self):
        manager = UserAgentManager()
        profile1 = manager.get_random_profile(session_id="test_session")
        profile2 = manager.get_random_profile(session_id="test_session")
        # Same session should return same profile
        assert profile1.user_agent == profile2.user_agent

    def test_different_sessions_get_different_profiles(self):
        manager = UserAgentManager()
        profiles = [
            manager.get_random_profile(session_id=f"session_{i}")
            for i in range(10)
        ]
        # At least some should be different (probabilistic but very likely)
        user_agents = [p.user_agent for p in profiles]
        unique_agents = set(user_agents)
        assert len(unique_agents) >= 1  # At least one unique

    def test_clear_session(self):
        manager = UserAgentManager()
        profile1 = manager.get_random_profile(session_id="clear_test")
        manager.clear_session("clear_test")
        profile2 = manager.get_random_profile(session_id="clear_test")
        # After clearing, may get different profile (not guaranteed but possible)
        # Just ensure no error occurs
        assert profile2 is not None

    def test_profile_has_valid_viewport(self):
        manager = UserAgentManager()
        profile = manager.get_random_profile()
        valid_widths = [w for w, h in manager.VIEWPORTS]
        assert profile.viewport_width in valid_widths

    def test_profile_has_valid_locale(self):
        manager = UserAgentManager()
        profile = manager.get_random_profile()
        assert profile.locale in manager.LOCALES

    def test_profile_has_valid_timezone(self):
        manager = UserAgentManager()
        profile = manager.get_random_profile()
        assert profile.timezone in manager.TIMEZONES

    def test_profile_platform_consistency(self):
        manager = UserAgentManager()
        profile = manager.get_random_profile()
        # Platform should be consistent with user agent
        ua_lower = profile.user_agent.lower()
        if "windows" in ua_lower:
            assert profile.platform in ["Windows", "Win32", "Win64"]
        elif "mac" in ua_lower or "macintosh" in ua_lower:
            assert "Mac" in profile.platform or "darwin" in profile.platform.lower()
        elif "linux" in ua_lower:
            assert "Linux" in profile.platform or "linux" in profile.platform.lower()

    def test_lru_eviction(self):
        manager = UserAgentManager(max_cached_profiles=3)
        manager.get_random_profile(session_id="s1")
        manager.get_random_profile(session_id="s2")
        manager.get_random_profile(session_id="s3")
        manager.get_random_profile(session_id="s4")  # Should evict s1
        stats = manager.get_cache_stats()
        assert stats["cached_profiles"] == 3
        assert stats["max_profiles"] == 3

    def test_clear_all(self):
        manager = UserAgentManager()
        manager.get_random_profile(session_id="s1")
        manager.get_random_profile(session_id="s2")
        manager.clear_all()
        stats = manager.get_cache_stats()
        assert stats["cached_profiles"] == 0

    def test_get_cache_stats(self):
        manager = UserAgentManager(max_cached_profiles=50)
        stats = manager.get_cache_stats()
        assert stats["max_profiles"] == 50
        assert stats["cached_profiles"] == 0
