#!/usr/bin/env python3
"""
Transcript Analysis CLI Script
Analyzes historical transcripts against Polymarket criteria

Usage:
    python scripts/analyze_transcripts.py \
        --transcripts "transcripts/microsoft/*.md" \
        --words data/test_microsoft/markets.json \
        --output data/microsoft_analysis/historical.json
"""

import argparse
import json
import sys
import os
from pathlib import Path
from typing import Dict, List, Any

# Add lib directory to path to import our library functions
sys.path.insert(0, str(Path(__file__).parent / 'lib'))

from transcript_analyzer import analyze_market_historical, load_transcripts


def load_markets_data(markets_path: str) -> List[Dict[str, Any]]:
    """
    Load markets.json from Phase 1 output.

    Args:
        markets_path: Path to markets.json file

    Returns:
        List of market dictionaries with market_question/threshold/words info

    Raises:
        FileNotFoundError: If markets file doesn't exist
        ValueError: If markets file has invalid format
    """
    if not os.path.exists(markets_path):
        raise FileNotFoundError(f"Markets file not found: {markets_path}")

    with open(markets_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Validate format
    if 'markets' not in data:
        raise ValueError(f"Invalid markets.json format: missing 'markets' key")

    markets = data['markets']
    if not isinstance(markets, list):
        raise ValueError(f"Invalid markets.json format: 'markets' must be a list")

    # Validate each market has required fields
    for idx, market in enumerate(markets):
        if not isinstance(market, dict):
            raise ValueError(f"Invalid market at index {idx}: must be a dictionary")

        required_fields = ['market_question', 'threshold']
        missing_fields = [f for f in required_fields if f not in market]
        if missing_fields:
            raise ValueError(
                f"Market at index {idx} missing required fields: {missing_fields}"
            )

        # Validate threshold is a valid positive integer
        threshold = market['threshold']
        if not isinstance(threshold, int):
            raise ValueError(
                f"Market at index {idx}: threshold must be an integer, got {type(threshold).__name__}"
            )
        if threshold < 1:
            raise ValueError(
                f"Market at index {idx}: threshold must be >= 1, got {threshold}"
            )

    return markets


def ensure_output_directory(output_path: str) -> None:
    """
    Ensure the output directory exists, create if it doesn't.

    Args:
        output_path: Path to output file
    """
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        print(f"✓ Created output directory: {output_dir}\n")


def main():
    """Main CLI entry point."""

    # 1. ARGUMENT PARSING
    parser = argparse.ArgumentParser(
        description='Analyze historical transcripts against Polymarket criteria',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
    python scripts/analyze_transcripts.py \\
        --transcripts "transcripts/microsoft/*.md" \\
        --words data/test_microsoft/markets.json \\
        --output data/microsoft_analysis/historical.json
        """
    )

    parser.add_argument(
        '--transcripts',
        required=True,
        help='Glob pattern for transcript files (e.g., "transcripts/microsoft/*.md")'
    )

    parser.add_argument(
        '--words',
        required=True,
        help='Path to markets.json from Phase 1'
    )

    parser.add_argument(
        '--output',
        required=True,
        help='Path for output JSON file'
    )

    args = parser.parse_args()

    try:
        # 2. LOAD MARKETS DATA
        print(f"Loading markets from: {args.words}")
        markets = load_markets_data(args.words)
        print(f"✓ Loaded {len(markets)} markets\n")

        # 3. LOAD TRANSCRIPTS
        print(f"Loading transcripts from pattern: {args.transcripts}")
        transcripts = load_transcripts(args.transcripts)

        if not transcripts:
            print(f"❌ ERROR: No transcripts found matching pattern: {args.transcripts}")
            sys.exit(1)

        quarters = sorted(transcripts.keys())
        print(f"✓ Loaded {len(transcripts)} quarters: {', '.join(quarters)}\n")

        # 4. RUN ANALYSIS
        print(f"Analyzing {len(markets)} markets across {len(transcripts)} quarters...")
        print("=" * 60)

        analysis_results = []

        for idx, market in enumerate(markets, 1):
            market_question = market['market_question']

            # Progress indicator
            print(f"[{idx}/{len(markets)}] Analyzing: {market_question[:50]}{'...' if len(market_question) > 50 else ''}")

            # Run historical analysis
            # analyze_market_historical expects market dict and transcripts
            result = analyze_market_historical(market, transcripts)

            analysis_results.append(result)

        print("=" * 60)
        print(f"✓ Analyzed {len(markets)} markets across {len(transcripts)} quarters\n")

        # 5. GENERATE OUTPUT
        output_data = {
            "analysis": analysis_results,
            "quarters_analyzed": quarters,
            "total_quarters": len(transcripts)
        }

        # Ensure output directory exists
        ensure_output_directory(args.output)

        # Write output JSON
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2)

        print(f"✓ Saved analysis to: {args.output}\n")

        # 6. PRINT SUMMARY STATISTICS
        print("Summary Statistics:")
        print("-" * 60)

        # Count markets by mention rate
        always_mentioned = sum(1 for r in analysis_results if r['mention_rate'] == 1.0)
        never_mentioned = sum(1 for r in analysis_results if r['mention_rate'] == 0.0)
        sometimes_mentioned = len(analysis_results) - always_mentioned - never_mentioned

        print(f"Markets always meeting threshold: {always_mentioned}")
        print(f"Markets sometimes meeting threshold: {sometimes_mentioned}")
        print(f"Markets never meeting threshold: {never_mentioned}")
        print()

        # Show top 5 by average count
        sorted_by_avg = sorted(analysis_results, key=lambda x: x['avg_count'], reverse=True)
        print("Top 5 markets by average count:")
        for result in sorted_by_avg[:5]:
            question = result['market_question']
            print(f"  • {question[:50]}{'...' if len(question) > 50 else ''}")
            print(f"    Avg: {result['avg_count']:.2f}, Rate: {result['mention_rate']:.0%}")

        print("\n✓ Analysis complete!")

    except FileNotFoundError as e:
        print(f"❌ ERROR: {e}")
        sys.exit(1)

    except ValueError as e:
        print(f"❌ ERROR: {e}")
        sys.exit(1)

    except Exception as e:
        print(f"❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
