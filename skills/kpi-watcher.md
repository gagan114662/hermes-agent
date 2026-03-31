# KPI & Anomaly Watcher

## When to Use

Activate this skill when:
- User says "how are we doing", "check the numbers", "any anomalies", "metrics report"
- User says "why did X change", "what happened to revenue", "explain this spike/drop"
- Scheduled periodic check (cron: hourly for critical metrics, daily for trends, weekly for reports)
- Another skill detects a potential metric issue (e.g., support volume spike from customer-support-ops)
- User sets up a new KPI to watch: "track X and alert me if it changes"
- Owner asks for investor update prep or board meeting data

## What You Need

### Tools
- `web_search` — Research external factors that explain anomalies (market events, competitor moves, seasonality)
- `browser_navigate` — Pull data from dashboards (Stripe, Google Analytics, Mixpanel, ad platforms)
- `prospect_tool` — CRM data for sales metrics (pipeline value, deal count, conversion rates)
- `email_read` — Scan for automated reports, alert emails from monitoring tools
- `state_db` — Store metric snapshots, historical baselines, alert thresholds, trend data
- `send_message` — Telegram alerts when anomalies detected
- `email_send` — Weekly/monthly metric reports to owner or stakeholders
- `file_tools` — Save detailed reports, charts data, audit logs
- `cron_schedule` — Set up periodic metric checks

### Data Needed
- Dashboard access credentials (Stripe, Analytics, ad platforms)
- Metric definitions: what to track, how to calculate, what's "normal"
- Historical baselines: 30-day rolling averages for each metric
- Alert thresholds: what % deviation triggers a notification
- Business context: pricing changes, launches, campaigns that affect metrics

## Process

### Step 1: Define the Metric Registry

Maintain a living registry of all tracked KPIs.

```
METRIC REGISTRY (stored in state_db):

REVENUE METRICS (check: hourly)
  - MRR (Monthly Recurring Revenue): Stripe dashboard
    Baseline: rolling 30-day average
    Alert threshold: >10% deviation from 7-day trend
    Source: browser_navigate("https://dashboard.stripe.com/revenue")

  - Daily revenue: Stripe daily totals
    Alert threshold: >20% drop from same day last week
    Source: browser_navigate("https://dashboard.stripe.com/payments")

  - Churn rate: cancellations / total customers
    Alert threshold: >15% increase from 30-day average
    Source: Stripe + CRM data

  - ARPU (Average Revenue Per User): MRR / active customers
    Alert threshold: >10% change either direction
    Source: Calculated from Stripe + customer count

GROWTH METRICS (check: daily)
  - New signups: daily registration count
    Baseline: 7-day rolling average
    Alert threshold: >25% deviation
    Source: browser_navigate(analytics_dashboard)

  - Trial-to-paid conversion rate
    Alert threshold: >15% drop from 30-day average
    Source: CRM pipeline analysis

  - Activation rate: % of signups completing onboarding
    Alert threshold: >20% drop
    Source: Product analytics

MARKETING METRICS (check: daily)
  - Ad spend (total and per-channel)
    Alert threshold: >10% overspend vs budget
    Source: browser_navigate(google_ads, facebook_ads)

  - CAC (Customer Acquisition Cost): total spend / new customers
    Alert threshold: >20% increase from 30-day average
    Source: Calculated

  - Website traffic and conversion rate
    Alert threshold: >25% traffic drop, >15% conversion drop
    Source: Google Analytics

SUPPORT METRICS (check: every 6 hours)
  - Ticket volume: new tickets per period
    Alert threshold: >30% spike from normal
    Source: Support tool or email scan

  - Average resolution time
    Alert threshold: >25% increase
    Source: Support tool

  - Customer satisfaction / NPS
    Alert threshold: any drop >5 points
    Source: Survey tool

PRODUCT METRICS (check: hourly)
  - Error rate: application errors per period
    Alert threshold: >50% spike or any 5xx error burst
    Source: Monitoring dashboard, error alert emails

  - Uptime: system availability
    Alert threshold: any downtime >5 minutes
    Source: Monitoring tool

  - Active users (DAU/WAU/MAU)
    Alert threshold: >15% drop in DAU
    Source: Analytics dashboard
```

### Step 2: Collect Current Values

For each scheduled check, pull fresh data.

```
1. Dashboard scraping:
   For each metric with a dashboard source:
     data = browser_navigate(url=metric.source_url)
     current_value = extract_metric(data, metric.selector)
     state_db(action="store_snapshot", metric=metric.name,
       value=current_value, timestamp=now)

2. API data:
   For metrics available via API:
     stripe_data = api_call(endpoint="stripe/revenue", params={period: "today"})
     analytics_data = api_call(endpoint="analytics/users", params={period: "today"})

3. Calculated metrics:
   For derived metrics (CAC, ARPU, conversion rates):
     Calculate from component metrics already collected
     Store the calculated value

4. CRM metrics:
   prospect_tool(action="pipeline_summary")
   → Pipeline value, deal count by stage, conversion rates

5. Email scan for automated reports:
   email_read(search="from:alerts@ OR from:noreply@stripe.com", after=last_check)
   → Parse any automated metric reports
```

