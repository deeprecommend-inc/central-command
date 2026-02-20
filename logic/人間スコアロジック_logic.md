# Human-Likeness Score

Behavioral metrics to evaluate how human-like a browser session appears.

Collects raw events during browser automation and computes a composite score (0-100) across 5 categories: **Time**, **Engagement**, **Network**, **Behavior**, and **Consistency**.

Source: `src/human_score.py`

---

## Scoring Summary

| Composite Score | Judgment |
|-----------------|----------|
| >= 70           | PASS (human-like) |
| < 70            | FAIL (bot-like) |

---

## Metric Definitions

### Time (max 21 pts)

| ID   | Name                    | Threshold        | Points | Description |
|------|-------------------------|------------------|--------|-------------|
| H_T1 | Event Interval CV       | CV >= 0.20       | 10     | Coefficient of variation of time intervals between consecutive actions. Natural humans have irregular timing (CV 0.2-1.5). Uniform intervals indicate automation. |
| H_T2 | Continuous Operation    | <= 180 min       | 6      | Total session duration. Sessions exceeding 3 hours without breaks are unnatural. |
| H_T3 | Night Ratio             | <= 0.50          | 5      | Proportion of actions occurring between 00:00-06:00. Excessive night activity is suspicious. Target-region dependent. |

### Engagement (max 24 pts)

| ID   | Name              | Threshold        | Points | Description |
|------|-------------------|------------------|--------|-------------|
| H_E1 | Dwell Skewness   | -1 to 2.5        | 8      | Skewness of page dwell time distribution. Extreme skew indicates unnatural browsing patterns. Requires >= 3 page visits. |
| H_E2 | Completion Rate   | 0.20 to 0.85    | 8      | Ratio of pages where content was fully consumed. Humans neither complete everything nor skip everything. |
| H_E3 | Bounce Rate       | <= 0.60          | 8      | Ratio of immediate bounces. Excessive bouncing suggests automated navigation without engagement. |

### Network (max 22 pts)

| ID   | Name                  | Threshold   | Points | Description |
|------|-----------------------|-------------|--------|-------------|
| H_N1 | IP Sharing Density   | <= 15       | 6      | Maximum number of sessions from the same IP address. Overcrowded IPs (shared proxies) are flagged. NAT environments considered. |
| H_N2 | Geo Jumps            | <= 2 / 24h  | 6      | Rapid country changes within a 24-hour window. More than 2 geo jumps is physically impossible without VPN. Travel exceptions apply. |
| H_N3 | Fingerprint Cluster  | <= 8        | 10     | Maximum sessions sharing the same browser fingerprint hash. Reusing identical fingerprints across many sessions is a strong bot signal. |

### Behavior (max 26 pts)

| ID   | Name                 | Threshold    | Points | Description |
|------|----------------------|--------------|--------|-------------|
| H_G1 | Action Speed        | <= 20 / min  | 10     | Actions per minute. Exceeding 20 APM is faster than typical human interaction. Platform dependent. |
| H_G2 | Action Diversity    | >= 0.30      | 8      | Ratio of unique action types to total actions. Humans use varied actions (click, scroll, type, navigate, search, save). Monotonous sequences are bot-like. |
| H_G3 | Transition Entropy  | >= 1.2       | 8      | Shannon entropy of action-type transition pairs. Low entropy means repetitive action sequences. Natural range is 1.2-2.5. Requires >= 2 actions. |

### Consistency (max 13 pts)

| ID   | Name                    | Threshold    | Points | Description |
|------|-------------------------|--------------|--------|-------------|
| H_C1 | CTR-Dwell Consistency  | \|Z\| <= 2   | 8      | Z-score difference between click-through rate and dwell time distributions. A large gap (high CTR but low dwell, or vice versa) indicates inconsistent engagement. Requires >= 3 page visits. |
| H_C2 | Outcome Distribution   | <= 0.80      | 5      | Maximum share of a single outcome type (success, failure, partial, skip). Real sessions produce varied outcomes, not 100% success or 100% failure. |

---

## Max Score Breakdown

| Category    | Max Points |
|-------------|------------|
| Time        | 21         |
| Engagement  | 24         |
| Network     | 22         |
| Behavior    | 26         |
| Consistency | 13         |
| **Total**   | **106**    |

Pass threshold: 70 points (absolute, not percentage).

---

## Usage

```python
from src.human_score import HumanScoreTracker

tracker = HumanScoreTracker()

# Record actions during browser session
tracker.record_action("click")
tracker.record_action("scroll")
tracker.record_action("type")

# Record page visits
tracker.record_page_visit("https://example.com", dwell_sec=12.5, completed=False, bounced=False, clicked=True)

# Record network info
tracker.record_ip("203.0.113.1", country="JP", fingerprint_hash="abc123")

# Record outcomes
tracker.record_outcome("success")

# Compute score
report = tracker.compute()
print(report)              # Human-readable report
print(report.summary())    # Dict for programmatic use
print(report.is_human)     # True if score >= 70
```

---

## Data Collection Methods

| Method | Parameters | Purpose |
|--------|-----------|---------|
| `record_action(action_type, timestamp?)` | Action type string (click, scroll, type, navigate, search, save) | Feeds H_T1, H_T3, H_G1, H_G2, H_G3 |
| `record_page_visit(url, dwell_sec, completed?, bounced?, clicked?)` | Page engagement data | Feeds H_E1, H_E2, H_E3, H_C1 |
| `record_ip(ip, country?, fingerprint_hash?)` | Network identity data | Feeds H_N1, H_N2, H_N3 |
| `record_outcome(outcome_type)` | Outcome label (success, failure, partial, skip) | Feeds H_C2 |

---

## Edge Cases

- Metrics with insufficient data default to pass (0 penalty) for: H_T3, H_E1, H_E3, H_N1, H_N2, H_N3, H_C1, H_C2
- Metrics with insufficient data default to fail (0 points) for: H_T1, H_E2, H_G1 (passes with 0 actions), H_G2, H_G3
- H_T2 measures wall-clock time from tracker creation, not cumulative action time
