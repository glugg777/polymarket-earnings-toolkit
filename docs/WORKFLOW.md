# Earnings Call Analysis Workflow

**Version:** 1.0
**Last Updated:** October 26, 2025

---

## Prerequisites

### Required Files
- [ ] Historical earnings transcripts in `transcripts/{company}/`
  - Format: `{Company}_Q{n}_{year}_Transcript.md`
  - Minimum: 3-4 quarters for statistical validity
  - **Can be auto-fetched:** Use Step 0 (`fetch_transcript.py`) to download from GuruFocus
- [ ] Polymarket event URL with mention markets

### Dependencies
- Python 3.9+
- Required packages: `pip install -r requirements.txt`
  - requests
  - jinja2
  - python-dateutil
  - playwright
  - python-dotenv
  - openai (for Perplexity API via OpenAI client)

---

## Workflow Steps

### Step 0: Fetch Historical Transcripts (5-10 minutes)

**Purpose:** Download earnings call transcripts from GuruFocus for historical analysis

**Command:**
```bash
# Fetch transcripts for 4 most recent quarters
python scripts/fetch_transcript.py \
  --url "https://www.gurufocus.com/stock/MSFT/transcripts/Q4-2024" \
  --output transcripts/microsoft/Microsoft_Q4_2024_Transcript.md

python scripts/fetch_transcript.py \
  --url "https://www.gurufocus.com/stock/MSFT/transcripts/Q1-2025" \
  --output transcripts/microsoft/Microsoft_Q1_2025_Transcript.md

python scripts/fetch_transcript.py \
  --url "https://www.gurufocus.com/stock/MSFT/transcripts/Q2-2025" \
  --output transcripts/microsoft/Microsoft_Q2_2025_Transcript.md

python scripts/fetch_transcript.py \
  --url "https://www.gurufocus.com/stock/MSFT/transcripts/Q3-2025" \
  --output transcripts/microsoft/Microsoft_Q3_2025_Transcript.md
```

**Human Review:**
- ✓ Verify transcript files were created (should be 40,000-70,000 characters each)
- ✓ Check that company name and quarter metadata look correct
- ✓ Open one file to spot-check formatting (should have speaker headers like `### Satya Nadella`)

**Troubleshooting:**
- If Cloudflare blocks: Script will wait and retry automatically
- If transcript too short (<10,000 chars): URL may be incorrect or page structure changed
- If metadata missing: Non-critical, transcript content is what matters

**Note:** If you already have historical transcripts, you can skip this step. The analyzer in Step 2 expects transcripts in `transcripts/{company}/` with the naming pattern shown above.

---

### Step 1: Fetch Market Data (5 minutes)

**Command:**
```bash
python scripts/fetch_market.py \
  --event-url "https://polymarket.com/event/{slug}" \
  --output data/{company}_q{n}_{year}/markets.json
```

**Human Review:**
- ✓ Verify all expected words are captured
- ✓ Check pricing data looks reasonable
- ✓ Note any missing order book data

**Troubleshooting:**
- If slug extraction fails: Check URL format
- If API fails: Check internet connection, Polymarket API status

---

### Step 2: Analyze Historical Transcripts (5 minutes)

**Command:**
```bash
python scripts/analyze_transcripts.py \
  --transcripts "transcripts/{company}/*.md" \
  --words data/{company}_q{n}_{year}/markets.json \
  --output data/{company}_q{n}_{year}/historical.json
```

**Human Review:**
- ✓ Spot-check mention rates against manual review
- ✓ Verify quarter labels are correct
- ✓ Flag any suspicious patterns (e.g., 0 mentions of common word)

**Troubleshooting:**
- If no transcripts found: Check glob pattern, file naming
- If counts seem off: Verify word parsing (check for typos, variations)

---

### Step 3: Research Recent News (10 minutes)

**Command:**
```bash
python scripts/search_news.py \
  --words data/{company}_q{n}_{year}/markets.json \
  --company "{Company Name}" \
  --date "YYYY-MM-DD" \
  --output data/{company}_q{n}_{year}/news.json
```

**Human Review:**
- ✓ Review key findings for relevance
- ✓ Flag any high-impact operational news (e.g., production halt)
- ✓ Note speculation vs. confirmed facts

**Troubleshooting:**
- If MCP fails: Check MCP server status, API keys
- If results are off-topic: Refine search queries in script

---

### Step 4: Calculate Edges (3 minutes)

**Command:**
```bash
python scripts/calculate_edges.py \
  --historical data/{company}_q{n}_{year}/historical.json \
  --markets data/{company}_q{n}_{year}/markets.json \
  --news data/{company}_q{n}_{year}/news.json \
  --news-weight 0.3 \
  --output data/{company}_q{n}_{year}/edges.json
```