### Step 3: Detect Anomalies

Compare current values against baselines and thresholds.

```
ANOMALY DETECTION ALGORITHM:

For each metric:
  1. Get baseline:
     baseline = state_db(action="get_baseline", metric=metric.name, period="30d")
     recent_trend = state_db(action="get_trend", metric=metric.name, period="7d")

  2. Calculate deviation:
     deviation_from_baseline = (current - baseline.avg) / baseline.avg * 100
     deviation_from_trend = (current - recent_trend.predicted) / recent_trend.predicted * 100

  3. Check threshold:
     if abs(deviation_from_baseline) > metric.alert_threshold:
       anomaly_detected = True
       severity = classify_severity(deviation, metric.importance)

  4. Classify severity:
     CRITICAL: Revenue drop >20%, error rate spike >100%, any downtime
     WARNING: Revenue drop 10-20%, growth metric drop >25%, spend overage
     INFO: Notable change worth mentioning but not alarming

  5. Filter noise:
     - Ignore known patterns (weekend dips, month-end spikes)
     - Ignore one-time events already acknowledged
     - Ignore metrics already in alert state (don't re-alert)
     - Apply minimum absolute threshold (ignore small $ changes on small base)
```

### Step 4: Investigate Anomalies

For each detected anomaly, find the likely cause.

```
INVESTIGATION PROCESS:

1. Check for correlated anomalies:
   - Revenue dropped AND signups dropped → likely upstream issue
   - Error rate spiked AND churn spiked → product issue causing churn
   - Ad spend spiked AND CAC stable → might be fine, just scaling

2. Check internal events:
   state_db(action="get_recent_events")
   → Recent deploys, pricing changes, campaign launches, feature flags

3. Check external factors:
   web_search(query=f"{industry} {today} outage OR news OR event")
   → Competitor launch, market event, platform outage, seasonality

4. Check support signals:
   email_read(search="subject:bug OR subject:issue OR subject:down", after=anomaly_start)
   → Customer complaints that explain the metric change

5. Correlate timing:
   When did the anomaly start? What changed at that time?
   state_db(action="get_timeline", metric=metric.name, range="48h")

6. Formulate explanation:
   CONFIRMED: Clear cause identified with evidence
   LIKELY: Strong correlation but not definitive
   UNKNOWN: No clear cause found, needs manual investigation
```

### Step 5: Alert and Recommend

Notify owner only when action is needed or insight is valuable.

```
ALERT RULES:
  - CRITICAL: Immediately via Telegram + email. Include recommended action.
  - WARNING: Telegram message within 1 hour. Include explanation and options.
  - INFO: Include in daily briefing only. Don't interrupt.
  - NO ALERT: If metric returned to normal before alert sent, log but don't notify.

NOTIFICATION FORMAT:
  send_message(chat_id=owner_id, text=alert_message)

  For critical:
    "METRIC ALERT: Revenue dropped 23% today vs 7-day average.
     Likely cause: Stripe webhook failure (3 failed charges detected).
     Recommended action: Check Stripe dashboard, retry failed charges.
     Dashboard: [link]"

  For warning:
    "METRIC NOTE: Signups down 18% this week.
     Likely cause: Google Ads campaign paused (budget exhausted).
     Recommended: Increase daily budget or reallocate from Facebook.
     Current CAC: $42 (still below $50 target)."

RECOMMENDATION ALWAYS INCLUDES:
  1. What changed (the metric)
  2. By how much (absolute and percentage)
  3. Likely why (root cause analysis)
  4. What to do (specific action)
  5. What happens if ignored (risk)
```

### Step 6: Periodic Reports

Generate scheduled reports at defined intervals.

```
DAILY REPORT (sent every morning in chief-of-staff briefing):
  - All metrics vs yesterday and vs 7-day average
  - Any active anomalies
  - Trend direction for each metric (up/down/flat)

WEEKLY REPORT (sent every Monday):
  - Week-over-week comparison for all metrics
  - Top 3 metrics that improved, top 3 that declined
  - Anomaly summary: what happened, what was done
  - Trend chart data (7-week history)

MONTHLY REPORT (sent 1st of month):
  - Month-over-month comparison
  - Quarter-to-date progress
  - Goal tracking (actual vs target)
  - Cohort analysis (if data available)
  - Investor-ready summary format
```

## Output Format

### Real-Time Alert

