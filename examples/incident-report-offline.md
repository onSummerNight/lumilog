# Incident report

- **Source:** `logs/sms-gateway.log`
- **Period:** 2026-10-07 13:00:00.110 → 2026-10-07 15:04:18.046
- **Events:** 13,702 parsed, 0 unparsed
- **Mode:** offline (rule-based). Every number comes from the log data.

## Summary

1. **CRITICAL** 13:41–13:56 · Submit failures at provider ISAT: ISAT submit failures 166/260 (64%), peak 92%/min vs baseline 0.0%
2. **MAJOR** 14:21–14:35 · Queue stall on gw-sms-02: gw-sms-02 queue grew to 462 while it submitted 0 messages (normal ~30/min)
3. **MAJOR** 14:40–14:50 · Delayed delivery reports from TSEL: TSEL delivery reports delayed: p90 up to 14.5 min (normal p90 ~27s)

## Timeline

| Start | End | Severity | Incident |
|---|---|---|---|
| 2026-10-07 13:41 | 2026-10-07 13:56 | critical | Submit failures at provider ISAT |
| 2026-10-07 14:21 | 2026-10-07 14:35 | major | Queue stall on gw-sms-02 |
| 2026-10-07 14:40 | 2026-10-07 14:50 | major | Delayed delivery reports from TSEL |

## 1. Submit failures at provider ISAT

**Window:** 2026-10-07 13:41 → 2026-10-07 13:56 (15 min) · **Severity:** critical

**What happened:** ISAT submit failures 166/260 (64%), peak 92%/min vs baseline 0.0%.

| Metric | Incident 13:41–13:56 | Normal 13:24–13:39 |
|---|---|---|
| Submits / min | 17.3 | 16.6 |
| Failed submits | 166 | 2 |
| Failure rate | 63.8% | 0.8% |
| Retries | 331 | 0 |
| Avg submit latency (ms) | 19,238 | 241 |
| Max queue depth | 5 | 5 |

**Sample failed submits (4 of 166):**

```
2026-10-07 13:41:10.880 ERROR [gw-sms-01] SUBMIT msgid=00000936 msisdn=62814****776 sender=DEMOBANK provider=ISAT status=FAILED error=TIMEOUT latency_ms=30000
2026-10-07 13:41:20.004 ERROR [gw-sms-01] SUBMIT msgid=00000951 msisdn=62814****011 sender=DEMOBANK provider=ISAT status=FAILED error=TIMEOUT latency_ms=30000
2026-10-07 13:41:20.779 ERROR [gw-sms-02] SUBMIT msgid=00000948 msisdn=62816****589 sender=DEMOBANK provider=ISAT status=FAILED error=TIMEOUT latency_ms=30000
2026-10-07 13:41:22.221 ERROR [gw-sms-01] SUBMIT msgid=0000093c msisdn=62814****778 sender=DEMOPAY provider=ISAT status=FAILED error=TIMEOUT latency_ms=30000
```

**Likely cause** (confidence: high): Problem on the ISAT side. Failures are concentrated on ISAT (dominant error: TIMEOUT) while other providers stayed normal in the same window (TSEL 0.0%, XL 0.0%), so the gateways themselves were healthy.

**Next checks:**

- Confirm with ISAT whether their SMSC had an outage or throttling in this window.
- Check network path and bind/session status from the gateways to ISAT.
- Decide whether failed messages need resending; OTP messages are usually stale after a few minutes.
- Consider automatic failover to another route when ISAT timeouts exceed a threshold.

## 2. Queue stall on gw-sms-02

**Window:** 2026-10-07 14:21 → 2026-10-07 14:35 (14 min) · **Severity:** major

**What happened:** gw-sms-02 queue grew to 462 while it submitted 0 messages (normal ~30/min).