**Human Review:**
- ✓ Review top 5 recommendations for sanity
- ✓ Check if news adjustments are appropriate
- ✓ Adjust `--news-weight` if needed (0.0 = ignore news, 0.5 = equal weight)

**Troubleshooting:**
- If edges seem extreme: Review fair value calculation
- If conviction tiers are wrong: Adjust thresholds in script

---

### Step 5: Generate Report (2 minutes)

**Command:**
```bash
python scripts/generate_report.py \
  --edges data/{company}_q{n}_{year}/edges.json \
  --company "{Company Name}" \
  --quarter "Q{n} {year}" \
  --output reports/{Company}_Q{n}_{year}_Analysis.md
```

**Human Review:**
- ✓ Final review of report
- ✓ Add any custom analysis/scenarios
- ✓ Publish or share

---

### Step 6: Monitor Markets & Reprice (2-3 minutes per run, 4-6 runs)

**When:** Day -2, -1, 0 (last 3 days before earnings)
**Frequency:** 2x per day (morning & evening) or as needed
**Purpose:** Detect market maker arrival, conviction changes, repricing needs

**IMPORTANT: Manual Date Tracking Required**

The `--days-until-earnings` parameter is **NOT auto-calculated**. You must manually calculate and specify the time remaining:

```bash
# Example: Earnings on October 22, today is October 20
# Days until = 2.0

# If earnings is at 4 PM ET and it's currently 10 AM ET same day:
# Days until = 6 hours / 24 hours = 0.25
```

**Time-Based Repricing Formula:**

| Days Until | Formula | Target Fill Rate | Use Case |
|------------|---------|------------------|----------|
| ≥5 days | bid + 2¢ | 60% | Maximize profit margin |
| 3-4 days | bid + 20% spread | 70% | Slightly aggressive |
| 1-2 days | bid + 40% spread | 85% | Competitive pricing |
| <1 day | bid + 80% spread | 95% | Prioritize execution |

**Safety Rails (Always Applied):**
- Never exceed `fair_value - 5¢` (maintain minimum profit margin)
- Never bid below `best_bid + 1¢` (must improve market)

**Command:**
```bash
python scripts/monitor_markets.py \
  --baseline data/{company}_q{n}_{year}/edges_initial.json \
  --event-url "https://polymarket.com/event/{slug}" \
  --days-until-earnings 2 \
  --output data/{company}_q{n}_{year}/edges_day2_am.json \
  --changes data/{company}_q{n}_{year}/repricing_day2_am.md
```

**What it does:**
1. Loads baseline edges_initial.json (fair values, initial limits)
2. Fetches current market data (**BOTH YES and NO order books** via CLOB API)
3. Selects correct book based on side (YES → YES book, NO → NO book)
4. Recalculates edges with new prices
5. Downgrades conviction if edges shrunk (STRONG → MODERATE → PASS)
6. Applies time-based repricing (more aggressive as earnings approaches)
7. Rescales portfolio if conviction changes
8. Validates YES + NO prices (flags anomalies if sum ≠ $1.00 ± 20¢)
9. Generates change log showing only what changed

**Output:**
- `edges_day2_am.json` — Updated edges with new conviction/limits/books
- `repricing_day2_am.md` — Change log (3KB, focused on changes)

**Human Review:**
- ✓ Check change log for markets requiring repricing
- ✓ Note conviction downgrades (position size reductions)
- ✓ Review skip risk warnings (markets where bid jumped above our limit)
- ✓ **For NO-side bets:** Verify NO book data looks reasonable (limits should be lower than YES limits for same fair value)
- ✓ Decide whether to update orders on Polymarket
- ✓ Check if any markets need news refresh (>30% price move warnings)

**NO-Side Market Indicators:**

Change log shows `Side` column. For NO-side bets:
```markdown
| Market | Side | Old Limit | New Limit | Change |
|--------|------|-----------|-----------|--------|
| Cybersecurity | NO | $0.06 | $0.38 | +$0.32 |
```

**Expected behavior:**
- NO fair value = 1 - YES fair value (e.g., 0% YES → 100% NO)
- NO limits are typically lower (betting on underpriced NO = overpriced YES)
- NO book uses separate token (`clobTokenIds[1]`)

**Validation Checks (Automatic):**

The script validates:
1. ✅ NO book not empty (bid=$0.00 and ask=$0.00 → skip market)
2. ✅ YES + NO prices ≈ $1.00 (flags if >20¢ deviation)
3. ✅ Fair value within 0-1 range
4. ✅ Limits don't exceed fair value - 5¢

If validation fails, script prints warnings and keeps baseline recommendation unchanged.

**Optional: Conditional News Refresh**
If monitor flags markets with >30% price moves:
```bash
# Refresh news for specific markets
python scripts/search_news.py \
  --words <filtered_markets.json> \
  --company "{Company}" \
  --date "YYYY-MM-DD" \
  --output data/{company}_q{n}_{year}/news_refresh.json

# Recalculate edges with fresh news
python scripts/calculate_edges.py \
  --historical data/{company}_q{n}_{year}/historical.json \
  --markets data/{company}_q{n}_{year}/markets.json \
  --news data/{company}_q{n}_{year}/news_refresh.json \
  --output data/{company}_q{n}_{year}/edges_refreshed.json
```

