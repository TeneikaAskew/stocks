# Market Events System - Analysis & Improvement Recommendations

**Date**: October 13, 2025
**Status**: Analysis Complete, Implementation Pending

---

## Table of Contents
1. [Current System Overview](#current-system-overview)
2. [Coverage Analysis](#coverage-analysis)
3. [Update Frequency & Data Sources](#update-frequency--data-sources)
4. [Limitations & Gaps](#limitations--gaps)
5. [notify_upcoming_events Purpose](#notify_upcoming_events-purpose)
6. [Improvement Recommendations](#improvement-recommendations)

---

## Current System Overview

### Components
- **market_events.json** (12KB, 61 events) - Primary data file, JSON format, tracked in git
- **market_events_tracker.py** - Manages event calendar, hardcoded 2025 events
- **fetch_economic_calendar.py** - Fetches FRED economic data via API
- **update_economic_events_calendar.yml** - GitHub Actions workflow (runs 2x daily)
- **notify_upcoming_events** - Job that alerts on upcoming high-impact events

### Workflow Schedule
- **6:00 AM EST** (11 AM UTC) - Daily morning check
- **4:30 PM EST** (9:30 PM UTC) - Weekday evening check (Mon-Fri)
- **Manual trigger** - Available via workflow_dispatch

---

## Coverage Analysis

### What's Included (61 Events)

| Event Type | Count | Frequency | Date Range | Coverage |
|------------|-------|-----------|------------|----------|
| **CPI** (Consumer Price Index) | 12 | Monthly (~13th) | Jan-Dec 2025 | ✅ Complete |
| **NFP** (Non-Farm Payrolls) | 12 | Monthly (1st Fri) | Jan-Dec 2025 | ✅ Complete |
| **GDP** (Gross Domestic Product) | 10 | Quarterly + revisions | Q4 2024 - Q3 2025 | ⚠️ Missing Q4 2025 |
| **PCE** (Personal Consumption Exp.) | 10 | Monthly (end of month) | Jan-Oct 2025 | ⚠️ Missing Nov-Dec |
| **FOMC** (Fed Rate Decisions) | 8 | 8x per year | Full 2025 | ✅ Complete |
| **SPECIAL** (Market Holidays) | 9 | Various | Full 2025 | ✅ Complete |

**Date Range**: January 10, 2025 → December 25, 2025

### What's Missing

#### High-Impact Events NOT Tracked
- **Retail Sales** (Monthly, high impact on consumer sector)
- **ISM PMI** (Manufacturing & Services, monthly)
- **PPI** (Producer Price Index, monthly inflation)
- **Housing Starts** (Monthly, housing sector impact)
- **Initial Jobless Claims** (Weekly, labor market indicator)
- **Consumer Confidence** (Monthly, sentiment indicator)
- **Durable Goods Orders** (Monthly, manufacturing indicator)
- **Trade Balance** (Monthly, currency/export impact)
- **Earnings Season Dates** (Quarterly, major market drivers)

#### Coverage Gaps
- **Q4 2025 GDP releases** (November/December)
- **November/December PCE** data
- **2026+ events** (system only covers 2025)

#### Event Types Defined But Not Used
The script defines these event types in `market_events_tracker.py:64-98` but doesn't include them in the calendar:
- RETAIL_SALES
- ISM_PMI
- HOUSING_STARTS
- JOBLESS_CLAIMS
- EARNINGS

---

## Update Frequency & Data Sources

### A. Market Events Calendar (JSON)

**Current State**: ⚠️ **STATIC - Hardcoded**

**How It Works**:
- Events hardcoded in `market_events_tracker.py:101-181`
- Workflow runs 2x daily but just re-saves same data
- No external data source integration
- No automatic updates

**Update Process**:
- ❌ **No automatic date detection** (e.g., if BLS reschedules CPI)
- ❌ **No automatic consensus fetching**
- ❌ **No automatic actual value updates**
- ✅ **Manual updates** possible via `add_event()` method
- ⚠️ **Manual maintenance required** for 2026 events

**Risk Level**: 🔴 **HIGH**
- Will break in 2026 without manual update
- Won't detect schedule changes
- Missing actual/consensus data for analysis

---

### B. FRED Economic Data

**Current State**: ✅ **DYNAMIC - Real-time API**

**How It Works**:
- Fetches from Federal Reserve Economic Data (FRED) API
- Requires `FRED_API_KEY` GitHub secret
- Workflow passes API key as environment variable
- Saves to `data/fred_economic_data.csv` (gitignored)

**Data Sources & Update Frequencies**:

| FRED Series | Indicator | Update Frequency | Data Lag |
|-------------|-----------|------------------|----------|
| **DFF** | Federal Funds Rate | Daily | 1 business day |
| **UNRATE** | Unemployment Rate | Monthly | ~1st Friday |
| **CPIAUCSL** | Consumer Price Index | Monthly | ~13th of month |
| **GDP** | Gross Domestic Product | Quarterly | ~25-30 days after quarter |
| **DEXUSEU** | USD/EUR Exchange Rate | Daily | 1 business day |
| **DGS10** | 10-Year Treasury Rate | Daily | 1 business day |
| **DGS2** | 2-Year Treasury Rate | Daily | 1 business day |
| **VIXCLS** | VIX Volatility Index | Daily | 1 business day |
| **DCOILWTICO** | WTI Crude Oil Price | Daily | 1 business day |
| **GOLDAMGBD228NLBM** | Gold Price (London AM) | Daily | 1 business day |

**Advantages**:
- ✅ Real historical data (not mock)
- ✅ Automatic data revisions when FRED updates
- ✅ No manual maintenance needed
- ✅ Official government/Fed data sources
- ✅ Free API (requires registration)

**Data Quality**:
- Forward-fills missing values (weekends/holidays)
- Handles multi-index columns from pandas
- Saves clean CSV format

---

## Limitations & Gaps

### What the System CAN Do

✅ **Manual Event Management**:
- `add_event()` method exists for programmatic additions
- Supports `actual`, `consensus`, and `notes` fields
- Can update events post-release

✅ **FRED Data Auto-Updates**:
- Fetches latest values automatically
- Handles data revisions from FRED
- Forward-fills missing values

✅ **Basic Alerting**:
- Identifies high-impact events in next 3 days
- Logs to GitHub Actions console
- Runs twice daily automatically

---

### What the System CANNOT Do

❌ **No Automatic Event Calendar Updates**:
- Doesn't fetch event dates from external calendar APIs
- Doesn't detect schedule changes (e.g., CPI date moved due to holiday)
- Doesn't automatically populate actual/consensus values after releases
- Won't work for 2026+ without manual code updates

❌ **No Dynamic Event Discovery**:
- Can't find "surprise" events (emergency FOMC meetings, special releases)
- No integration with economic calendar services
- Missing spontaneous/unscheduled events

❌ **No Revision Tracking**:
- Doesn't track when economic data gets revised
- Doesn't store historical versions of consensus estimates
- No "surprise index" calculation (actual vs consensus)

❌ **No Real Notifications**:
- Only logs to GitHub Actions (must manually check)
- No email, Slack, SMS, or Discord alerts
- No push notifications to mobile devices

❌ **No Event Impact Analysis**:
- Doesn't analyze historical market reactions
- No correlation with price movements
- No volatility pattern recognition

❌ **Limited Context**:
- No consensus estimates shown
- No previous values displayed
- No historical comparison
- No time of release information

---

## notify_upcoming_events Purpose

### What It Does

**Primary Function**:
Early warning system that scans for high-impact economic events in the next 3 days and logs alerts to GitHub Actions.

**Workflow**:
1. Loads `data/market_events.json` from repository
2. Filters events in next 3 days (today + 3)
3. Shows only "High" or "Very High" impact events
4. Prints to GitHub Actions workflow logs

**Alert Criteria**:
- **"Very High" Impact**: FOMC meetings only (8 per year)
- **"High" Impact**: CPI, NFP, GDP, PCE releases

**Ignores**:
- Low/Medium impact events
- Market holidays (SPECIAL events)
- Events beyond 3-day window

---

### Example Outputs

#### When Events Are Coming
```
✓ Loaded events from market_events.json
📅 UPCOMING HIGH IMPACT EVENTS:
  2025-10-30 (2 days): GDP Q3 2025 Advance [High]
  2025-10-31 (3 days): PCE Price Index [High]
```

#### When All Clear
```
✓ Loaded events from market_events.json
✓ No high-impact events in the next 3 days
```

#### When File Missing (Error State)
```
⚠️  Warning: market_events.json not found
The file may not have been created by the previous job.
This could indicate the market_events_tracker.py script failed.
```

---

### Real-World Use Cases

#### 1. Trading Preparation
**Scenario**: Monday morning, CPI release on Wednesday
- **Action**: Reduce leverage today/Tuesday
- **Rationale**: CPI often causes 0.5-1% market swings
- **Timing**: Adjust positions before Wednesday 8:30 AM EST

#### 2. Options Trading
**Scenario**: FOMC meeting in 2 days, you have short puts expiring Friday
- **Action**: Close short puts or roll to next week
- **Rationale**: FOMC causes volatility spikes, IV expansion
- **Risk**: Unlimited loss if market tanks on hawkish Fed

#### 3. Portfolio Rebalancing
**Scenario**: NFP (jobs report) coming Friday, portfolio at all-time highs
- **Action**: Take some profits Thursday, raise cash
- **Rationale**: NFP beats/misses can cause reversals
- **Benefit**: Lock in gains before potential drawdown

#### 4. Risk Management
**Scenario**: GDP release tomorrow, holding leveraged ETFs
- **Action**: Reduce position size or hedge with puts
- **Rationale**: GDP surprises amplified by leverage
- **Protection**: Limit max loss to acceptable level

#### 5. Market Analysis
**Scenario**: PCE data in 3 days, analyzing market trends
- **Action**: Wait for PCE before making long-term calls
- **Rationale**: Fed policy depends on inflation data
- **Context**: Better decisions with complete information

---

### What It DOESN'T Provide

❌ **No Push Notifications**
- Must manually check GitHub Actions logs
- No mobile alerts
- No real-time awareness

❌ **No Event Context**
- Doesn't show consensus estimates
- Doesn't show previous values
- Doesn't indicate time of release
- No historical volatility data

❌ **No Actionable Recommendations**
- Doesn't suggest position adjustments
- Doesn't calculate risk exposure
- Doesn't recommend hedges
- No strategy suggestions

❌ **No Integration**
- Can't feed into trading systems
- No API endpoint for external tools
- No calendar export (iCal/Google Calendar)
- No TradingView alerts

---

## Improvement Recommendations

### Priority 1 - Critical (Do First)

#### 1. Add 2026+ Event Generation
**Problem**: System only has 2025 events hardcoded
**Risk**: Complete failure in January 2026
**Solution**: Implement rule-based date calculation

**Implementation**:
```python
def generate_events_for_year(year):
    """Generate economic events for any year using rules."""
    events = []

    # CPI: Second Tuesday-Thursday of month (~13th)
    for month in range(1, 13):
        cpi_date = get_nth_weekday(year, month, 1, 2)  # 2nd Tuesday
        events.append({
            'date': cpi_date,
            'event_type': 'CPI',
            'event': f'CPI Release',
            'expected_impact': 'High'
        })

    # NFP: First Friday of month
    for month in range(1, 13):
        nfp_date = get_nth_weekday(year, month, 4, 0)  # 1st Friday
        events.append({
            'date': nfp_date,
            'event_type': 'NFP',
            'event': 'Non-Farm Payrolls',
            'expected_impact': 'High'
        })

    # FOMC: Use Federal Reserve published schedule
    fomc_dates = fetch_fomc_schedule(year)  # From Fed website
    for date in fomc_dates:
        events.append({
            'date': date,
            'event_type': 'FOMC',
            'event': 'FOMC Meeting & Decision',
            'expected_impact': 'Very High'
        })

    return events
```

**Effort**: Medium (2-3 days)
**Value**: Critical - prevents system failure

---

#### 2. Add Missing High-Impact Events
**Problem**: Only 6 event types tracked, missing many important releases
**Impact**: Incomplete market awareness, missed trading risks
**Solution**: Add 5-10 more event types

**Events to Add**:
- ✅ Retail Sales (monthly, ~15th)
- ✅ ISM PMI Manufacturing (monthly, 1st business day)
- ✅ ISM PMI Services (monthly, 3rd business day)
- ✅ PPI (Producer Price Index, monthly, ~14th)
- ✅ Housing Starts (monthly, ~17th)
- ✅ Consumer Confidence (monthly, last Tuesday)
- ✅ Initial Jobless Claims (weekly, Thursday 8:30 AM)
- ✅ Durable Goods Orders (monthly, ~25th)
- ✅ Personal Income/Spending (monthly, with PCE)
- ✅ Trade Balance (monthly, ~5th)

**Implementation**: Extend `get_2025_economic_calendar()` method

**Effort**: Low (1 day)
**Value**: High - complete coverage

---

#### 3. Complete 2025 Coverage
**Problem**: Missing Q4 GDP and Nov-Dec PCE
**Impact**: Incomplete year coverage
**Solution**: Add missing end-of-year events

**Missing Events**:
```python
# GDP Q3 2025 Second & Final
{'date': '2025-11-25', 'event_type': 'GDP', 'event': 'GDP Q3 2025 Second'},
{'date': '2025-12-23', 'event_type': 'GDP', 'event': 'GDP Q3 2025 Final'},

# GDP Q4 2025 Advance (in 2026)
{'date': '2026-01-29', 'event_type': 'GDP', 'event': 'GDP Q4 2025 Advance'},

# PCE November & December
{'date': '2025-11-26', 'event_type': 'PCE', 'event': 'PCE Price Index'},
{'date': '2025-12-20', 'event_type': 'PCE', 'event': 'PCE Price Index'},
```

**Effort**: Very Low (30 minutes)
**Value**: Medium - completes 2025

---

### Priority 2 - High Value

#### 4. Integrate Economic Calendar API
**Problem**: Manual updates for dates, consensus, actuals
**Impact**: Outdated data, schedule changes missed
**Solution**: Use external economic calendar service

**Options**:

##### Option A: Trading Economics API (Recommended)
- **Coverage**: 20M+ economic indicators, 196 countries
- **Features**: Real-time events, consensus, actuals, revisions
- **Update Frequency**: Real-time as data releases
- **Cost**: Paid ($50-500/month depending on tier)
- **Data Quality**: Excellent, widely used by institutions
- **API Docs**: https://tradingeconomics.com/api

**Implementation**:
```python
import requests

def fetch_trading_economics_calendar(start_date, end_date, api_key):
    """Fetch economic calendar from Trading Economics."""
    url = f"https://api.tradingeconomics.com/calendar"
    params = {
        'c': api_key,
        'd1': start_date,  # YYYY-MM-DD
        'd2': end_date,
        'country': 'united states',
        'importance': '3'  # High importance only
    }

    response = requests.get(url, params=params)
    events = response.json()

    return parse_trading_economics_response(events)
```

##### Option B: Alpha Vantage (Free Tier Available)
- **Coverage**: US economic indicators
- **Features**: Economic calendar, FRED integration
- **Update Frequency**: Daily updates
- **Cost**: Free tier (5 API calls/min, 500/day)
- **Data Quality**: Good, maintained by Alpha Vantage team
- **API Docs**: https://www.alphavantage.co/documentation/

##### Option C: Yahoo Finance Calendar Scraping (Free)
- **Coverage**: Major US economic events
- **Features**: Dates, consensus, actuals
- **Update Frequency**: Near real-time
- **Cost**: Free
- **Data Quality**: Good, but requires scraping (brittle)
- **Reliability**: May break if Yahoo changes site structure

**Recommendation**: Start with **Alpha Vantage free tier**, upgrade to **Trading Economics** if needed

**Effort**: Medium (3-5 days)
**Value**: Very High - automated updates

---

#### 5. Add Consensus & Actual Value Tracking
**Problem**: No consensus estimates or actual results stored
**Impact**: Can't analyze beat/miss patterns or surprise reactions
**Solution**: Fetch and store consensus before events, actuals after

**Data Structure**:
```python
{
    'date': '2025-10-10',
    'event_type': 'CPI',
    'event': 'CPI Release',
    'expected_impact': 'High',
    'consensus': '2.3% YoY',           # Pre-event estimate
    'consensus_range': '2.2% - 2.4%',  # Range of estimates
    'actual': '2.4% YoY',               # Post-event result
    'previous': '2.5% YoY',             # Prior month/quarter
    'surprise': '+0.1%',                # Actual - Consensus
    'surprise_pct': 4.35,               # % surprise relative to consensus
    'revision': None,                   # If prior data revised
    'release_time': '08:30 ET',
    'updated_at': '2025-10-10T08:31:00Z'
}
```

**Sources**:
- **Briefing.com** (free, requires scraping)
- **Trading Economics API** (paid, structured)
- **MarketWatch** (free, requires scraping)
- **Bloomberg API** (expensive, enterprise)

**Analysis Enabled**:
- Surprise index calculation
- Beat/miss pattern recognition
- Market reaction correlation
- Volatility prediction models

**Effort**: Medium (4-5 days with API, 7-10 days with scraping)
**Value**: Very High - enables advanced analysis

---

#### 6. Add Revision Tracking
**Problem**: Economic data often revised (GDP, NFP), not tracked
**Impact**: Missing important information about data reliability
**Solution**: Store revision history for key indicators

**Implementation**:
```python
{
    'date': '2025-07-31',
    'event_type': 'GDP',
    'event': 'GDP Q2 2025 Advance',
    'releases': [
        {
            'version': 'Advance',
            'date': '2025-07-31',
            'value': '2.1%',
            'consensus': '2.0%'
        },
        {
            'version': 'Second',
            'date': '2025-08-28',
            'value': '2.2%',          # Revised up
            'revision': '+0.1%',
            'notes': 'Consumer spending stronger than initially reported'
        },
        {
            'version': 'Final',
            'date': '2025-09-26',
            'value': '2.2%',          # Confirmed
            'revision': '0.0%'
        }
    ]
}
```

**Use Cases**:
- Track data reliability by indicator
- Identify patterns in revisions (e.g., NFP always revised up)
- Adjust trading strategies based on revision probability
- Build ML models that account for revision risk

**Effort**: Medium (3-4 days)
**Value**: Medium - improves data quality insights

---

### Priority 3 - Nice to Have

#### 7. Real Notifications System
**Problem**: Must manually check GitHub Actions logs
**Impact**: Easy to miss important alerts
**Solution**: Add push notifications via multiple channels

##### Option A: Email Notifications
**Using SendGrid** (Free tier: 100 emails/day)

```python
import sendgrid
from sendgrid.helpers.mail import Mail, Email, To, Content

def send_event_alert(events, api_key, recipients):
    """Send email alert for upcoming events."""
    sg = sendgrid.SendGridAPIClient(api_key)

    subject = f"⚠️ {len(events)} High-Impact Economic Events in Next 3 Days"

    html_content = """
    <html>
      <body>
        <h2>Upcoming Market-Moving Events</h2>
        <table border="1">
          <tr><th>Date</th><th>Event</th><th>Impact</th></tr>
    """

    for event in events:
        html_content += f"""
          <tr>
            <td>{event['date']}</td>
            <td>{event['event']}</td>
            <td>{event['expected_impact']}</td>
          </tr>
        """

    html_content += """
        </table>
      </body>
    </html>
    """

    message = Mail(
        from_email=Email("alerts@yourdomain.com"),
        to_emails=[To(email) for email in recipients],
        subject=subject,
        html_content=Content("text/html", html_content)
    )

    sg.send(message)
```

**GitHub Actions Integration**:
```yaml
- name: Send email alerts
  if: ${{ env.UPCOMING_EVENTS_COUNT > 0 }}
  env:
    SENDGRID_API_KEY: ${{ secrets.SENDGRID_API_KEY }}
    ALERT_EMAILS: ${{ secrets.ALERT_EMAILS }}
  run: python scripts/send_event_alerts.py
```

##### Option B: Slack Notifications
**Using Slack Webhooks** (Free)

```python
import requests
import json

def send_slack_alert(events, webhook_url):
    """Send Slack message for upcoming events."""

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"📅 {len(events)} High-Impact Events in Next 3 Days"
            }
        }
    ]

    for event in events:
        blocks.append({
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Date:* {event['date']}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Impact:* {event['expected_impact']}"
                }
            ]
        })
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{event['event']}*"
            }
        })
        blocks.append({"type": "divider"})

    payload = {
        "blocks": blocks,
        "username": "Economic Events Bot",
        "icon_emoji": ":chart_with_upwards_trend:"
    }

    requests.post(webhook_url, json=payload)
```

**Setup**:
1. Create Slack App: https://api.slack.com/apps
2. Enable Incoming Webhooks
3. Add webhook URL to GitHub Secrets: `SLACK_WEBHOOK_URL`

##### Option C: Discord Notifications
**Using Discord Webhooks** (Free)

```python
def send_discord_alert(events, webhook_url):
    """Send Discord message for upcoming events."""

    embed = {
        "title": "📅 Upcoming High-Impact Economic Events",
        "description": f"Found {len(events)} events in the next 3 days",
        "color": 15844367,  # Gold color
        "fields": []
    }

    for event in events:
        embed["fields"].append({
            "name": event['event'],
            "value": f"**Date:** {event['date']}\n**Impact:** {event['expected_impact']}",
            "inline": False
        })

    payload = {
        "username": "Market Events",
        "avatar_url": "https://example.com/bot-avatar.png",
        "embeds": [embed]
    }

    requests.post(webhook_url, json=payload)
```

##### Option D: SMS Notifications
**Using Twilio** (Paid: ~$0.01/SMS)

```python
from twilio.rest import Client

def send_sms_alert(events, account_sid, auth_token, to_number, from_number):
    """Send SMS alert for upcoming events."""
    client = Client(account_sid, auth_token)

    message_body = f"⚠️ {len(events)} High-Impact Events in Next 3 Days:\n\n"

    for event in events:
        days = (pd.to_datetime(event['date']) - pd.Timestamp.now()).days
        message_body += f"• {event['date']} ({days}d): {event['event']}\n"

    client.messages.create(
        body=message_body,
        from_=from_number,
        to=to_number
    )
```

**Cost Comparison**:
- Email (SendGrid): Free (100/day), $15/mo (40K/mo)
- Slack: Free (unlimited)
- Discord: Free (unlimited)
- SMS (Twilio): ~$0.01/SMS, ~$0.60/month for 2x daily alerts

**Recommendation**: Implement **Slack or Discord first** (free, easy), add **Email** for non-technical recipients

**Effort**: Low-Medium (1-2 days per channel)
**Value**: High - immediate awareness

---

#### 8. Enhanced Event Context
**Problem**: Alerts lack actionable context
**Solution**: Add more information to alerts

**Additional Data to Include**:
- 📊 **Consensus estimates** (what market expects)
- 📈 **Previous values** (last release)
- ⏰ **Release time** (8:30 AM ET, 10:00 AM ET, etc.)
- 📉 **Historical volatility** (avg market move on this event)
- 🎯 **Market expectations** (dovish/hawkish for FOMC)
- 🔄 **Recent trend** (3-month direction)
- ⚠️ **Risk level** (based on consensus spread)

**Enhanced Alert Example**:
```
📅 UPCOMING HIGH IMPACT EVENTS

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 CPI Release - October 2025
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📅 Date: Wednesday, Oct 10, 2025 @ 8:30 AM ET
🎯 Consensus: 2.3% YoY (Range: 2.2% - 2.5%)
📈 Previous: 2.5% YoY (Month-over-month: -0.2%)
📊 3-Month Trend: Declining ↓
⚠️  Impact: HIGH
📉 Avg Market Move: ±0.8% (SPY)
🔔 IV Percentile: 65% (elevated)

💡 Trading Notes:
• Higher than expected (>2.4%) = Bearish
• In-line (2.2%-2.4%) = Neutral
• Lower than expected (<2.2%) = Bullish
• Watch 10Y Treasury yield reaction

🔗 Links:
• BLS Release: https://bls.gov/cpi
• MarketWatch Coverage: https://mw.com/...
• TradingView Chart: https://tradingview.com/...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Implementation**: Integrate with Trading Economics or Alpha Vantage API

**Effort**: Medium (3-4 days)
**Value**: High - actionable intelligence

---

#### 9. Calendar Export
**Problem**: Can't add events to personal calendar
**Solution**: Generate iCal/Google Calendar compatible files

**Implementation**:
```python
from icalendar import Calendar, Event
from datetime import datetime

def generate_ical_calendar(events):
    """Generate iCalendar file for economic events."""
    cal = Calendar()
    cal.add('prodid', '-//Economic Events Calendar//EN')
    cal.add('version', '2.0')
    cal.add('name', 'Market Events')
    cal.add('x-wr-calname', 'High-Impact Economic Events')

    for event_data in events:
        event = Event()
        event.add('summary', f"{event_data['event']} [{event_data['expected_impact']}]")
        event.add('dtstart', datetime.combine(event_data['date'], datetime.min.time()))
        event.add('dtend', datetime.combine(event_data['date'], datetime.min.time()))
        event.add('description', f"Impact: {event_data['expected_impact']}\nType: {event_data['event_type']}")
        event.add('categories', [event_data['event_type'], 'Market Events'])
        event.add('priority', 5 if event_data['expected_impact'] == 'Very High' else 3)

        # Add alerts
        if event_data['expected_impact'] in ['High', 'Very High']:
            alarm = Alarm()
            alarm.add('trigger', timedelta(days=-1))  # 1 day before
            alarm.add('action', 'DISPLAY')
            alarm.add('description', f"High-impact event tomorrow: {event_data['event']}")
            event.add_component(alarm)

        cal.add_component(event)

    return cal.to_ical()
```

**Usage**:
```python
# Generate and save
ical_data = generate_ical_calendar(events_df.to_dict('records'))
with open('data/market_events.ics', 'wb') as f:
    f.write(ical_data)
```

**Distribution Options**:
- Host on GitHub Pages
- Google Calendar subscription URL
- Add to workflow artifacts
- Email as attachment

**Effort**: Low (1-2 days)
**Value**: Medium - convenience

---

#### 10. Event Impact Analysis
**Problem**: No historical context on market reactions
**Solution**: Analyze past market moves around events

**Implementation**:
```python
def analyze_event_historical_impact(event_type, lookback_months=24):
    """Analyze historical market reaction to specific event type."""

    # Get historical events
    hist_events = events_df[
        (events_df['event_type'] == event_type) &
        (events_df['date'] < pd.Timestamp.now()) &
        (events_df['date'] > pd.Timestamp.now() - pd.DateOffset(months=lookback_months))
    ]

    results = []
    for _, event in hist_events.iterrows():
        # Fetch market data around event
        event_date = event['date']
        spy_data = yf.download('SPY',
                               start=event_date - timedelta(days=5),
                               end=event_date + timedelta(days=5))

        # Calculate metrics
        day_before = spy_data['Close'].iloc[-6]
        day_of = spy_data['Close'].iloc[-5]
        day_after = spy_data['Close'].iloc[-4]
        week_after = spy_data['Close'].iloc[-1]

        results.append({
            'date': event_date,
            'event': event['event'],
            'actual': event.get('actual'),
            'consensus': event.get('consensus'),
            'surprise': event.get('surprise'),
            'day_of_return': ((day_of - day_before) / day_before) * 100,
            'day_after_return': ((day_after - day_of) / day_of) * 100,
            'week_return': ((week_after - day_of) / day_of) * 100,
            'day_of_volume_spike': spy_data['Volume'].iloc[-5] / spy_data['Volume'].iloc[-6:-5].mean()
        })

    impact_df = pd.DataFrame(results)

    # Summary statistics
    summary = {
        'event_type': event_type,
        'sample_size': len(impact_df),
        'avg_day_of_move': impact_df['day_of_return'].abs().mean(),
        'avg_week_move': impact_df['week_return'].abs().mean(),
        'max_day_move': impact_df['day_of_return'].abs().max(),
        'volatility_spike': impact_df['day_of_volume_spike'].mean(),
        'positive_reaction_pct': (impact_df['day_of_return'] > 0).sum() / len(impact_df) * 100
    }

    return summary, impact_df
```

**Insights Generated**:
- Average market move on CPI days: ±0.8%
- FOMC days average move: ±1.2%
- NFP "surprise" correlation with returns
- IV expansion patterns pre-event
- Sector rotation after specific events

**ML Model Features**:
- Event type
- Consensus spread (uncertainty measure)
- Previous 3-month trend
- Market regime (bull/bear)
- VIX level
- Days since last event
- Time of day

**Effort**: High (5-7 days)
**Value**: Very High - predictive capabilities

---

#### 11. TradingView Integration
**Problem**: Can't see events on trading charts
**Solution**: Create TradingView alerts or indicators

**Option A: Pine Script Indicator**
```pinescript
//@version=5
indicator("Economic Events", overlay=true)

// Economic event dates (manually updated or from webhook)
cpi_dates = array.new_int()
array.push(cpi_dates, timestamp("2025-10-10"))
array.push(cpi_dates, timestamp("2025-11-13"))

fomc_dates = array.new_int()
array.push(fomc_dates, timestamp("2025-11-05"))

// Check if current bar is an event date
is_cpi = array.includes(cpi_dates, time)
is_fomc = array.includes(fomc_dates, time)

// Plot markers
plotshape(is_cpi, "CPI", shape.triangleup, location.belowbar, color.orange, size=size.small)
plotshape(is_fomc, "FOMC", shape.circle, location.belowbar, color.red, size=size.normal)

// Background highlighting
bgcolor(is_cpi ? color.new(color.orange, 90) : na)
bgcolor(is_fomc ? color.new(color.red, 90) : na)
```

**Option B: Webhook Alerts**
- Create TradingView alerts via API
- Triggered by GitHub workflow
- Sends notifications to TradingView mobile app

**Effort**: Low-Medium (2-3 days)
**Value**: Medium - visual integration

---

#### 12. Smart Filtering
**Problem**: Fixed 3-day window, no customization
**Solution**: Configurable alerts with user preferences

**Configuration File** (`alerts_config.json`):
```json
{
  "alert_window_days": 5,
  "skip_weekends": true,
  "event_types": {
    "FOMC": {
      "enabled": true,
      "advance_days": 7,
      "notify_channels": ["email", "slack"]
    },
    "CPI": {
      "enabled": true,
      "advance_days": 3,
      "notify_channels": ["slack"]
    },
    "NFP": {
      "enabled": true,
      "advance_days": 3,
      "notify_channels": ["slack"]
    },
    "GDP": {
      "enabled": false
    },
    "PCE": {
      "enabled": true,
      "advance_days": 2,
      "notify_channels": ["email"]
    }
  },
  "suppress_repeated": true,
  "repeated_threshold_hours": 24,
  "quiet_hours": {
    "enabled": true,
    "start": "22:00",
    "end": "06:00",
    "timezone": "US/Eastern"
  }
}
```

**Features**:
- Per-event type configuration
- Custom advance notice windows
- Channel-specific routing
- Suppress duplicate alerts
- Quiet hours (no alerts at night)
- Weekend skipping

**Effort**: Medium (3-4 days)
**Value**: High - personalization

---

#### 13. Multi-Market Support
**Problem**: US-only events
**Solution**: Add other major markets

**Markets to Add**:
- **Europe**: ECB decisions, Eurozone CPI/GDP
- **UK**: BoE decisions, UK CPI/GDP
- **Japan**: BoJ decisions, Tankan survey
- **China**: PMI, GDP, Trade data
- **Canada**: BoC decisions, Employment
- **Australia**: RBA decisions, Employment

**Implementation**: Similar structure to US events, with market identifier

**Effort**: Medium (4-5 days)
**Value**: Medium - for global traders

---

## Implementation Roadmap

### Phase 1: Critical Foundation (Week 1-2)
1. ✅ Add 2026+ event generation
2. ✅ Add missing high-impact events
3. ✅ Complete 2025 coverage

**Goal**: System works long-term without manual updates

---

### Phase 2: Data Quality (Week 3-4)
4. ✅ Integrate economic calendar API (Alpha Vantage or Trading Economics)
5. ✅ Add consensus & actual value tracking
6. ✅ Add revision tracking

**Goal**: Automated, high-quality data

---

### Phase 3: User Experience (Week 5-6)
7. ✅ Real notifications (Slack + Email)
8. ✅ Enhanced event context
9. ✅ Calendar export (iCal)

**Goal**: Actionable, accessible alerts

---

### Phase 4: Advanced Features (Week 7-8)
10. ✅ Event impact analysis
11. ✅ Smart filtering & preferences
12. ✅ TradingView integration

**Goal**: Predictive, personalized system

---

### Phase 5: Expansion (Week 9+)
13. ✅ Multi-market support
14. ✅ Mobile app (optional)
15. ✅ ML-based predictions (optional)

**Goal**: Comprehensive global solution

---

## Cost Estimates

### Free Tier (Current + Basic Improvements)
- GitHub Actions: Free (2,000 minutes/month)
- FRED API: Free (requires registration)
- Alpha Vantage: Free (500 calls/day)
- Slack/Discord: Free (unlimited)
- SendGrid: Free (100 emails/day)

**Total**: $0/month

---

### Professional Tier
- GitHub Actions: Free (sufficient for this)
- Trading Economics API: $79/month (Starter)
- SendGrid: $15/month (40K emails)
- Twilio SMS: ~$1/month (60 alerts)

**Total**: ~$95/month

---

### Enterprise Tier
- Trading Economics API: $249/month (Professional)
- SendGrid: $90/month (100K emails)
- AWS hosting (for API/dashboard): $20/month
- TradingView Premium: $60/month

**Total**: ~$419/month

---

## Technical Debt & Maintenance

### Current Technical Debt
1. **Hardcoded 2025 events** - Will break in 2026
2. **No automated testing** - Changes could break silently
3. **No data validation** - Invalid dates/values could cause errors
4. **No monitoring** - Can't detect issues proactively
5. **No backup system** - If GitHub Actions fails, no fallback

### Maintenance Requirements

**Weekly**:
- Monitor workflow runs for failures
- Check data quality (missing events, bad dates)

**Monthly**:
- Review and update consensus estimates
- Verify FRED API still working
- Check for new economic indicators to track

**Quarterly**:
- Update FOMC schedule (Fed publishes annually)
- Review event types (add new indicators)
- Analyze system performance

**Annually**:
- Generate next year's events
- Review and update impact classifications
- Audit data accuracy

---

## Success Metrics

### Key Performance Indicators

**Coverage**:
- Event types tracked: Target 15+ (currently 6)
- Events per year: Target 200+ (currently 61)
- Data accuracy: Target 99%+ (currently unmeasured)

**Timeliness**:
- Alert lead time: 3 days (achieved)
- Data freshness: <24 hours (FRED data achieved)
- Schedule change detection: Target <24 hours (not implemented)

**Usability**:
- Alert delivery success: Target 99.9%
- User engagement: Monitor click-through on links
- False positive rate: Target <5%

**Value**:
- Trading decisions influenced: Track via surveys
- Risk events avoided: Count position adjustments before events
- Portfolio protection: Measure drawdown reduction

---

## Conclusion

The current market events system provides a solid foundation with:
- ✅ Hardcoded calendar for major 2025 events
- ✅ FRED API integration for economic data
- ✅ Automated twice-daily workflows
- ✅ Basic alerting via GitHub Actions logs

However, significant improvements are needed for:
- ❌ Long-term sustainability (2026+ event generation)
- ❌ Data completeness (missing event types, consensus/actuals)
- ❌ User experience (real notifications, enhanced context)
- ❌ Advanced features (impact analysis, smart filtering)

**Recommended Next Steps**:
1. Implement **Phase 1** (2-3 days) to ensure system doesn't break in 2026
2. Choose an economic calendar API and implement **Phase 2** (1-2 weeks)
3. Add real notifications via **Slack + Email** (2-3 days)
4. Iterate on advanced features based on user feedback

**Expected Timeline**: 4-6 weeks for full implementation of Priority 1 & 2 items

**ROI**: High - automated, reliable market intelligence with minimal ongoing maintenance

---

**Last Updated**: October 13, 2025
**Version**: 1.0
**Author**: Market Events System Analysis
**Status**: Pending Implementation
