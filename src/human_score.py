"""
Human-Likeness Score - Behavioral metrics to evaluate how human-like a browser session appears.

Collects raw events during browser automation and computes a composite score (0-100)
across 5 categories: Time, Engagement, Network, Behavior, and Consistency.

Metric definitions:
  H_T1  Event interval CV         - Natural timing variation (CV >= 0.20)
  H_T2  Continuous operation time  - Not running too long continuously (<= 180 min)
  H_T3  Night-time ratio           - Activity not concentrated at night (<= 0.50)
  H_E1  Dwell time skewness        - No extreme dwell distribution bias (-1 to 2.5)
  H_E2  Completion rate             - Moderate content completion (0.20 to 0.85)
  H_E3  Immediate bounce rate       - Bounces not excessive (<= 0.60)
  H_N1  IP sharing density          - Not using overcrowded IPs (<= 15)
  H_N2  Geo jumps                   - No rapid country changes (<= 2 per 24h)
  H_N3  Fingerprint cluster size    - Same fingerprint not reused too much (<= 8)
  H_G1  Action speed                - Within human limits (<= 20 per minute)
  H_G2  Action diversity            - Multiple action types present (>= 0.30)
  H_G3  Transition entropy          - Non-monotonous action sequences (>= 1.2)
  H_C1  CTR-dwell consistency       - Z-score gap not excessive (|Z| <= 2)
  H_C2  Outcome distribution        - Outcomes not concentrated on single type (<= 0.80)
  H_S0  Human score (composite)     - Weighted sum of all above (>= 70 = human)
"""
import math
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MetricResult:
    """Result of a single metric evaluation"""
    metric_id: str
    name: str
    category: str
    value: float
    threshold_pass: bool
    points: int
    max_points: int
    note: str = ""


@dataclass
class HumanScoreReport:
    """Complete human-likeness score report"""
    metrics: list[MetricResult]
    total_score: int
    max_score: int
    is_human: bool

    def summary(self) -> dict:
        return {
            "score": self.total_score,
            "max": self.max_score,
            "is_human": self.is_human,
            "metrics": {m.metric_id: {"value": round(m.value, 4), "pass": m.threshold_pass, "points": m.points} for m in self.metrics},
        }

    def __str__(self) -> str:
        lines = [f"Human Score: {self.total_score}/{self.max_score} ({'PASS' if self.is_human else 'FAIL'})"]
        by_cat: dict[str, list[MetricResult]] = {}
        for m in self.metrics:
            by_cat.setdefault(m.category, []).append(m)
        for cat, items in by_cat.items():
            lines.append(f"  [{cat}]")
            for m in items:
                flag = "OK" if m.threshold_pass else "NG"
                lines.append(f"    {m.metric_id} {m.name}: {m.value:.4f} [{flag}] +{m.points}/{m.max_points}")
                if m.note:
                    lines.append(f"      {m.note}")
        return "\n".join(lines)


@dataclass
class _ActionEvent:
    action_type: str
    timestamp: float


@dataclass
class _PageVisit:
    url: str
    dwell_sec: float
    completed: bool
    bounced: bool
    clicked: bool


@dataclass
class _IPRecord:
    ip: str
    country: str
    fingerprint_hash: str
    timestamp: float


