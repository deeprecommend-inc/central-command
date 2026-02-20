"""Tests for human-likeness score module"""
import time
import pytest
from src.human_score import HumanScoreTracker, HumanScoreReport, MetricResult


class TestHumanScoreTracker:
    """Test all 14 metrics and composite score"""

    def _make_tracker_with_natural_data(self) -> HumanScoreTracker:
        """Create a tracker with realistic human-like data"""
        t = HumanScoreTracker()
        base = t._start

        # 25 actions with natural timing variation (~5-40s intervals)
        action_types = ["click", "scroll", "type", "navigate", "search", "hover", "wait"]
        ts = base
        for i in range(25):
            ts += 5 + (i % 7) * 5 + (i * 3 % 11)
            t.record_action(action_types[i % len(action_types)], timestamp=ts)

        # 8 page visits with varied engagement
        for i in range(8):
            t.record_page_visit(
                url=f"https://example.com/page{i}",
                dwell_sec=10 + i * 12,
                completed=(i % 3 != 0),
                bounced=(i == 7),
                clicked=(i % 2 == 0),
            )

        # 2 IPs, same country
        t.record_ip("198.51.100.1", "us", "fp_abc")
        t.record_ip("198.51.100.2", "us", "fp_def")

        # Mixed outcomes
        for outcome in ["success", "partial", "success", "skip"]:
            t.record_outcome(outcome)

        return t

    def test_compute_returns_report(self):
        t = self._make_tracker_with_natural_data()
        report = t.compute()
        assert isinstance(report, HumanScoreReport)
        assert len(report.metrics) == 14
        assert report.max_score > 0

    def test_all_metric_ids_present(self):
        t = self._make_tracker_with_natural_data()
        report = t.compute()
        ids = {m.metric_id for m in report.metrics}
        expected = {
            "H_T1", "H_T2", "H_T3",
            "H_E1", "H_E2", "H_E3",
            "H_N1", "H_N2", "H_N3",
            "H_G1", "H_G2", "H_G3",
            "H_C1", "H_C2",
        }
        assert ids == expected

    def test_natural_data_passes(self):
        t = self._make_tracker_with_natural_data()
        report = t.compute()
        assert report.is_human
        assert report.total_score >= 70

    def test_empty_tracker(self):
        t = HumanScoreTracker()
        report = t.compute()
        assert isinstance(report, HumanScoreReport)
        assert report.max_score > 0

    # -- H_T1: Event Interval CV --

    def test_h_t1_uniform_intervals_fail(self):
        t = HumanScoreTracker()
        base = t._start
        for i in range(20):
            t.record_action("click", timestamp=base + i * 10.0)  # exactly 10s apart
        report = t.compute()
        h_t1 = next(m for m in report.metrics if m.metric_id == "H_T1")
        assert h_t1.value < 0.01  # CV near 0
        assert not h_t1.threshold_pass

    def test_h_t1_varied_intervals_pass(self):
        t = HumanScoreTracker()
        base = t._start
        intervals = [3, 12, 5, 25, 8, 40, 2, 18, 7, 30]
        ts = base
        for iv in intervals:
            ts += iv
            t.record_action("click", timestamp=ts)
        report = t.compute()
        h_t1 = next(m for m in report.metrics if m.metric_id == "H_T1")
        assert h_t1.value >= 0.20
        assert h_t1.threshold_pass

    # -- H_T2: Continuous operation --

    def test_h_t2_short_session(self):
        t = HumanScoreTracker()
        report = t.compute()
        h_t2 = next(m for m in report.metrics if m.metric_id == "H_T2")
        assert h_t2.threshold_pass
        assert h_t2.points == 6

    # -- H_T3: Night ratio --

    def test_h_t3_daytime_pass(self):
        t = HumanScoreTracker()
        base = t._start
        for i in range(10):
            # Force daytime timestamps (noon)
            import datetime
            dt = datetime.datetime.now().replace(hour=12, minute=0, second=0)
            ts = dt.timestamp() + i * 60
            t.record_action("click", timestamp=ts)
        report = t.compute()
        h_t3 = next(m for m in report.metrics if m.metric_id == "H_T3")
        assert h_t3.threshold_pass

    # -- H_E1: Dwell skewness --

    def test_h_e1_balanced_dwells_pass(self):
        t = HumanScoreTracker()
        for i in range(10):
            t.record_page_visit(f"https://x.com/{i}", dwell_sec=20 + i * 5)
        report = t.compute()
        h_e1 = next(m for m in report.metrics if m.metric_id == "H_E1")
        assert h_e1.threshold_pass

    # -- H_E2: Completion rate --

    def test_h_e2_all_complete_fail(self):
        t = HumanScoreTracker()
        for i in range(5):
            t.record_page_visit(f"https://x.com/{i}", dwell_sec=30, completed=True)
        report = t.compute()
        h_e2 = next(m for m in report.metrics if m.metric_id == "H_E2")
        assert not h_e2.threshold_pass  # 1.0 > 0.85

    def test_h_e2_moderate_pass(self):
        t = HumanScoreTracker()
        for i in range(10):
            t.record_page_visit(f"https://x.com/{i}", dwell_sec=30, completed=(i < 5))
        report = t.compute()
        h_e2 = next(m for m in report.metrics if m.metric_id == "H_E2")
        assert h_e2.threshold_pass  # 0.5

    # -- H_E3: Bounce rate --

    def test_h_e3_high_bounce_fail(self):
        t = HumanScoreTracker()
        for i in range(10):
            t.record_page_visit(f"https://x.com/{i}", dwell_sec=1, bounced=True)
        report = t.compute()
        h_e3 = next(m for m in report.metrics if m.metric_id == "H_E3")
        assert not h_e3.threshold_pass

    # -- H_N1: IP density --

    def test_h_n1_overcrowded_ip_fail(self):
        t = HumanScoreTracker()
        for i in range(20):
            t.record_ip("1.2.3.4", "us", f"fp{i}")
        report = t.compute()
        h_n1 = next(m for m in report.metrics if m.metric_id == "H_N1")
        assert not h_n1.threshold_pass

    # -- H_N2: Geo jumps --

    def test_h_n2_rapid_jumps_fail(self):
        t = HumanScoreTracker()
        countries = ["us", "jp", "de", "fr", "au"]
        from src.human_score import _IPRecord
        base = time.time()
        for i, c in enumerate(countries):
            t._ips.append(_IPRecord(ip=f"1.2.3.{i}", country=c, fingerprint_hash=f"fp{i}", timestamp=base + i * 60))
        report = t.compute()
        h_n2 = next(m for m in report.metrics if m.metric_id == "H_N2")
        assert h_n2.value >= 3
        assert not h_n2.threshold_pass

    # -- H_N3: Fingerprint cluster --

    def test_h_n3_same_fingerprint_fail(self):
        t = HumanScoreTracker()
        for i in range(12):
            t.record_ip(f"1.2.3.{i}", "us", "same_fp")
        report = t.compute()
        h_n3 = next(m for m in report.metrics if m.metric_id == "H_N3")
        assert not h_n3.threshold_pass

    # -- H_G1: Action speed --

    def test_h_g1_too_fast_fail(self):
        t = HumanScoreTracker()
        base = t._start
        for i in range(100):
            t.record_action("click", timestamp=base + i * 0.5)  # 120/min
        report = t.compute()
        h_g1 = next(m for m in report.metrics if m.metric_id == "H_G1")
        assert not h_g1.threshold_pass

    def test_h_g1_normal_speed_pass(self):
        t = HumanScoreTracker()
        base = t._start
        for i in range(10):
            t.record_action("click", timestamp=base + i * 10)  # 6/min
        report = t.compute()
        h_g1 = next(m for m in report.metrics if m.metric_id == "H_G1")
        assert h_g1.threshold_pass

    # -- H_G2: Action diversity --

    def test_h_g2_single_type_fail(self):
        t = HumanScoreTracker()
        base = t._start
        for i in range(20):
            t.record_action("click", timestamp=base + i * 10)
        report = t.compute()
        h_g2 = next(m for m in report.metrics if m.metric_id == "H_G2")
        assert h_g2.value < 0.30
        assert not h_g2.threshold_pass

    # -- H_G3: Transition entropy --

    def test_h_g3_monotonous_fail(self):
        t = HumanScoreTracker()
        base = t._start
        for i in range(20):
            t.record_action("click", timestamp=base + i * 10)
        report = t.compute()
        h_g3 = next(m for m in report.metrics if m.metric_id == "H_G3")
        assert h_g3.value == 0.0  # all same transitions
        assert not h_g3.threshold_pass

    # -- H_C2: Outcome distribution --

    def test_h_c2_single_outcome_fail(self):
        t = HumanScoreTracker()
        for _ in range(10):
            t.record_outcome("success")
        report = t.compute()
        h_c2 = next(m for m in report.metrics if m.metric_id == "H_C2")
        assert h_c2.value == 1.0
        assert not h_c2.threshold_pass

    # -- Report output --

    def test_summary_dict(self):
        t = self._make_tracker_with_natural_data()
        report = t.compute()
        s = report.summary()
        assert "score" in s
        assert "max" in s
        assert "is_human" in s
        assert "metrics" in s
        assert "H_T1" in s["metrics"]

    def test_str_output(self):
        t = self._make_tracker_with_natural_data()
        report = t.compute()
        text = str(report)
        assert "Human Score:" in text
        assert "H_T1" in text
        assert "H_S0" not in text  # H_S0 is composite, not in individual metrics