| Metric | Incident 14:21–14:35 | Normal 14:05–14:19 |
|---|---|---|
| Submits / min | 0.0 | 32.7 |
| Failed submits | 0 | 3 |
| Failure rate | n/a | 0.7% |
| Retries | 0 | 0 |
| Avg submit latency (ms) | n/a | 242 |
| Max queue depth | 462 | 5 |

**Queue depth on gw-sms-02 (first 5 minutes):**

```
2026-10-07 14:21:59.999 INFO  [gw-sms-02] QUEUE depth=50
2026-10-07 14:22:59.999 INFO  [gw-sms-02] QUEUE depth=84
2026-10-07 14:23:59.999 INFO  [gw-sms-02] QUEUE depth=118
2026-10-07 14:24:59.999 INFO  [gw-sms-02] QUEUE depth=151
2026-10-07 14:25:59.999 INFO  [gw-sms-02] QUEUE depth=186
```

**Likely cause** (confidence: medium): gw-sms-02 stopped sending while its outbound queue kept growing. Other hosts kept working (gw-sms-01 sent 430) and provider failure rates in the same window were normal (ISAT 0.0%, TSEL 1.4%, XL 0.0%), which points to gw-sms-02 itself: a hung sender process, lost provider binds, or an exhausted connection pool. The logs show the symptom, not which of these it was.

**Next checks:**

- Check the sender process on gw-sms-02 (alive, stuck threads, restarts) around 14:21.
- Check provider bind/session status on gw-sms-02 at the stall start.
- Verify the backlog drained after recovery and no messages were dropped.
- Add an alert on queue depth rising while submit rate is near zero.

## 3. Delayed delivery reports from TSEL

**Window:** 2026-10-07 14:40 → 2026-10-07 14:50 (10 min) · **Severity:** major

**What happened:** TSEL delivery reports delayed: p90 up to 14.5 min (normal p90 ~27s).

| Metric | Incident 14:40–14:50 | Normal 14:52–15:02 |
|---|---|---|
| Submits / min | 32.1 | 25.0 |
| Failed submits | 1 | 1 |
| Failure rate | 0.3% | 0.4% |
| Retries | 0 | 0 |
| Avg submit latency (ms) | 240 | 238 |
| Max queue depth | 5 | 4 |

**Slowest deliveries (submit and report):**

```
# msgid 0000196c: report after 14.8 min
2026-10-07 14:49:22.146 INFO  [gw-sms-02] SUBMIT msgid=0000196c msisdn=62813****277 sender=DEMOBANK provider=TSEL status=ACCEPTED latency_ms=327
2026-10-07 15:04:11.813 INFO  [gw-sms-02] DLR msgid=0000196c provider=TSEL status=DELIVERED
# msgid 00001786: report after 14.8 min
2026-10-07 14:41:26.769 INFO  [gw-sms-01] SUBMIT msgid=00001786 msisdn=62811****867 sender=OTP-SVC provider=TSEL status=ACCEPTED latency_ms=249
2026-10-07 14:56:15.817 INFO  [gw-sms-01] DLR msgid=00001786 provider=TSEL status=DELIVERED
# msgid 00001947: report after 14.8 min
2026-10-07 14:48:37.610 INFO  [gw-sms-01] SUBMIT msgid=00001947 msisdn=62811****152 sender=DEMOBANK provider=TSEL status=ACCEPTED latency_ms=379
2026-10-07 15:03:25.726 INFO  [gw-sms-01] DLR msgid=00001947 provider=TSEL status=DELIVERED
```

**Likely cause** (confidence: medium): Messages to TSEL were accepted normally (submit failure rate 0.3%, avg latency 240 ms vs 238 ms normally) but delivery reports came back late (p90 up to 14.5 min vs ~27s normally). The delay is on the TSEL delivery-report path, not in sending.

**Next checks:**

- Ask TSEL whether their delivery-report pipeline was delayed in this window.
- Confirm whether end users actually received messages late, or only the reports were late.
- Check that delayed reports did not trigger unnecessary resends or timeouts in upstream apps.

