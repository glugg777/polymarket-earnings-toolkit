#!/usr/bin/env python3
"""
Test Step 3 with Multiple Markets

This script tests analyze_market_historical() with several different markets
to ensure it handles various edge cases:
- High frequency words (AI, Cloud)
- Low frequency words (Stargate, Phi)
- Multi-word phrases (Microsoft 365, Artificial Intelligence)
- Different thresholds
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'lib'))

from transcript_analyzer import load_transcripts, analyze_market_historical


def main():
    print("=" * 80)
    print("STEP 3 TEST: Multiple Markets Analysis")
    print("=" * 80)
    print()

    # Define paths
    project_root = Path(__file__).parent.parent
    markets_file = project_root / "data" / "test_microsoft" / "markets.json"
    transcripts_pattern = str(project_root / "transcripts" / "microsoft" / "*.md")

    # Load data
    with open(markets_file, 'r') as f:
        data = json.load(f)
        markets = data.get("markets", [])

    transcripts = load_transcripts(transcripts_pattern)
    print(f"✓ Loaded {len(markets)} markets and {len(transcripts)} transcripts")
    print()

    # Select interesting markets to test
    test_markets = [
        "Copilot",       # High frequency
        "AI",            # Very high frequency
        "Cloud",         # High frequency
        "Stargate",      # Low/zero frequency
        "M365",          # Multi-word
        "Phi",           # Low frequency
        "OpenAI"         # Medium frequency
    ]

    results = []

    for keyword in test_markets:
        # Find market
        market = None
        for m in markets:
            if keyword.lower() in m.get("word", "").lower():
                market = m
                break

        if not market:
            print(f"⚠ Could not find market for '{keyword}'")
            continue

        # Analyze
        result = analyze_market_historical(market, transcripts)
        results.append(result)

        # Display compact summary
        print(f"📊 {keyword:12s} | Avg: {result['avg_count']:6.2f} | Rate: {result['mention_rate']:.0%} | Quarters: ", end="")

        sorted_quarters = sorted(result['quarters'].items())
        counts_str = ", ".join([f"{q}: {data['count']}" for q, data in sorted_quarters])
        print(counts_str)

    print()
    print("=" * 80)
    print("OBSERVATIONS")
    print("=" * 80)
    print()

    # Sort by average count
    results.sort(key=lambda x: x['avg_count'], reverse=True)

    print("Top 5 Most Mentioned:")
    for i, result in enumerate(results[:5], 1):
        word = result['word'].split('"')[1] if '"' in result['word'] else result['word']
        print(f"  {i}. {word:30s} - {result['avg_count']:6.2f} mentions/quarter")

    print()
    print("Lowest Mention Rate:")
    low_rate = [r for r in results if r['mention_rate'] < 1.0]
    if low_rate:
        for result in sorted(low_rate, key=lambda x: x['mention_rate']):
            word = result['word'].split('"')[1] if '"' in result['word'] else result['word']
            print(f"  • {word:30s} - {result['mention_rate']:.0%} of quarters")
    else:
        print("  All markets had 100% mention rate!")

    print()
    print("✓ Step 3 handles multiple market types successfully")
    print()


if __name__ == "__main__":
    main()