```
METRIC ALERT [{severity}]
Metric: {metric_name}
Current: {value} ({direction} {change_pct}% from baseline)
Baseline: {baseline_value} (30-day avg)
Since: {anomaly_start_time}

CAUSE: {confirmed/likely/unknown}
  {Explanation with evidence}

ACTION RECOMMENDED:
  {Specific step to take}

RISK IF IGNORED:
  {What happens if no action taken}

[Dashboard link] [Investigate more] [Snooze 24h]
```

### Daily Metrics Summary

```
DAILY METRICS — {date}
==========================

REVENUE
  MRR:          ${value}   ({pct}% vs yesterday, {pct}% vs 7d avg)
  Daily rev:    ${value}   ({pct}% vs same day last week)
  Churn:        {value}%   ({direction} from {prev}%)
  ARPU:         ${value}   (stable)

GROWTH
  Signups:      {count}    ({pct}% vs 7d avg)
  Conversion:   {pct}%     ({direction} from {prev}%)
  Activation:   {pct}%     (stable)

MARKETING
  Ad spend:     ${value}   (${remaining} of ${budget} budget left)
  CAC:          ${value}   ({direction} from ${prev})
  Traffic:      {count}    ({pct}% vs 7d avg)

SUPPORT
  Tickets:      {count}    ({direction} from normal)
  Avg resolve:  {hours}h   ({direction})

PRODUCT
  Error rate:   {pct}%     (normal)
  Uptime:       {pct}%     (target: 99.9%)
  DAU:          {count}    ({pct}% vs 7d avg)

ANOMALIES: {count} active
  {List if any}

OVERALL: {Green / Yellow / Red} — {one sentence assessment}
```

### Weekly Report

```
WEEKLY METRICS REPORT — Week of {date}
==========================================

TOP LINE:
  MRR: ${value} ({+/-}{pct}% WoW) | Target: ${target} ({pct}% of target)
  New customers: {count} | Churned: {count} | Net: {+/-count}

WINNERS THIS WEEK:
  1. {metric}: {value} — up {pct}% because {reason}
  2. {metric}: {value} — up {pct}% because {reason}
  3. {metric}: {value} — up {pct}% because {reason}

NEEDS ATTENTION:
  1. {metric}: {value} — down {pct}% because {reason}. Action: {recommendation}
  2. {metric}: {value} — down {pct}% because {reason}. Action: {recommendation}

ANOMALIES THIS WEEK:
  {date}: {what happened} → {what was done} → {outcome}
  {date}: {what happened} → {what was done} → {outcome}

7-WEEK TREND:
  MRR:     $X → $X → $X → $X → $X → $X → ${current}  (trend: {up/flat/down})
  Signups: X  → X  → X  → X  → X  → X  → {current}   (trend: {up/flat/down})
  Churn:   X% → X% → X% → X% → X% → X% → {current}%  (trend: {up/flat/down})
```

## Examples

### Example 1: Revenue Anomaly Detection

**Input:** (Automatic hourly check detects revenue drop)

**Process:**
1. Pull Stripe data: daily revenue down 28% vs 7-day average
2. Check correlated metrics: signups normal, churn normal, error rate normal
3. Investigate: find 12 failed charge attempts in last 4 hours
4. Check Stripe status page: no outage reported
5. Check webhook logs: webhook endpoint returning 500 errors since 2pm
6. Root cause: deployment at 1:45pm broke webhook handler

**Output:**
```
METRIC ALERT [CRITICAL]
Metric: Daily Revenue
Current: $1,240 (down 28% from $1,722 baseline)
Since: 2:00pm today

CAUSE: CONFIRMED
  Stripe webhook handler broken since 1:45pm deploy.
  12 charges failed to process. Estimated lost: $482.

ACTION RECOMMENDED:
  1. Rollback deploy or fix webhook handler
  2. Retry 12 failed charges via Stripe dashboard
  3. Notify affected customers if charges will re-attempt

RISK IF IGNORED:
  ~$1,200/day in failed charges. Customers may see failed payment notices.
```

### Example 2: "How are we doing this week?"

**Input:** "How are we doing?"

**Process:**
1. Pull all metrics for current week
2. Compare to last week and 30-day averages
3. Identify top movers in both directions
4. Compile weekly summary

**Output:** Full weekly metrics report with winners, concerns, and trends

### Example 3: Setting Up a New KPI

**Input:** "Start tracking our NPS score and alert me if it drops"

**Process:**
1. Ask: Where is NPS data? (survey tool, dashboard URL, email reports)
2. Set up metric in registry with source, baseline, threshold
3. Create cron schedule for checks
4. Confirm setup

**Output:**
```
NPS tracking configured:
  Source: Typeform survey results (checked daily)
  Current baseline: 47 (will calibrate over 30 days)
  Alert threshold: drop of >5 points
  Check frequency: Daily at 9am

First baseline snapshot taken. Will alert you if NPS moves significantly.
```