class HumanScoreTracker:
    """
    Collects behavioral events during a browser session and computes
    a human-likeness score across 14 metrics.

    Usage:
        tracker = HumanScoreTracker()
        tracker.record_action("click")
        tracker.record_action("scroll")
        tracker.record_page_visit("https://...", dwell_sec=12.5, completed=False, bounced=False)
        report = tracker.compute()
        print(report)
    """

    def __init__(self, session_start: Optional[float] = None):
        self._start = session_start or time.time()
        self._actions: list[_ActionEvent] = []
        self._pages: list[_PageVisit] = []
        self._ips: list[_IPRecord] = []
        self._outcomes: list[str] = []

    # -- Recording methods --

    def record_action(self, action_type: str, timestamp: Optional[float] = None) -> None:
        """Record a browser action (click, scroll, type, navigate, search, save, etc.)"""
        self._actions.append(_ActionEvent(
            action_type=action_type,
            timestamp=timestamp or time.time(),
        ))

    def record_page_visit(
        self,
        url: str,
        dwell_sec: float,
        completed: bool = False,
        bounced: bool = False,
        clicked: bool = False,
    ) -> None:
        """Record a page visit with engagement metrics"""
        self._pages.append(_PageVisit(
            url=url, dwell_sec=dwell_sec, completed=completed,
            bounced=bounced, clicked=clicked,
        ))

    def record_ip(self, ip: str, country: str = "", fingerprint_hash: str = "") -> None:
        """Record IP address and fingerprint used for a request"""
        self._ips.append(_IPRecord(
            ip=ip, country=country, fingerprint_hash=fingerprint_hash,
            timestamp=time.time(),
        ))

    def record_outcome(self, outcome_type: str) -> None:
        """Record a task outcome (success, failure, partial, skip, etc.)"""
        self._outcomes.append(outcome_type)

    # -- Computation --

    def compute(self) -> HumanScoreReport:
        """Compute all metrics and return a HumanScoreReport"""
        results = [
            self._h_t1(),
            self._h_t2(),
            self._h_t3(),
            self._h_e1(),
            self._h_e2(),
            self._h_e3(),
            self._h_n1(),
            self._h_n2(),
            self._h_n3(),
            self._h_g1(),
            self._h_g2(),
            self._h_g3(),
            self._h_c1(),
            self._h_c2(),
        ]
        total = sum(r.points for r in results)
        max_score = sum(r.max_points for r in results)
        return HumanScoreReport(
            metrics=results,
            total_score=total,
            max_score=max_score,
            is_human=total >= 70,
        )

    # -- Time metrics --

    def _h_t1(self) -> MetricResult:
        """H_T1: Event interval coefficient of variation (CV >= 0.20 is natural)"""
        intervals = self._get_intervals()
        if len(intervals) < 2:
            return MetricResult("H_T1", "Event Interval CV", "Time", 0.0, False, 0, 10, "Not enough events")
        mean = sum(intervals) / len(intervals)
        if mean == 0:
            return MetricResult("H_T1", "Event Interval CV", "Time", 0.0, False, 0, 10, "Zero mean interval")
        variance = sum((x - mean) ** 2 for x in intervals) / len(intervals)
        cv = math.sqrt(variance) / mean
        passed = cv >= 0.20
        return MetricResult("H_T1", "Event Interval CV", "Time", cv, passed, 10 if passed else 0, 10,
                            "CV 0.2-1.5 is natural range")

    def _h_t2(self) -> MetricResult:
        """H_T2: Continuous operation time (<= 180 min)"""
        duration_min = (time.time() - self._start) / 60.0
        passed = duration_min <= 180
        return MetricResult("H_T2", "Continuous Operation", "Time", duration_min, passed, 6 if passed else 0, 6)

    def _h_t3(self) -> MetricResult:
        """H_T3: Night-time activity ratio (<= 0.50)"""
        if not self._actions:
            return MetricResult("H_T3", "Night Ratio", "Time", 0.0, True, 5, 5, "No actions recorded")
        night_count = 0
        for a in self._actions:
            import datetime
            hour = datetime.datetime.fromtimestamp(a.timestamp).hour
            if 0 <= hour < 6:
                night_count += 1
        ratio = night_count / len(self._actions) if self._actions else 0
        passed = ratio <= 0.50
        return MetricResult("H_T3", "Night Ratio", "Time", ratio, passed, 5 if passed else 0, 5,
                            "Target region dependent")

    # -- Engagement metrics --

    def _h_e1(self) -> MetricResult:
        """H_E1: Dwell time skewness (-1 to 2.5 is natural)"""
        dwells = [p.dwell_sec for p in self._pages]
        if len(dwells) < 3:
            return MetricResult("H_E1", "Dwell Skewness", "Engagement", 0.0, True, 8, 8,
                                "Not enough page visits for skewness")
        n = len(dwells)
        mean = sum(dwells) / n
        variance = sum((x - mean) ** 2 for x in dwells) / n
        std = math.sqrt(variance) if variance > 0 else 0
        if std == 0:
            skew = 0.0
        else:
            skew = (sum((x - mean) ** 3 for x in dwells) / n) / (std ** 3)
        passed = -1 <= skew <= 2.5
        return MetricResult("H_E1", "Dwell Skewness", "Engagement", skew, passed, 8 if passed else 0, 8,
                            "Short video content uses different criteria")

    def _h_e2(self) -> MetricResult:
        """H_E2: Completion rate (0.20 to 0.85 is natural spread)"""
        if not self._pages:
            return MetricResult("H_E2", "Completion Rate", "Engagement", 0.0, False, 0, 8, "No page visits")
        completed = sum(1 for p in self._pages if p.completed)
        rate = completed / len(self._pages)
        passed = 0.20 <= rate <= 0.85
        return MetricResult("H_E2", "Completion Rate", "Engagement", rate, passed, 8 if passed else 0, 8,
                            "Content dependent")

    def _h_e3(self) -> MetricResult:
        """H_E3: Immediate bounce rate (<= 0.60)"""
        if not self._pages:
            return MetricResult("H_E3", "Bounce Rate", "Engagement", 0.0, True, 8, 8, "No page visits")
        bounced = sum(1 for p in self._pages if p.bounced)
        rate = bounced / len(self._pages)
        passed = rate <= 0.60
        return MetricResult("H_E3", "Bounce Rate", "Engagement", rate, passed, 8 if passed else 0, 8,
                            "Ad traffic uses different correction")

    # -- Network metrics --

    def _h_n1(self) -> MetricResult:
        """H_N1: IP sharing density (<= 15 sessions per IP)"""
        if not self._ips:
            return MetricResult("H_N1", "IP Density", "Network", 0, True, 6, 6, "No IP data")
        ip_counts = Counter(r.ip for r in self._ips)
        max_density = max(ip_counts.values())
        passed = max_density <= 15
        return MetricResult("H_N1", "IP Density", "Network", float(max_density), passed, 6 if passed else 0, 6,
                            "NAT considered")

    def _h_n2(self) -> MetricResult:
        """H_N2: Geo jumps - rapid country changes (<= 2 per 24h)"""
        if len(self._ips) < 2:
            return MetricResult("H_N2", "Geo Jumps", "Network", 0, True, 6, 6, "Not enough IP data")
        sorted_ips = sorted(self._ips, key=lambda r: r.timestamp)
        jumps = 0
        window_start = sorted_ips[0].timestamp
        for i in range(1, len(sorted_ips)):
            if sorted_ips[i].country and sorted_ips[i - 1].country:
                if sorted_ips[i].country != sorted_ips[i - 1].country:
                    if (sorted_ips[i].timestamp - window_start) <= 86400:
                        jumps += 1
        passed = jumps <= 2
        return MetricResult("H_N2", "Geo Jumps", "Network", float(jumps), passed, 6 if passed else 0, 6,
                            "Travel exception applies")

    def _h_n3(self) -> MetricResult:
        """H_N3: Fingerprint cluster size (<= 8 sessions per fingerprint)"""
        if not self._ips:
            return MetricResult("H_N3", "Fingerprint Cluster", "Network", 0, True, 10, 10, "No fingerprint data")
        fp_counts = Counter(r.fingerprint_hash for r in self._ips if r.fingerprint_hash)
        if not fp_counts:
            return MetricResult("H_N3", "Fingerprint Cluster", "Network", 0, True, 10, 10, "No fingerprint hashes")
        max_cluster = max(fp_counts.values())
        passed = max_cluster <= 8
        return MetricResult("H_N3", "Fingerprint Cluster", "Network", float(max_cluster), passed, 10 if passed else 0, 10,
                            "Hash-based recommended")

    # -- Behavior metrics --

    def _h_g1(self) -> MetricResult:
        """H_G1: Action speed (<= 20 actions per minute)"""
        if not self._actions:
            return MetricResult("H_G1", "Action Speed", "Behavior", 0.0, True, 10, 10, "No actions")
        sorted_actions = sorted(self._actions, key=lambda a: a.timestamp)
        span = sorted_actions[-1].timestamp - sorted_actions[0].timestamp
        duration_min = span / 60.0 if span > 0 else 1 / 60  # minimum 1 second
        apm = len(self._actions) / duration_min
        passed = apm <= 20
        return MetricResult("H_G1", "Action Speed", "Behavior", apm, passed, 10 if passed else 0, 10,
                            "Platform dependent")

    def _h_g2(self) -> MetricResult:
        """H_G2: Action diversity - unique action type ratio (>= 0.30)"""
        if not self._actions:
            return MetricResult("H_G2", "Action Diversity", "Behavior", 0.0, False, 0, 8, "No actions")
        types = set(a.action_type for a in self._actions)
        # Diversity = unique types / expected variety (cap at known action types count)
        # Use Shannon diversity index alternative: unique / total (capped)
        diversity = len(types) / max(len(self._actions), 1)
        # Clamp to 1.0 max
        diversity = min(diversity, 1.0)
        passed = diversity >= 0.30
        return MetricResult("H_G2", "Action Diversity", "Behavior", diversity, passed, 8 if passed else 0, 8,
                            "browse + search + save etc.")

    def _h_g3(self) -> MetricResult:
        """H_G3: Transition entropy - Shannon entropy of action type transitions (>= 1.2)"""
        if len(self._actions) < 2:
            return MetricResult("H_G3", "Transition Entropy", "Behavior", 0.0, False, 0, 8,
                                "Not enough actions for transition analysis")
        transitions: Counter = Counter()
        for i in range(len(self._actions) - 1):
            pair = (self._actions[i].action_type, self._actions[i + 1].action_type)
            transitions[pair] += 1
        total = sum(transitions.values())
        entropy = 0.0
        for count in transitions.values():
            p = count / total
            if p > 0:
                entropy -= p * math.log2(p)
        passed = entropy >= 1.2
        return MetricResult("H_G3", "Transition Entropy", "Behavior", entropy, passed, 8 if passed else 0, 8,
                            "1.2-2.5 is natural range")

    # -- Consistency metrics --

    def _h_c1(self) -> MetricResult:
        """H_C1: CTR vs dwell time consistency (|Z-score diff| <= 2)"""
        if len(self._pages) < 3:
            return MetricResult("H_C1", "CTR-Dwell Consistency", "Consistency", 0.0, True, 8, 8,
                                "Not enough data for Z-score")
        # CTR: click-through rate per page
        ctrs = [1.0 if p.clicked else 0.0 for p in self._pages]
        dwells = [p.dwell_sec for p in self._pages]

        z_ctr = self._z_score_mean(ctrs)
        z_dwell = self._z_score_mean(dwells)

        if z_ctr is None or z_dwell is None:
            return MetricResult("H_C1", "CTR-Dwell Consistency", "Consistency", 0.0, True, 8, 8,
                                "Insufficient variance for Z-score")

        diff = abs(z_ctr - z_dwell)
        passed = diff <= 2
        return MetricResult("H_C1", "CTR-Dwell Consistency", "Consistency", diff, passed, 8 if passed else 0, 8,
                            "Population update needed")

    def _h_c2(self) -> MetricResult:
        """H_C2: Outcome distribution - max single outcome share (<= 0.80)"""
        if not self._outcomes:
            return MetricResult("H_C2", "Outcome Distribution", "Consistency", 0.0, True, 5, 5,
                                "No outcomes recorded")
        counts = Counter(self._outcomes)
        max_share = max(counts.values()) / len(self._outcomes)
        passed = max_share <= 0.80
        return MetricResult("H_C2", "Outcome Distribution", "Consistency", max_share, passed, 5 if passed else 0, 5,
                            "Promo periods use different threshold")

    # -- Helpers --

    def _get_intervals(self) -> list[float]:
        """Get time intervals between consecutive actions"""
        if len(self._actions) < 2:
            return []
        sorted_actions = sorted(self._actions, key=lambda a: a.timestamp)
        return [sorted_actions[i].timestamp - sorted_actions[i - 1].timestamp
                for i in range(1, len(sorted_actions))]

    @staticmethod
    def _z_score_mean(values: list[float]) -> Optional[float]:
        """Compute Z-score of the mean (how far mean is from expected = 0 in standard units)"""
        if len(values) < 2:
            return None
        n = len(values)
        mean = sum(values) / n
        variance = sum((x - mean) ** 2 for x in values) / n
        std = math.sqrt(variance)
        if std == 0:
            return None
        return mean / std