**Optional: Regenerate Full Report**
```bash
# Generate updated comprehensive report (optional, usually not needed)
python scripts/generate_report.py \
  --edges data/{company}_q{n}_{year}/edges_day2_am.json \
  --company "{Company}" \
  --quarter "Q{n} {year}" \
  --output reports/{Company}_Q{n}_{year}_Day2.md
```

**Recommended approach:** Use change logs for day-to-day monitoring, optionally regenerate full report on Day 0 (final) for documentation.

**Troubleshooting:**
- If no markets need repricing: Great! Your initial limits are still competitive
- If ALL markets need repricing: Likely market makers arrived, spreads tightened significantly
- If conviction downgrades: Expected as markets move toward fair value, position sizes auto-adjust
- If validation warnings appear: Check API status, verify event URL is correct
- If scale factor changes significantly (>10%): Review conviction tier changes, ensure total allocation makes sense

---

### Change Log Interpretation Guide

**Executive Summary Section:**

```markdown
## Executive Summary

- **Conviction changes:** 1 markets
- **Repricing needed:** 9 markets (limit changed >10¢)
- **Spread tightened:** 1 markets (>30% tighter)
- **Edge deteriorated:** 1 markets (>5pp drop)

**Portfolio Allocation:**
- Baseline: 100.0% (0.606 scale factor)
- Updated: 100.0% (0.571 scale factor)
- **⚠️ Scale factor changed by -0.035** - affects ALL position sizes
```

**What this means:**
- **Conviction changes:** Markets moved between STRONG/MODERATE/PASS tiers (affects position sizing)
- **Repricing needed:** Your current limits may get skipped, adjust higher to improve fill rate
- **Spread tightened:** Market makers arrived, liquidity improved (good for execution)
- **Edge deteriorated:** Market price moved against you, consider news refresh
- **Scale factor change:** Raw allocation changed (e.g., upgrade MODERATE→STRONG increased total), all positions rescaled to maintain 100% max

**Conviction Tier Changes:**

```markdown
| Market | Old → New | Edge Change | Action Required |
|--------|-----------|-------------|--------------------|
| Gaming | MODERATE → STRONG | +16.0pp | ⬆️ Increase size |
```

**What to do:**
- **Upgrade (MOD→STRONG):** Edge increased, increase position size
- **Downgrade (STRONG→MOD):** Edge decreased, reduce position size
- **Downgrade to PASS:** Edge <10%, exit position or don't place order

**Markets Requiring Repricing:**

```markdown
| Market | Side | Old Limit | New Limit | Change | Skip Risk |
|--------|------|-----------|-----------|--------|-----------|
| Shutdown | NO | $0.04 | $0.41 | +0.37 | 🟡 MEDIUM |
| CapEx | YES | $0.03 | $0.40 | +0.37 | 🟢 LOW |
```

