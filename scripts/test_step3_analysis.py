#!/usr/bin/env python3
"""
Test Script for Step 3: Historical Analysis Function

This script validates the analyze_market_historical() function by:
1. Loading real Microsoft transcripts (Q1-Q4 2025)
2. Loading market definitions from markets.json
3. Running analysis on the "Copilot" market
4. Validating results against expected values
5. Displaying formatted output

Expected Results for "Copilot" market:
- Q1_2025: 65 mentions (>= 1) ✓
- Q2_2025: 48 mentions (>= 1) ✓
- Q3_2025: 25 mentions (>= 1) ✓
- Q4_2025: 41 mentions (>= 1) ✓
- mention_rate: 1.0 (100%)
- avg_count: 44.75
"""

import sys
import json
from pathlib import Path

# Add lib directory to path so we can import transcript_analyzer
sys.path.insert(0, str(Path(__file__).parent / 'lib'))

from transcript_analyzer import (
    load_transcripts,
    analyze_market_historical
)


def main():
    print("=" * 80)
    print("STEP 3 TEST: Historical Analysis Function")
    print("=" * 80)
    print()

    # Define paths
    project_root = Path(__file__).parent.parent
    data_dir = project_root / "data" / "test_microsoft"
    markets_file = data_dir / "markets.json"
    transcripts_dir = project_root / "transcripts" / "microsoft"
    transcripts_pattern = str(transcripts_dir / "*.md")

    print("📂 Loading test data...")
    print(f"   Markets: {markets_file}")
    print(f"   Transcripts: {transcripts_pattern}")
    print()

    # Step 1: Load markets.json
    try:
        with open(markets_file, 'r') as f:
            data = json.load(f)
            markets = data.get("markets", [])
        print(f"✓ Loaded {len(markets)} markets from markets.json")
    except Exception as e:
        print(f"✗ Error loading markets.json: {e}")
        sys.exit(1)

    # Step 2: Load transcripts using Step 2's function
    try:
        transcripts = load_transcripts(transcripts_pattern)
        print(f"✓ Loaded {len(transcripts)} transcripts")
    except Exception as e:
        print(f"✗ Error loading transcripts: {e}")
        sys.exit(1)

    print()

    # Step 3: Find the "Copilot" market
    copilot_market = None
    for market in markets:
        if "copilot" in market.get("word", "").lower():
            copilot_market = market
            break

    if not copilot_market:
        print("✗ Could not find Copilot market in markets.json")
        sys.exit(1)

    print("🎯 Testing Market:")
    print(f"   Question: {copilot_market['word']}")
    print(f"   Words: {copilot_market['words']}")
    print(f"   Threshold: {copilot_market['threshold']}")
    print(f"   Market ID: {copilot_market['market_id']}")
    print()

    # Step 4: Run historical analysis
    print("🔬 Running Historical Analysis...")
    print()
    result = analyze_market_historical(copilot_market, transcripts)

    # Step 5: Display results
    print("=" * 80)
    print("ANALYSIS RESULTS")
    print("=" * 80)
    print()
    print(f"Market: {result['word']}")
    print(f"Threshold: {result['threshold']} mention(s)")
    print()

    print("QUARTER-BY-QUARTER RESULTS:")
    print("-" * 80)

    # Sort quarters chronologically
    sorted_quarters = sorted(result['quarters'].items())

    for quarter, data in sorted_quarters:
        met_symbol = "✓" if data['met_threshold'] else "✗"
        status = "MET" if data['met_threshold'] else "NOT MET"
        print(f"  {quarter}: {data['count']:3d} mentions  {met_symbol} {status}")

    print()
    print("STATISTICS:")
    print("-" * 80)
    print(f"  Mention Rate:           {result['mention_rate']:.2%} ({result['mention_rate']:.2f})")
    print(f"  Average Count:          {result['avg_count']:.2f} mentions/quarter")
    print(f"  Historical Probability: {result['historical_probability']:.2%}")
    print()

    # Step 6: Validate against expected values
    print("=" * 80)
    print("VALIDATION")
    print("=" * 80)
    print()

    expected_counts = {
        "Q1_2025": 65,
        "Q2_2025": 48,
        "Q3_2025": 25,
        "Q4_2025": 41
    }
    expected_mention_rate = 1.0
    expected_avg_count = 44.75

    all_passed = True

    # Validate counts
    print("Validating quarter counts:")
    for quarter, expected_count in expected_counts.items():
        actual_count = result['quarters'][quarter]['count']
        passed = actual_count == expected_count
        symbol = "✓" if passed else "✗"

        if passed:
            print(f"  {symbol} {quarter}: {actual_count} == {expected_count}")
        else:
            print(f"  {symbol} {quarter}: {actual_count} != {expected_count} (MISMATCH)")
            all_passed = False

    print()

    # Validate mention rate
    mention_rate_passed = abs(result['mention_rate'] - expected_mention_rate) < 0.001
    symbol = "✓" if mention_rate_passed else "✗"
    print(f"  {symbol} Mention Rate: {result['mention_rate']:.2f} == {expected_mention_rate:.2f}")
    if not mention_rate_passed:
        all_passed = False

    # Validate average count
    avg_count_passed = abs(result['avg_count'] - expected_avg_count) < 0.01
    symbol = "✓" if avg_count_passed else "✗"
    print(f"  {symbol} Average Count: {result['avg_count']:.2f} == {expected_avg_count:.2f}")
    if not avg_count_passed:
        all_passed = False

    print()

    # Final result
    if all_passed:
        print("=" * 80)
        print("✓ ALL VALIDATIONS PASSED")
        print("=" * 80)
        print()
        print("Step 3 implementation is working correctly!")
        print("Ready to proceed to Step 4: Result Display")
        return 0
    else:
        print("=" * 80)
        print("✗ SOME VALIDATIONS FAILED")
        print("=" * 80)
        print()
        print("Please review the implementation.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
