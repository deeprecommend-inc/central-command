"""
Tests for human_timing module

Spec coverage:
  random_delay(min_s, max_s) -> float
    - Log-normal distribution, clamped to [min_s, max_s]
    - CV ~0.53 satisfying H_T1 >= 0.20
    - Default args (0.5, 3.0)
    - Edge: min == max, narrow range, wide range, zero-width
  action_throttle(action_count, elapsed_s) -> float
    - Target rate: 18 actions/min
    - Returns 0.0 when under limit
    - Returns positive delay when over limit
    - Guards: count <= 0, elapsed <= 0
    - Exact math verification
  dwell_time(base_s) -> float
    - Gamma(shape=2, scale=base_s/2), minimum 1.0s
    - Default args (3.0)
    - Edge: very small base_s, large base_s
  human_sleep(min_s, max_s) -> float
    - Async wrapper around random_delay + asyncio.sleep
    - Returns actual delay used
    - Default args
"""
import asyncio
import math
import time
import pytest
from src.human_timing import random_delay, action_throttle, dwell_time, human_sleep


# ---------------------------------------------------------------------------
# random_delay
# ---------------------------------------------------------------------------

class TestRandomDelay:
    def test_within_bounds(self):
        for _ in range(200):
            d = random_delay(0.5, 3.0)
            assert 0.5 <= d <= 3.0

    def test_custom_bounds(self):
        for _ in range(100):
            d = random_delay(1.0, 10.0)
            assert 1.0 <= d <= 10.0

    def test_default_args(self):
        """Default (0.5, 3.0) should work without arguments"""
        d = random_delay()
        assert 0.5 <= d <= 3.0

    def test_cv_above_threshold(self):
        """CV should be >= 0.20 (H_T1 threshold) over many samples"""
        samples = [random_delay(0.5, 5.0) for _ in range(500)]
        mean = sum(samples) / len(samples)
        variance = sum((x - mean) ** 2 for x in samples) / len(samples)
        cv = math.sqrt(variance) / mean if mean > 0 else 0
        assert cv >= 0.20, f"CV={cv:.4f} < 0.20"

    def test_min_equals_max(self):
        """When min == max, output must be that value"""
        for val in [0.0, 1.0, 5.5, 100.0]:
            d = random_delay(val, val)
            assert d == val

    def test_narrow_range(self):
        """Very narrow range: all values still within bounds"""
        for _ in range(100):
            d = random_delay(2.0, 2.01)
            assert 2.0 <= d <= 2.01

    def test_wide_range(self):
        """Wide range: values span the range"""
        samples = [random_delay(0.1, 100.0) for _ in range(500)]
        # Log-normal with midpoint ~50 clusters above 5; check spread exists
        assert min(samples) < max(samples), "Expected variation in samples"
        assert max(samples) > 10.0, "Expected some larger values"
        assert min(samples) >= 0.1, "All values must respect lower bound"

    def test_distribution_right_skewed(self):
        """Log-normal is right-skewed: median < mean"""
        samples = [random_delay(0.5, 20.0) for _ in range(1000)]
        mean = sum(samples) / len(samples)
        sorted_s = sorted(samples)
        median = sorted_s[len(sorted_s) // 2]
        assert median <= mean, f"Expected right-skewed: median={median:.3f} should be <= mean={mean:.3f}"

    def test_repeated_calls_vary(self):
        """Consecutive calls produce different values (not deterministic)"""
        values = [random_delay(0.5, 5.0) for _ in range(20)]
        unique = len(set(values))
        assert unique >= 10, f"Only {unique}/20 unique values -- too deterministic"

    def test_stability_over_large_sample(self):
        """Mean should be roughly near midpoint over large sample"""
        samples = [random_delay(1.0, 5.0) for _ in range(2000)]
        mean = sum(samples) / len(samples)
        # Log-normal shifts mean up from geometric midpoint, but should stay in range
        assert 1.5 <= mean <= 4.5, f"Mean={mean:.3f} outside reasonable range"


# ---------------------------------------------------------------------------
# action_throttle
# ---------------------------------------------------------------------------

class TestActionThrottle:
    def test_low_rate_no_delay(self):
        # 5 actions in 60s = 5/min, well under 18/min
        assert action_throttle(5, 60.0) == 0.0

    def test_high_rate_returns_delay(self):
        # 30 actions in 30s = 60/min, way over 18/min
        delay = action_throttle(30, 30.0)
        assert delay > 0.0

    def test_zero_actions(self):
        assert action_throttle(0, 10.0) == 0.0

    def test_zero_elapsed(self):
        assert action_throttle(5, 0.0) == 0.0

    def test_negative_action_count(self):
        assert action_throttle(-1, 10.0) == 0.0

    def test_negative_elapsed(self):
        assert action_throttle(5, -1.0) == 0.0

    def test_both_negative(self):
        assert action_throttle(-5, -10.0) == 0.0

    def test_exactly_at_limit(self):
        # 18 actions in 60s = 18/min, exactly at limit
        assert action_throttle(18, 60.0) == 0.0

    def test_slightly_over_limit(self):
        # 19 actions in 60s = 19/min, just over 18/min
        delay = action_throttle(19, 60.0)
        assert delay > 0.0

    def test_exact_delay_calculation(self):
        """Verify the exact math: needed_elapsed = (count / 18) * 60"""
        # 36 actions in 60s = 36/min
        # needed_elapsed = (36 / 18) * 60 = 120s
        # delay = 120 - 60 = 60s
        delay = action_throttle(36, 60.0)
        assert abs(delay - 60.0) < 0.01, f"Expected 60.0, got {delay}"

    def test_single_action_fast(self):
        """1 action in 0.1s = 600/min -- should throttle"""
        delay = action_throttle(1, 0.1)
        assert delay > 0.0

    def test_single_action_slow(self):
        """1 action in 10s = 6/min -- no throttle"""
        assert action_throttle(1, 10.0) == 0.0

    def test_large_action_count(self):
        """Very large count with proportional time should not throttle"""
        # 1800 actions in 6000s = 18/min
        assert action_throttle(1800, 6000.0) == 0.0

    def test_large_action_count_fast(self):
        """Very large count in short time should produce large delay"""
        delay = action_throttle(1000, 10.0)
        assert delay > 3000.0  # Needs > 3333s total


# ---------------------------------------------------------------------------
# dwell_time
# ---------------------------------------------------------------------------

class TestDwellTime:
    def test_minimum_floor(self):
        """All values must be >= 1.0s regardless of base_s"""
        for _ in range(200):
            d = dwell_time(3.0)
            assert d >= 1.0

    def test_default_args(self):
        """Default (3.0) should work without arguments"""
        d = dwell_time()
        assert d >= 1.0

    def test_reasonable_mean_default(self):
        """Gamma(2, 1.5) has theoretical mean=3.0"""
        samples = [dwell_time(3.0) for _ in range(500)]
        mean = sum(samples) / len(samples)
        assert 2.0 <= mean <= 5.0, f"Mean dwell={mean:.2f} outside expected range"

    def test_custom_base_higher(self):
        """Higher base_s should produce higher mean"""
        samples_low = [dwell_time(3.0) for _ in range(300)]
        samples_high = [dwell_time(15.0) for _ in range(300)]
        mean_low = sum(samples_low) / len(samples_low)
        mean_high = sum(samples_high) / len(samples_high)
        assert mean_high > mean_low, f"mean_high={mean_high:.2f} should be > mean_low={mean_low:.2f}"

    def test_very_small_base(self):
        """Very small base_s: floor at 1.0s should dominate"""
        samples = [dwell_time(0.1) for _ in range(100)]
        # Most values should be near 1.0 due to floor
        near_floor = sum(1 for s in samples if s < 1.5)
        assert near_floor > 50, f"Only {near_floor}/100 near floor with base_s=0.1"

    def test_very_large_base(self):
        """Very large base_s should still produce values"""
        d = dwell_time(1000.0)
        assert d >= 1.0
        assert d < 10000.0  # Reasonable upper bound

    def test_positive_skew(self):
        """Gamma distribution should be right-skewed"""
        samples = sorted([dwell_time(5.0) for _ in range(1000)])
        median = samples[len(samples) // 2]
        mean = sum(samples) / len(samples)
        assert median <= mean * 1.1, "Expected right-skew (median <= mean)"


# ---------------------------------------------------------------------------
# human_sleep
# ---------------------------------------------------------------------------

class TestHumanSleep:
    @pytest.mark.asyncio
    async def test_returns_delay_value(self):
        delay = await human_sleep(0.01, 0.05)
        assert 0.01 <= delay <= 0.05

    @pytest.mark.asyncio
    async def test_actually_sleeps(self):
        start = time.time()
        await human_sleep(0.05, 0.1)
        elapsed = time.time() - start
        assert elapsed >= 0.04  # Allow small timing tolerance

    @pytest.mark.asyncio
    async def test_default_args(self):
        """Default args should work and return within (0.5, 3.0)"""
        delay = await human_sleep()
        assert 0.5 <= delay <= 3.0

    @pytest.mark.asyncio
    async def test_min_equals_max(self):
        delay = await human_sleep(0.02, 0.02)
        assert delay == 0.02

    @pytest.mark.asyncio
    async def test_multiple_sequential_calls(self):
        """Multiple calls produce varying delays"""
        delays = []
        for _ in range(10):
            d = await human_sleep(0.01, 0.05)
            delays.append(d)
        unique = len(set(round(d, 6) for d in delays))
        assert unique >= 5, f"Only {unique}/10 unique delays"
