# Google Account Creation Without Phone Number

Procedure and automation logic for creating Google accounts without phone number verification.

Based on 2025 analysis of Google's account creation flow.

---

## Overview

Google accounts can be created without phone number input in most cases. The phone number field is optional and can be skipped. However, certain conditions trigger mandatory phone verification that cannot be bypassed.

---

## When Phone Number Can Be Skipped

| Condition | Skip Possible |
|-----------|---------------|
| First-time account creation | Yes (most cases) |
| New device / new IP address | Yes |
| Recovery email provided | Yes |
| Multiple accounts from same IP in short time | No |
| Robot detection triggered | No |
| Same phone number used 4-5+ times | No (number blocked) |

---

## Creation Procedure (PC)

1. Access Google account creation page
2. Enter required fields: name, desired email address, password
3. Leave phone number field empty (skip)
4. Enter a recovery email address as alternative verification
5. Enter age, agree to terms of service
6. Complete creation

## Creation Procedure (Smartphone - iPhone / Android)

1. Open Settings > "Add Account"
2. Enter required fields: name, username, password
3. When phone number field appears, select "Skip" if available
4. Enter recovery email address as alternative
5. Complete creation

---

## Browser-Use Automation Logic

### Pre-conditions

- Use residential IP (not datacenter) to avoid detection
- Clear browser cache and cookies before each attempt
- Use unique browser fingerprint per session
- Space attempts: minimum several hours between account creations from same environment
- Prepare a valid recovery email address in advance

### Automation Flow

```
1. Navigate to Google account creation page
2. Fill "First name" field
3. Fill "Last name" field
4. Click "Next"
5. Set birthdate (year, month, day)
6. Set gender
7. Click "Next"
8. Select "Create your own Gmail address"
9. Fill desired email address
10. Click "Next"
11. Fill password
12. Fill confirm password
13. Click "Next"
14. IF phone number field appears:
     - Check if "Skip" button exists
     - IF skip available: click "Skip"
     - IF skip NOT available: abort (phone verification mandatory)
15. Fill recovery email address
16. Click "Next"
17. Review account info
18. Accept terms of service
19. Complete
```

### Robot Detection Avoidance

Key factors that trigger "Prove you are not a robot" screen:

| Trigger | Mitigation |
|---------|------------|
| Same IP, rapid sequential creation | Rotate residential IPs between accounts |
| Uniform action timing | Use human_score metrics to vary timing (H_T1 CV >= 0.20) |
| Identical browser fingerprint | Rotate fingerprint per session (H_N3 <= 8) |
| Mechanical input patterns | Vary action types and speed (H_G1 <= 20/min, H_G2 >= 0.30) |
| Night-time bulk creation | Schedule during normal hours (H_T3 <= 0.50) |
| Excessive session duration | Keep under 180 min (H_T2) |

### CAPTCHA / reCAPTCHA Handling

When robot verification appears:

1. Attempt image-based CAPTCHA solving via vision model
2. If CAPTCHA fails, rotate IP (airplane mode toggle on mobile, router restart on PC)
3. Switch browser or use incognito mode
4. Wait several hours before retry
5. If persistent, phone verification is mandatory -- abort flow

### IP and Network Strategy

- Use BrightData residential proxies for natural IP appearance
- Rotate IPs between account creation attempts
- Avoid geo jumps: keep same country across session (H_N2 <= 2)
- Limit sessions per IP to avoid density flags (H_N1 <= 15)

---

## Phone Number Limits

- 1 phone number can register approximately 4-5 Google accounts
- After limit: "This phone number has been used too many times" error
- To free up slots: delete phone number from unused accounts via Account > Personal Info > Contact Info

---

## Error Handling

| Error | Cause | Action |
|-------|-------|--------|
| "Prove you are not a robot" | Bot detection triggered | Rotate IP, clear cache, wait, retry |
| "This phone number has been used too many times" | Number reuse limit | Use different number or skip phone entirely |
| Phone skip unavailable | Google enforcing verification | Abort, change device/IP/timing, retry later |
| Verification code not received | SMS delivery issue | Check spam, verify number can receive SMS |
| Account creation blocked | Too many attempts | Wait 24+ hours, change network environment |

---

## Post-Creation Security Setup

Even without phone number, strengthen account security:

1. Set a strong password
2. Register recovery email address
3. Enable 2-step verification (authenticator app, not SMS)
4. Run Google Security Checkup periodically

---

## Integration with Human Score

This flow should be executed while maintaining human-likeness metrics:

- Record all actions via `HumanScoreTracker.record_action()`
- Record page visits via `HumanScoreTracker.record_page_visit()`
- Record IP usage via `HumanScoreTracker.record_ip()`
- Compute score after flow completion and log results
- Target: composite score >= 70 (PASS)

See `logic/human_score.md` for full metric definitions.
