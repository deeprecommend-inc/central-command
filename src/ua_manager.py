"""
User Agent Manager - Manages browser fingerprints and user agents
"""
import random
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional
from fake_useragent import UserAgent
from loguru import logger


@dataclass
class BrowserProfile:
    """Browser profile with consistent fingerprint settings"""

    user_agent: str
    viewport_width: int
    viewport_height: int
    locale: str
    timezone: str
    platform: str

    def to_playwright_context(self) -> dict:
        """Convert to Playwright browser context options"""
        return {
            "user_agent": self.user_agent,
            "viewport": {"width": self.viewport_width, "height": self.viewport_height},
            "locale": self.locale,
            "timezone_id": self.timezone,
        }


class LRUCache:
    """Simple LRU cache implementation using OrderedDict"""

    def __init__(self, max_size: int = 100):
        self._cache: OrderedDict = OrderedDict()
        self._max_size = max_size

    def get(self, key: str) -> Optional[any]:
        """Get item and move to end (most recently used)"""
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def set(self, key: str, value: any) -> None:
        """Set item, evicting oldest if at capacity"""
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            if len(self._cache) >= self._max_size:
                oldest = next(iter(self._cache))
                del self._cache[oldest]
                logger.debug(f"LRU evicted: {oldest}")
        self._cache[key] = value

    def delete(self, key: str) -> bool:
        """Delete item if exists"""
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def __contains__(self, key: str) -> bool:
        return key in self._cache

    def __len__(self) -> int:
        return len(self._cache)

    def clear(self) -> None:
        """Clear all cached items"""
        self._cache.clear()


class UserAgentManager:
    """Manages user agents and browser profiles with LRU caching"""

    MAX_CACHED_PROFILES = 100

    VIEWPORTS = [
        (1920, 1080),
        (1366, 768),
        (1536, 864),
        (1440, 900),
        (1280, 720),
        (2560, 1440),
    ]

    LOCALES = ["en-US", "en-GB", "de-DE", "fr-FR", "ja-JP", "es-ES"]

    TIMEZONES = [
        "America/New_York",
        "America/Los_Angeles",
        "Europe/London",
        "Europe/Berlin",
        "Asia/Tokyo",
        "Australia/Sydney",
    ]

    def __init__(self, max_cached_profiles: int = MAX_CACHED_PROFILES):
        self._ua = UserAgent()
        self._profiles = LRUCache(max_size=max_cached_profiles)

    def get_random_profile(self, session_id: Optional[str] = None) -> BrowserProfile:
        """Generate a random but consistent browser profile"""
        # If session_id provided and profile exists, return cached
        if session_id:
            cached = self._profiles.get(session_id)
            if cached:
                return cached

        # Generate new profile
        ua_string = self._ua.random
        viewport = random.choice(self.VIEWPORTS)
        locale = random.choice(self.LOCALES)
        timezone = random.choice(self.TIMEZONES)

        # Detect platform from UA
        platform = "Windows"
        if "Mac" in ua_string:
            platform = "MacIntel"
        elif "Linux" in ua_string:
            platform = "Linux x86_64"

        profile = BrowserProfile(
            user_agent=ua_string,
            viewport_width=viewport[0],
            viewport_height=viewport[1],
            locale=locale,
            timezone=timezone,
            platform=platform,
        )

        # Cache if session_id provided
        if session_id:
            self._profiles.set(session_id, profile)
            logger.debug(f"Created browser profile for session {session_id}")

        return profile

    def get_chrome_profile(self, session_id: Optional[str] = None) -> BrowserProfile:
        """Get a Chrome-specific profile"""
        if session_id:
            cached = self._profiles.get(session_id)
            if cached:
                return cached

        ua_string = self._ua.chrome
        viewport = random.choice(self.VIEWPORTS)
        locale = random.choice(self.LOCALES)
        timezone = random.choice(self.TIMEZONES)

        profile = BrowserProfile(
            user_agent=ua_string,
            viewport_width=viewport[0],
            viewport_height=viewport[1],
            locale=locale,
            timezone=timezone,
            platform="Windows",
        )

        if session_id:
            self._profiles.set(session_id, profile)

        return profile

    def clear_session(self, session_id: str) -> None:
        """Clear cached profile for session"""
        if self._profiles.delete(session_id):
            logger.debug(f"Cleared profile for session {session_id}")

    def clear_all(self) -> None:
        """Clear all cached profiles"""
        self._profiles.clear()
        logger.debug("Cleared all cached profiles")

    def get_cache_stats(self) -> dict:
        """Get cache statistics"""
        return {
            "cached_profiles": len(self._profiles),
            "max_profiles": self._profiles._max_size,
        }