**What this means:**
- **Old Limit:** Your baseline recommendation (or last monitoring run)
- **New Limit:** Time-adjusted limit based on days remaining
- **Change:** How much higher you should bid to maintain target fill rate
- **Skip Risk:**
  - 🔴 HIGH: Current best_bid > your old limit (you'll be skipped if not updated)
  - 🟡 MEDIUM: Current best_bid close to your limit (update recommended)
  - 🟢 LOW: Still competitive, but updating improves fill probability

**What to do:**
1. 🔴 HIGH risk: Update immediately (or you won't get filled)
2. 🟡 MEDIUM risk: Update within 12 hours
3. 🟢 LOW risk: Optional update (balances profit vs. execution)

**Spreads Tightened:**

```markdown
- **Azure**
  - Spread: 99% → 13% (-87% change)
```

**What this means:**
- Market makers arrived, liquidity improved dramatically
- Your old limit may be too low now (market is more efficient)
- Consider repricing upward even if not flagged in repricing table

**Edge Deteriorated:**

```markdown
- **CapEx**
  - Edge: +18.0% → +10.5% (-7.5pp)
```

**What this means:**
- Market price moved against you (market thinks it's more likely than you do)
- Still positive edge (10.5%), but conviction may downgrade (STRONG→MODERATE)
- **Consider:** News refresh to see if something changed

**NO-Side Markets:**

For NO-side bets, change log shows `Side = NO`:

```markdown
| Market | Side | Old Limit | New Limit | Change |
|--------|------|-----------|-----------|--------|
| Cybersecurity | NO | $0.06 | $0.38 | +$0.32 |
```

**Sanity checks:**
- ✓ NO limit < YES limit (for similar fair values)
- ✓ NO fair value = 1 - YES fair value (printed in logs)
- ✓ NO book bid/ask reasonable (not $0.00/$0.00)

**Progression Example (Server market, YES-side):**

| Day | Formula | Limit | Change | Rationale |
|-----|---------|-------|--------|-----------|
| -5 | bid + 2¢ | $0.14 | - | Baseline (maximize profit) |
| -3 | bid + 20% spread | $0.29 | +$0.15 | Slightly aggressive |
| -1 | bid + 40% spread | $0.47 | +$0.18 | Competitive |
| 0 | bid + 80% spread | $0.82 | +$0.35 | Very aggressive (prioritize fill) |

**Total increase: $0.68 from Day -5 to Day 0**

---

## Example: Microsoft Q3 2025 (Complete Workflow with Monitoring)

### Day -5 (October 17): Initial Analysis

```bash
# Create directories
mkdir -p data/microsoft_q3_2025 reports transcripts/microsoft

# Step 0: Fetch historical transcripts (if needed)
# Skip this if you already have transcripts in transcripts/microsoft/
python scripts/fetch_transcript.py \
  --url "https://www.gurufocus.com/stock/MSFT/transcripts/Q4-2024" \
  --output transcripts/microsoft/Microsoft_Q4_2024_Transcript.md

python scripts/fetch_transcript.py \
  --url "https://www.gurufocus.com/stock/MSFT/transcripts/Q1-2025" \
  --output transcripts/microsoft/Microsoft_Q1_2025_Transcript.md

python scripts/fetch_transcript.py \
  --url "https://www.gurufocus.com/stock/MSFT/transcripts/Q2-2025" \
  --output transcripts/microsoft/Microsoft_Q2_2025_Transcript.md

# Step 1: Fetch markets (Phase 1)
python scripts/fetch_market.py \
  --event-url "https://polymarket.com/event/what-will-microsoft-msft-say-during-their-next-earnings-call" \
  --output data/microsoft_q3_2025/markets.json

# Step 2: Analyze transcripts (Phase 2)
python scripts/analyze_transcripts.py \
  --transcripts "transcripts/microsoft/*_Transcript.md" \
  --words data/microsoft_q3_2025/markets.json \
  --output data/microsoft_q3_2025/historical.json

# Step 3: Search news (Phase 3)
python scripts/search_news.py \
  --words data/microsoft_q3_2025/markets.json \
  --company "Microsoft" \
  --date "2025-10-22" \
  --output data/microsoft_q3_2025/news.json

# Step 4: Calculate edges (Phase 4)
python scripts/calculate_edges.py \
  --historical data/microsoft_q3_2025/historical.json \
  --markets data/microsoft_q3_2025/markets.json \
  --news data/microsoft_q3_2025/news.json \
  --output data/microsoft_q3_2025/edges_initial.json  # Note: _initial suffix

# Step 5: Generate initial report (Phase 5)
python scripts/generate_report.py \
  --edges data/microsoft_q3_2025/edges_initial.json \
  --company "Microsoft" \
  --quarter "Q3 2025" \
  --output reports/microsoft_q3_2025_initial.md
```

**Output Files:**
- `data/microsoft_q3_2025/markets.json` (snapshot of order books)
- `data/microsoft_q3_2025/historical.json` (4 quarters of mention data)
- `data/microsoft_q3_2025/news.json` (Perplexity research on 17 markets)
- `data/microsoft_q3_2025/edges_initial.json` (baseline recommendations)
- `reports/microsoft_q3_2025_initial.md` (comprehensive 8KB report)

**Time:** ~25 minutes
**Action:** Review report, place initial limit orders on Polymarket

---

### Day -2 (October 20): Morning Monitor Run

```bash
# Calculate days until earnings
# Earnings: October 22 at 4 PM ET
# Today: October 20 at 9 AM ET
# Time remaining: 2 days + 7 hours = 2.29 days
# Round to: 2 days for formula selection

# Step 6a: Monitor markets (Phase 4.5)
python scripts/monitor_markets.py \
  --baseline data/microsoft_q3_2025/edges_initial.json \
  --event-url "https://polymarket.com/event/what-will-microsoft-msft-say-during-their-next-earnings-call" \
  --days-until-earnings 2 \
  --output data/microsoft_q3_2025/edges_day2_am.json \
  --changes data/microsoft_q3_2025/repricing_day2_am.md

# Review change log
cat data/microsoft_q3_2025/repricing_day2_am.md
```

**Output:**
- `repricing_day2_am.md` — Change log shows:
  - 3 markets need repricing (spread tightened >30%)
  - 1 conviction downgrade (Azure: STRONG → MODERATE)
  - Server market at high skip risk (bid jumped to $0.55, our limit $0.14)
  - Formula used: bid + 40% spread (1-2 days tier)

**Time:** 2 minutes
**Action:** Update limit orders for 3 flagged markets

---

### Day -2 (October 20): Evening Monitor Run

```bash
# Calculate days until earnings
# Earnings: October 22 at 4 PM ET
# Today: October 20 at 8 PM ET
# Time remaining: 1 day + 20 hours = 1.83 days
# Round to: 1.5 days

# Step 6b: Monitor again (evening check)
python scripts/monitor_markets.py \
  --baseline data/microsoft_q3_2025/edges_initial.json \
  --event-url "https://polymarket.com/event/what-will-microsoft-msft-say-during-their-next-earnings-call" \
  --days-until-earnings 1.5 \
  --output data/microsoft_q3_2025/edges_day2_pm.json \
  --changes data/microsoft_q3_2025/repricing_day2_pm.md
```

**Output:**
- Minimal changes since morning
- 1 market price moved >30% → News refresh recommended
- Formula used: bid + 40% spread (1-2 days tier)

---

### Day -1 (October 21): Final Adjustments

```bash
# Calculate days until earnings
# Earnings: October 22 at 4 PM ET
# Today: October 21 at 10 AM ET
# Time remaining: 1 day + 6 hours = 1.25 days
# Round to: 1 day

# Step 6c: Monitor (day before earnings)
python scripts/monitor_markets.py \
  --baseline data/microsoft_q3_2025/edges_initial.json \
  --event-url "https://polymarket.com/event/what-will-microsoft-msft-say-during-their-next-earnings-call" \
  --days-until-earnings 1 \
  --output data/microsoft_q3_2025/edges_day1_am.json \
  --changes data/microsoft_q3_2025/repricing_day1_am.md
```

**Output:**
- Time formula now bid + 40% spread (competitive tier)
- 5 markets need repricing upward to avoid skips
- No conviction changes

**Action:** Final limit order updates

---

### Day 0 (October 22): Earnings Day

```bash
# Calculate days until earnings
# Earnings: October 22 at 4 PM ET
# Today: October 22 at 10 AM ET
# Time remaining: 6 hours = 0.25 days

# Step 6d: Final monitor (hours before earnings)
python scripts/monitor_markets.py \
  --baseline data/microsoft_q3_2025/edges_initial.json \
  --event-url "https://polymarket.com/event/what-will-microsoft-msft-say-during-their-next-earnings-call" \
  --days-until-earnings 0.25 \
  --output data/microsoft_q3_2025/edges_final.json \
  --changes data/microsoft_q3_2025/repricing_final.md

# Optional: Generate final comprehensive report for documentation
python scripts/generate_report.py \
  --edges data/microsoft_q3_2025/edges_final.json \
  --company "Microsoft" \
  --quarter "Q3 2025" \
  --output reports/microsoft_q3_2025_final.md
```

**Output:**
- Final recommendations with Day 0 aggressive pricing (bid + 80% spread)
- Formula used: bid + 80% spread (<1 day tier, very aggressive)
- Optional final comprehensive report for archival

**Action:** Last chance to fill any pending orders

---

### File Structure After Complete Workflow

```
data/microsoft_q3_2025/
├── markets.json                    # Initial snapshot (Day -5)
├── historical.json                 # Quarterly mention data (stable)
├── news.json                       # Initial news research (Day -5)
├── edges_initial.json              # Baseline recommendations (Day -5)
├── edges_day2_am.json              # Updated (Day -2 AM)
├── edges_day2_pm.json              # Updated (Day -2 PM)
├── edges_day1_am.json              # Updated (Day -1 AM)
├── edges_final.json                # Final (Day 0)
├── repricing_day2_am.md            # Change log (Day -2 AM)
├── repricing_day2_pm.md            # Change log (Day -2 PM)
├── repricing_day1_am.md            # Change log (Day -1 AM)
└── repricing_final.md              # Change log (Day 0)

reports/
├── microsoft_q3_2025_initial.md    # Comprehensive report (Day -5, 8KB)
└── microsoft_q3_2025_final.md      # Final comprehensive report (Day 0, 8KB, optional)
```

---

### Total Time Investment

| Phase | Day | Time | Cumulative |
|-------|-----|------|------------|
| **Step 0: Fetch Transcripts** | -5 | 10 min | 10 min |
| **Steps 1-5: Initial Analysis** | -5 | 25 min | 35 min |
| **Monitor Run 1** | -2 AM | 2 min | 37 min |
| **Monitor Run 2** | -2 PM | 2 min | 39 min |
| **Monitor Run 3** | -1 AM | 2 min | 41 min |
| **Monitor Run 4** | 0 | 2 min | 43 min |
| **Optional Final Report** | 0 | 2 min | 45 min |

**Total:** 43-45 minutes per event (vs. 3 hours manual)
**Time saved:** ~2.25 hours per event × 17 events = **38 hours**

**Note:** Step 0 (transcript fetching) is a one-time setup. If you already have transcripts or reuse them across multiple earnings events, the per-event time drops to 33-35 minutes.

---

## Conversational Orchestration with Claude

The entire workflow can be orchestrated through natural language with Claude Code. Here's a realistic conversation showing how to analyze Microsoft Q4 2025 earnings:

---

**You:** I want to analyze Microsoft's Q4 2025 earnings call. The event is happening October 29, 2025 at 4 PM ET. Here's the Polymarket event URL:
https://polymarket.com/event/what-will-microsoft-msft-say-during-their-next-earnings-call

**Claude:** I'll help you analyze this earnings event. Let me start by setting up the directory structure and checking what historical transcripts we have.

```bash
mkdir -p data/microsoft_q4_2025 reports
ls transcripts/microsoft/
```

Do you have historical transcripts already, or should I fetch them from GuruFocus?

---

**You:** I don't have transcripts yet. Can you fetch the last 4 quarters (Q1-Q4 2025) from GuruFocus?

Here are the URLs:
- Q1 2025: https://www.gurufocus.com/stock/MSFT/transcripts/3015001
- Q2 2025: https://www.gurufocus.com/stock/MSFT/transcripts/3015002
- Q3 2025: https://www.gurufocus.com/stock/MSFT/transcripts/3015003
- Q4 2024: https://www.gurufocus.com/stock/MSFT/transcripts/3015000

**Claude:** Perfect! I'll fetch all 4 transcripts now. This will take about 2-3 minutes per transcript.

**[Step 0: Fetch Historical Transcripts]**
```bash
mkdir -p transcripts/microsoft

python scripts/fetch_transcript.py \
  --url "https://www.gurufocus.com/stock/MSFT/transcripts/3015000" \
  --output transcripts/microsoft/Microsoft_Q4_2024_Transcript.md

python scripts/fetch_transcript.py \
  --url "https://www.gurufocus.com/stock/MSFT/transcripts/3015001" \
  --output transcripts/microsoft/Microsoft_Q1_2025_Transcript.md

python scripts/fetch_transcript.py \
  --url "https://www.gurufocus.com/stock/MSFT/transcripts/3015002" \
  --output transcripts/microsoft/Microsoft_Q2_2025_Transcript.md

python scripts/fetch_transcript.py \
  --url "https://www.gurufocus.com/stock/MSFT/transcripts/3015003" \
  --output transcripts/microsoft/Microsoft_Q3_2025_Transcript.md
```

✓ Fetched 4 transcripts:
- Q4_2024: 52,441 characters
- Q1_2025: 56,841 characters
- Q2_2025: 53,158 characters
- Q3_2025: 49,701 characters

All transcripts look good. Ready to proceed to market data fetching.

---

**You:** Great! Now fetch the market data from that Polymarket URL.

**Claude:** I'll fetch the market data now.

**[Step 1: Fetch Market Data]**
```bash
python scripts/fetch_market.py \
  --event-url "https://polymarket.com/event/what-will-microsoft-msft-say-during-their-next-earnings-call" \
  --output data/microsoft_q4_2025/markets.json
```

✓ Successfully fetched 17 markets:
- Cloud (8.9%)
- Azure (7.4%)
- AI (6.2%)
- Gaming (4.5%)
- Copilot (3.8%)
- Security (3.2%)
... and 11 more

All markets have complete order book data. Would you like to proceed with historical analysis?

---

**You:** Yes, analyze the historical transcripts against these markets.

**Claude:** I'll analyze all 4 transcripts to calculate historical mention rates.

**[Step 2: Analyze Historical Transcripts]**
```bash
python scripts/analyze_transcripts.py \
  --transcripts "transcripts/microsoft/*.md" \
  --words data/microsoft_q4_2025/markets.json \
  --output data/microsoft_q4_2025/historical.json
```

✓ Analyzed 4 quarters of transcripts:
- Found 17 markets to track
- Calculated mention rates for each quarter
- Detected trends: "Cloud" mentions increasing (12 → 18), "Gaming" stable (6-7), "Copilot" new term (0 → 8)

Key findings:
- **Cloud**: 14.5 avg mentions (high volatility, σ=3.2)
- **AI**: 9.2 avg mentions (trending up strongly)
- **Security**: 4.8 avg mentions (stable)

Ready for news research?

---

**You:** Yes, search recent news. The earnings call is October 29, 2025.

**Claude:** I'll search for relevant news about Microsoft related to each market.

**[Step 3: Research Recent News]**
```bash
python scripts/search_news.py \
  --words data/microsoft_q4_2025/markets.json \
  --company "Microsoft" \
  --date "2025-10-29" \
  --output data/microsoft_q4_2025/news.json
```

✓ Researched 17 markets via Perplexity API (took 45 seconds with rate limiting)

Notable findings:
- **Azure**: Major announcement Oct 15 about new datacenter expansion (+bullish for mentions)
- **Gaming**: Xbox sales down 12% in Q4 (analysts predicting defensive posture, -bearish for mentions)
- **Copilot**: Enterprise adoption up 40% (likely to be emphasized, +bullish)

All news research complete. Ready to calculate edges?

---

**You:** Yes, calculate edges. Use a news weight of 0.3.

**Claude:** I'll calculate fair values and edges now.

**[Step 4: Calculate Edges]**
```bash
python scripts/calculate_edges.py \
  --historical data/microsoft_q4_2025/historical.json \
  --markets data/microsoft_q4_2025/markets.json \
  --news data/microsoft_q4_2025/news.json \
  --news-weight 0.3 \
  --output data/microsoft_q4_2025/edges_initial.json
```

✓ Calculated edges for 17 markets:

**Top 5 Recommendations:**
1. **Cloud 8+ times** (STRONG, +32% edge) - YES at $0.41 vs fair $0.73 → Limit $0.68
2. **Copilot 4+ times** (STRONG, +24% edge) - YES at $0.52 vs fair $0.76 → Limit $0.71
3. **Gaming 7+ times** (MODERATE, +15% edge) - NO at $0.68 vs fair $0.53 → Limit $0.48
4. **Security 5+ times** (MODERATE, +12% edge) - YES at $0.58 vs fair $0.70 → Limit $0.65
5. **AI 10+ times** (MODERATE, +11% edge) - YES at $0.62 vs fair $0.73 → Limit $0.68

Portfolio allocation: 100% (scaled from 165% raw)

Ready to generate report?

---

**You:** Yes, generate the full report.

**Claude:** I'll create a comprehensive markdown report now.

**[Step 5: Generate Report]**
```bash
python scripts/generate_report.py \
  --edges data/microsoft_q4_2025/edges_initial.json \
  --company "Microsoft" \
  --quarter "Q4 2025" \
  --output reports/Microsoft_Q4_2025_Analysis.md
```

✓ Report generated: `reports/Microsoft_Q4_2025_Analysis.md` (7.8 KB)

Report includes:
- Executive summary with top recommendations
- 3 STRONG conviction bets (25% position each)
- 7 MODERATE conviction bets (15% position each)
- 7 PASS markets (edges <10%)
- Historical trends and news adjustments
- Risk analysis and methodology

**Next steps:**
1. Review the report and place initial limit orders on Polymarket
2. Starting Day -2 (October 27), run `monitor_markets.py` twice daily to track spread tightening and adjust limits

Would you like me to explain any specific recommendation in detail?

---

**You:** The Cloud recommendation looks aggressive. Can you break down why the edge is so high?

**Claude:** Let me examine the Cloud market calculation:

**Historical Pattern (70% of weight):**
- Q4 2024: 12 mentions
- Q1 2025: 14 mentions
- Q2 2025: 18 mentions (Azure expansion announcement)
- Q3 2025: 15 mentions
- **Average: 14.75 mentions**, threshold is 8+ → 100% hit rate historically

**News Adjustment (+bullish, 30% of weight):**
- October 15: Microsoft announces $10B datacenter expansion in Texas
- October 20: Analyst report predicts "cloud will dominate earnings narrative"
- Perplexity conclusion: 85% confidence mentions will be HIGH

**Combined Fair Value:** 73% chance of 8+ mentions
**Market Price:** 41% (YES side)
**Edge:** +32 percentage points

**Why the market is mispriced:**
The market is pricing in ~40% chance, but historical data + recent bullish news suggests ~73%. This creates a large edge. The STRONG conviction (25% position) reflects high confidence due to:
1. Consistent historical pattern (low variance)
2. Confirming recent news
3. Wide spread (low liquidity → less efficient pricing)

Make sense?

---

**You:** That makes sense. It's October 27 now, 2 days before earnings. Can you monitor the markets and check if I need to reprice my limits?

**Claude:** I'll check current market conditions and calculate time-adjusted limits.

**[Step 6: Monitor Markets]**
```bash
python scripts/monitor_markets.py \
  --baseline data/microsoft_q4_2025/edges_initial.json \
  --event-url "https://polymarket.com/event/what-will-microsoft-msft-say-during-their-next-earnings-call" \
  --days-until-earnings 2 \
  --output data/microsoft_q4_2025/edges_day2_am.json \
  --changes data/microsoft_q4_2025/repricing_day2_am.md
```

**Change Log Summary:**

⚠️ **3 markets need repricing** (spreads tightened, market makers arrived):

| Market | Old Limit | New Limit | Change | Skip Risk |
|--------|-----------|-----------|--------|-----------|
| Cloud 8+ | $0.68 | $0.85 | +$0.17 | 🔴 HIGH (bid jumped to $0.72) |
| Copilot 4+ | $0.71 | $0.79 | +$0.08 | 🟡 MEDIUM |
| Gaming 7+ (NO) | $0.48 | $0.52 | +$0.04 | 🟢 LOW |

**Conviction changes:** 1 market
- Security 5+: MODERATE → PASS (edge dropped to 8% after spread tightened)

**Recommendation:**
1. **Update Cloud limit immediately** to $0.85 (or you'll get skipped)
2. Update Copilot limit to $0.79 within 12 hours
3. Gaming limit is still competitive but can be improved

New formula: bid + 40% spread (2 days until earnings)

Would you like me to run another check this evening?

---

**You:** Yes, check again at 8 PM tonight (still Day -2).

**Claude:** I'll run the evening monitoring check now.

```bash
python scripts/monitor_markets.py \
  --baseline data/microsoft_q4_2025/edges_initial.json \
  --event-url "https://polymarket.com/event/what-will-microsoft-msft-say-during-their-next-earnings-call" \
  --days-until-earnings 1.67 \
  --output data/microsoft_q4_2025/edges_day2_pm.json \
  --changes data/microsoft_q4_2025/repricing_day2_pm.md
```

✓ Minimal changes since morning:
- Cloud spread still tight (you should have updated to $0.85 already)
- No new conviction changes
- 1 market (Copilot) showed 15% price move, but within normal range

**Action:** Continue monitoring tomorrow morning (Day -1).

---

**Summary of Conversational Workflow:**

This natural language orchestration allows you to:
1. **Guide the process** - Provide URLs and parameters conversationally
2. **Review at each step** - See summaries before proceeding
3. **Ask questions** - Get detailed explanations of recommendations
4. **Adjust parameters** - Change news weights, filters, etc. on the fly
5. **Monitor iteratively** - Check markets multiple times as earnings approaches

**Time saved:** ~2.5 hours vs manual analysis (5 minutes per phase vs 20-30 minutes)

---

## Tips & Best Practices

### Initial Analysis (Phases 1-5)

1. **Always review historical analysis** - Spot-check against manual count
2. **Be skeptical of news** - Filter through "earnings call lens"
3. **Adjust news weight** - Use 0.2-0.3 for most cases, 0.4-0.5 for major operational news
4. **Cross-reference** - Compare recommendations to manual intuition
5. **Document exceptions** - Note any manual overrides in report

### Market Monitoring (Phase 4.5)

6. **Track earnings date manually** - Set calendar reminder to calculate `--days-until-earnings` before each run
7. **Run 2x per day minimum** - Morning & evening checks catch market maker arrival
8. **Prioritize HIGH skip risk** - Update these immediately to avoid missing fills
9. **Don't chase spreads** - If spread tightened but edge <10%, consider passing
10. **For NO-side markets** - Verify NO book exists (not $0/$0) and limits make sense
11. **Monitor scale factor changes** - >5% change means conviction shifted, review position sizes
12. **Use change logs, not full reports** - Faster to review, focuses on what matters
13. **News refresh is optional** - Only needed if >30% price move without news in your analysis
14. **Trust the formula** - Time-based repricing balances profit vs. execution, don't second-guess
15. **Archive baseline file** - Save `edges_initial.json` separately, don't overwrite with monitoring runs

---

## Common Issues

### Initial Analysis Issues

**Issue:** Script can't find transcripts
**Solution:** Check glob pattern, verify filenames match expected format

**Issue:** Order book data missing
**Solution:** Some markets may not have active trading, use YES price as fallback

**Issue:** News results irrelevant
**Solution:** Refine search queries in `search_news.py`

**Issue:** Fair value seems wrong
**Solution:** Check historical analysis, verify word parsing is correct

### Monitoring Issues

**Issue:** Warning: "Empty order book for NO side"
**Solution:** NO market has no liquidity. Keep baseline recommendation or skip market. Script automatically handles this.

**Issue:** Warning: "Pricing anomaly - YES mid + NO mid ≠ $1.00"
**Solution:** API data issue or extreme spread. Check Polymarket website directly. Script keeps baseline unchanged.

**Issue:** All limits jump dramatically (>$0.50)
**Solution:** Likely miscalculated `--days-until-earnings`. Verify current time vs. earnings time.

**Issue:** No markets flagged for repricing
**Solution:** Normal if spreads haven't tightened. Your baseline limits are still competitive.

**Issue:** Scale factor shows NA or error
**Solution:** All markets are PASS conviction (no positions). Either edges deteriorated significantly or baseline had issues.

**Issue:** NO-side limit higher than YES-side limit
**Solution:** Bug or data error. NO limits should be lower for overpriced markets. Check logs for validation warnings.

**Issue:** Change log shows conviction downgrade but edge increased
**Solution:** NOT POSSIBLE - edge and conviction move together. Likely looking at different markets or comparing wrong baseline.

---

*For questions or issues, refer to implementation plan: `docs/implementation-plans/EARNINGS_ANALYSIS_SCRIPTS_IMPLEMENTATION_PLAN.md`*
