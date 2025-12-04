# Earnings Call Analysis Toolkit

Automated earnings call analysis for prediction markets using historical transcripts and recent news.

**Save 2+ hours per earnings event** with systematic, data-driven analysis of mention markets on Polymarket.

## Features

- 📊 **Historical Analysis**: Analyze 3-4 quarters of earnings transcripts to calculate baseline mention rates
- 📰 **News Research**: Automated Perplexity AI integration to adjust for recent developments
- 💰 **Edge Calculation**: Calculate fair values and identify mispriced markets
- 📈 **Portfolio Optimization**: Auto-scale positions to maximize expected value
- 🔄 **Market Monitoring**: Track spread tightening and reprice limits as earnings approaches
- 📝 **Report Generation**: Comprehensive markdown reports with all recommendations

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt

# Install Playwright for transcript fetching
playwright install chromium
```

### 2. API Key Setup

1. Get your Perplexity API key from: https://www.perplexity.ai/settings/api
2. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```
3. Add your API key to `.env`:
   ```
   PERPLEXITY_API_KEY=pplx-your-api-key-here
   ```

### 3. Run Complete Analysis

Example analyzing Coinbase Q4 2025 earnings:

```bash
# Step 0: Fetch historical transcripts (5-10 min)
python scripts/fetch_transcript.py \
  --url "https://www.gurufocus.com/stock/COIN/transcripts/Q3-2024" \
  --output transcripts/coinbase/Coinbase_Q3_2024_Transcript.md

# Repeat for Q4 2024, Q1 2025, Q2 2025...

# Step 1: Fetch market data (30 sec)
python scripts/fetch_market.py \
  --event-url "https://polymarket.com/event/earnings-mentions-coinbase-2025-10-29" \
  --output data/coinbase_q4_2025/markets.json

# Step 2: Analyze historical transcripts (1 min)
python scripts/analyze_transcripts.py \
  --transcripts "transcripts/coinbase/*.md" \
  --words data/coinbase_q4_2025/markets.json \
  --output data/coinbase_q4_2025/historical.json

# Step 3: Search recent news (2 min)
python scripts/search_news.py \
  --words data/coinbase_q4_2025/markets.json \
  --company "Coinbase" \
  --date "2025-10-29" \
  --output data/coinbase_q4_2025/news.json

# Step 4: Calculate edges (30 sec)
python scripts/calculate_edges.py \
  --historical data/coinbase_q4_2025/historical.json \
  --markets data/coinbase_q4_2025/markets.json \
  --news data/coinbase_q4_2025/news.json \
  --news-weight 0.3 \
  --output data/coinbase_q4_2025/edges_initial.json

# Step 5: Generate report (10 sec)
python scripts/generate_report.py \
  --edges data/coinbase_q4_2025/edges_initial.json \
  --company "Coinbase" \
  --quarter "Q4 2025" \
  --output reports/Coinbase_Q4_2025_Analysis.md
```

### 4. Monitor & Reprice (Days -2, -1, 0)

```bash
# Day -2 before earnings
python scripts/monitor_markets.py \
  --baseline data/coinbase_q4_2025/edges_initial.json \
  --event-url "https://polymarket.com/event/earnings-mentions-coinbase-2025-10-29" \
  --days-until-earnings 2 \
  --output data/coinbase_q4_2025/edges_day2.json \
  --changes data/coinbase_q4_2025/repricing_day2.md
```

## Workflow Overview

```
Step 0: Fetch Transcripts (10 min)
   ↓
Step 1: Fetch Markets (30 sec)
   ↓
Step 2: Analyze Historical (1 min)
   ↓
Step 3: Search News (2 min)
   ↓
Step 4: Calculate Edges (30 sec)
   ↓
Step 5: Generate Report (10 sec)
   ↓
Step 6: Monitor & Reprice (2-3 min, 2x daily)
```

**Total Time:** ~45 minutes per event (vs 3 hours manual)

## Output Files

```
data/coinbase_q4_2025/
├── markets.json           # Initial market snapshot
├── historical.json        # 4 quarters of mention data
├── news.json             # Perplexity research
├── edges_initial.json    # Baseline recommendations
└── edges_day2.json       # Updated with repricing

reports/
└── Coinbase_Q4_2025_Analysis.md  # Full analysis report (8-10 KB)
```

## Example Output

See `example/` directory for complete Coinbase Q4 2025 analysis with:
- 18 markets analyzed
- 11 STRONG conviction bets (>20% edge)
- 3 MODERATE conviction bets (10-20% edge)
- Full historical data and news research

## Documentation

- **[Complete Workflow Guide](docs/WORKFLOW.md)** - Detailed step-by-step instructions
- **Troubleshooting** - Common issues and solutions
- **Best Practices** - Tips for optimal results
- **Monitoring Strategy** - How to reprice as earnings approaches

## Requirements

- Python 3.9+
- Perplexity API key (get from [perplexity.ai](https://www.perplexity.ai/settings/api))
- Internet connection for API calls

## Contributing

This is v2 public release. Contributions welcome! Please:
1. Fork the repo
2. Create a feature branch
3. Submit a pull request

## License

MIT License - see [LICENSE](LICENSE) file for details

## Support

- **Issues**: Open a GitHub issue
- **Documentation**: See `docs/WORKFLOW.md`
- **Examples**: Check `example/` directory

---

**Version:** 2.0 (Public)
**Last Updated:** November 2025
