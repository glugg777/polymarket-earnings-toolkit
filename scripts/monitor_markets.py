#!/usr/bin/env python3
"""
Phase 4.5: Market Monitor with Dynamic Repricing

Monitors order books and dynamically adjusts BOTH limit prices AND conviction tiers/position
sizes based on current market conditions and time until earnings.

Problem Solved:
- Markets analyzed 3-5 days before earnings have low liquidity (70-90% spreads)
- Static limit orders get skipped 40% of the time when market makers arrive 1-2 days later
- Spreads tighten to 10-30% but our old limit prices are too conservative

Solution:
- Monitor current market state vs baseline analysis
- Recalculate edges and conviction tiers based on NEW spreads
- Apply time-based repricing formula (more aggressive closer to earnings)
- Rescale portfolio if conviction tiers change
- Generate change log for human review

Usage:
    python scripts/monitor_markets.py \
        --baseline data/test_microsoft/edges.json \
        --event-url "https://polymarket.com/event/microsoft-q3-earnings" \
        --days-until-earnings 2 \
        --output data/test_microsoft/edges_updated.json \
        --changes data/test_microsoft/changes.md

Safety Mechanisms:
- Dynamic conviction recalculation (STRONG→MODERATE→PASS as edges shrink)
- Portfolio rescaling (maintains 100% max allocation)
- Time-based repricing (balances profit margin vs execution probability)
- Safety rails (never exceed fair_value - 5¢, never bid below best_bid)
- No auto-execution (requires human review of change log)
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent))

import requests
from lib.url_parser import extract_slug

# API Base URLs
GAMMA_API_BASE = "https://gamma-api.polymarket.com"
CLOB_API_BASE = "https://clob.polymarket.com"


def parse_arguments() -> argparse.Namespace:
    """
    Parse command line arguments.

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description='Monitor markets and dynamically adjust limit prices and conviction tiers',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Monitor markets 2 days before earnings
    python scripts/monitor_markets.py \\
        --baseline data/test_microsoft/edges.json \\
        --event-url "https://polymarket.com/event/microsoft-q3-earnings" \\
        --days-until-earnings 2 \\
        --output data/test_microsoft/edges_updated.json \\
        --changes data/test_microsoft/changes.md

    # Monitor on earnings day (very aggressive pricing)
    python scripts/monitor_markets.py \\
        --baseline data/test_microsoft/edges.json \\
        --event-url "https://polymarket.com/event/microsoft-q3-earnings" \\
        --days-until-earnings 0 \\
        --output data/test_microsoft/edges_updated.json \\
        --changes data/test_microsoft/changes.md
        """
    )

    parser.add_argument(
        '--baseline',
        required=True,
        help='Path to baseline edges.json from Phase 4 (initial analysis)'
    )

    parser.add_argument(
        '--event-url',
        required=True,
        help='Polymarket event URL (e.g., https://polymarket.com/event/microsoft-q3-earnings)'
    )

    parser.add_argument(
        '--days-until-earnings',
        type=float,
        required=True,
        help='Days until earnings call (can be fractional, e.g., 1.5 for 36 hours)'
    )

    parser.add_argument(
        '--output',
        required=True,
        help='Output path for updated edges.json file'
    )

    parser.add_argument(
        '--changes',
        required=True,
        help='Output path for changes markdown report'
    )

    parser.add_argument(
        '--max-allocation',
        type=float,
        default=1.0,
        help='Maximum total portfolio allocation (default: 1.0 = 100%%)'
    )

    return parser.parse_args()


def validate_arguments(args: argparse.Namespace) -> None:
    """
    Validate parsed arguments.

    Args:
        args: Parsed arguments namespace

    Raises:
        ValueError: If arguments are invalid
        FileNotFoundError: If baseline file doesn't exist
    """
    # Validate baseline file exists
    baseline_path = Path(args.baseline)
    if not baseline_path.exists():
        raise FileNotFoundError(f"Baseline file not found: {args.baseline}")

    # Validate days_until_earnings
    if args.days_until_earnings < 0:
        raise ValueError(
            f"--days-until-earnings must be >= 0, got: {args.days_until_earnings}"
        )

    # Validate max_allocation
    if not 0.0 < args.max_allocation <= 1.0:
        raise ValueError(
            f"--max-allocation must be between 0.0 and 1.0, got: {args.max_allocation}"
        )


def load_baseline(file_path: str) -> Dict[str, Any]:
    """
    Load baseline edges.json from Phase 4.

    Args:
        file_path: Path to baseline edges.json

    Returns:
        Baseline analysis data with recommendations and fair values

    Raises:
        ValueError: If JSON is invalid or missing required fields
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in baseline file: {e}")

    # Validate structure
    if 'recommendations' not in data:
        raise ValueError("Baseline file missing 'recommendations' field")

    if 'all' not in data['recommendations']:
        raise ValueError("Baseline file missing 'recommendations.all' field")

    return data


def fetch_current_markets(event_url: str) -> Dict[str, Dict[str, Any]]:
    """
    Fetch current market data from Polymarket APIs for BOTH YES and NO sides.

    Enhancement for NO-side betting: Fetches order books for both YES and NO tokens,
    enabling proper limit order calculation for both sides.

    Reuses logic from fetch_market.py to get:
    - Current YES/NO prices
    - Best bid/ask from BOTH YES and NO order books
    - Spreads for both sides

    Args:
        event_url: Polymarket event URL

    Returns:
        Dictionary mapping market_question → {
            yes_price, no_price,
            yes_book: {best_bid, best_ask, spread},
            no_book: {best_bid, best_ask, spread}
        }

    Raises:
        requests.HTTPError: If API calls fail
        ValueError: If no event found or invalid data
    """
    print(f"\nFetching current market data...")

    # Step 1: Extract slug from URL
    slug = extract_slug(event_url)
    print(f"  Slug: {slug}")

    # Step 2: Get event data from Gamma API
    events_url = f"{GAMMA_API_BASE}/events?slug={slug}"
    response = requests.get(events_url)
    response.raise_for_status()
    events = response.json()

    if not events or len(events) == 0:
        raise ValueError(f"No event found for slug: {slug}")

    event = events[0]
    event_id = event['id']
    print(f"  Event: {event.get('title', 'Unknown')}")

    # Step 3: Get full event with all markets
    full_url = f"{GAMMA_API_BASE}/events/{event_id}"
    full_response = requests.get(full_url)
    full_response.raise_for_status()
    full_event = full_response.json()

    markets = full_event.get('markets', [])
    print(f"  Found {len(markets)} markets")

    # Step 4: Collect BOTH YES and NO token IDs for batch order book fetch
    token_ids = []
    market_token_map = {}  # Maps market_id → {'yes': token_id, 'no': token_id}

    for market in markets:
        clob_token_ids_str = market.get('clobTokenIds', '[]')
        try:
            clob_token_ids = json.loads(clob_token_ids_str)
            if clob_token_ids and len(clob_token_ids) >= 2:
                # YES token is always first, NO token is second
                yes_token_id = clob_token_ids[0]
                no_token_id = clob_token_ids[1]

                token_ids.append(yes_token_id)
                token_ids.append(no_token_id)

                market_token_map[market['id']] = {
                    'yes': yes_token_id,
                    'no': no_token_id
                }
            elif clob_token_ids and len(clob_token_ids) == 1:
                # Fallback: only YES token (defensive)
                yes_token_id = clob_token_ids[0]
                token_ids.append(yes_token_id)
                market_token_map[market['id']] = {
                    'yes': yes_token_id,
                    'no': None
                }
        except (json.JSONDecodeError, IndexError):
            pass

    # Step 5: Batch fetch order books for ALL tokens (YES and NO)
    print(f"  Fetching order books for {len(token_ids)} tokens ({len(markets)} × 2)...")
    payload = [{"token_id": token_id} for token_id in token_ids]
    url = f"{CLOB_API_BASE}/books"
    response = requests.post(url, json=payload)
    response.raise_for_status()
    order_books = response.json()

    # Convert to dictionary keyed by asset_id
    order_book_map = {}
    for book in order_books:
        asset_id = book.get('asset_id')
        if asset_id:
            order_book_map[asset_id] = book

    # Step 6: Build market data dictionary with BOTH YES and NO books
    current_markets = {}

    for market in markets:
        question = market.get('question', '')

        # Get pricing
        outcome_prices_str = market.get('outcomePrices')
        if not outcome_prices_str:
            continue

        try:
            outcome_prices = json.loads(outcome_prices_str)
            if len(outcome_prices) < 2:
                continue
            yes_price = float(outcome_prices[0])
            no_price = float(outcome_prices[1])
        except (json.JSONDecodeError, ValueError, IndexError):
            continue

        # Get token IDs for this market
        market_id = market.get('id')
        token_map = market_token_map.get(market_id)
        if not token_map:
            continue

        # Extract YES order book
        yes_token_id = token_map.get('yes')
        yes_book = {'best_bid': 0.0, 'best_ask': 0.0, 'spread': 0.0}

        if yes_token_id and yes_token_id in order_book_map:
            book = order_book_map[yes_token_id]
            bids = book.get('bids', [])
            asks = book.get('asks', [])

            yes_book['best_bid'] = float(bids[0]['price']) if bids else 0.0
            yes_book['best_ask'] = float(asks[0]['price']) if asks else 0.0
            yes_book['spread'] = yes_book['best_ask'] - yes_book['best_bid'] if (yes_book['best_bid'] and yes_book['best_ask']) else 0.0

        # Extract NO order book
        no_token_id = token_map.get('no')
        no_book = {'best_bid': 0.0, 'best_ask': 0.0, 'spread': 0.0}

        if no_token_id and no_token_id in order_book_map:
            book = order_book_map[no_token_id]
            bids = book.get('bids', [])
            asks = book.get('asks', [])

            no_book['best_bid'] = float(bids[0]['price']) if bids else 0.0
            no_book['best_ask'] = float(asks[0]['price']) if asks else 0.0
            no_book['spread'] = no_book['best_ask'] - no_book['best_bid'] if (no_book['best_bid'] and no_book['best_ask']) else 0.0

        current_markets[question] = {
            'yes_price': yes_price,
            'no_price': no_price,
            'yes_book': yes_book,
            'no_book': no_book
        }

    print(f"✓ Fetched current data for {len(current_markets)} markets (both YES and NO books)\n")
    return current_markets


def determine_conviction(abs_edge: float) -> Tuple[str, float]:
    """
    Determine conviction tier and position size based on absolute edge magnitude.

    REUSED FROM calculate_edges.py (lines 623-648)

    Conviction Tiers:
    - STRONG: >20% absolute edge → 25% position size
    - MODERATE: >10% absolute edge → 15% position size
    - PASS: <10% absolute edge → 0% position size (no bet)

    Args:
        abs_edge: Absolute edge magnitude (0.0-1.0)

    Returns:
        Tuple of (conviction_tier, position_size)
    """
    if abs_edge > 0.20:
        return ('STRONG', 0.25)
    elif abs_edge > 0.10:
        return ('MODERATE', 0.15)
    else:
        return ('PASS', 0.0)


def apply_portfolio_scaling(
    recommendations: List[Dict[str, Any]],
    max_allocation: float
) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
    """
    Scale portfolio positions to fit within maximum allocation constraint.

    REUSED FROM calculate_edges.py (lines 930-960)

    This is a CRITICAL safety mechanism in Phase 4.5. When conviction tiers change
    (e.g., STRONG → MODERATE → PASS), the total raw allocation changes. We must
    recalculate the scale factor to maintain risk discipline.

    Example:
        Baseline: 3 STRONG (75%) + 6 MODERATE (90%) = 165% raw
                  Scale factor: 100% / 165% = 0.606
                  Scaled allocation: 100%

        After monitoring: 2 STRONG (50%) + 7 MODERATE (105%) = 155% raw (1 downgrade)
                         Scale factor: 100% / 155% = 0.645
                         Scaled allocation: 100%

    Args:
        recommendations: List of recommendation dictionaries with 'conviction' and 'position_size'
        max_allocation: Maximum total portfolio allocation (typically 1.0 = 100%)

    Returns:
        Tuple of (scaled_recommendations, scaling_metadata)
        - scaled_recommendations: Updated list with scaled position_size
        - scaling_metadata: Dict with total_raw, total_scaled, scale_factor, was_scaled
    """
    # Calculate total raw allocation (before scaling)
    total_raw_allocation = sum(
        r['position_size'] for r in recommendations
        if r['conviction'] != 'PASS'
    )

    # Determine scale factor
    if total_raw_allocation > max_allocation:
        scale_factor = max_allocation / total_raw_allocation
    elif total_raw_allocation > 0:
        scale_factor = 1.0
    else:
        # Edge case: all markets are PASS
        scale_factor = 1.0

    # Apply scaling to all non-PASS recommendations
    for rec in recommendations:
        if rec['conviction'] != 'PASS':
            # Store original position size before scaling
            if 'raw_position_size' not in rec:
                rec['raw_position_size'] = rec['position_size']
            # Apply scale factor
            rec['position_size'] = rec['raw_position_size'] * scale_factor

    # Calculate total scaled allocation
    total_scaled_allocation = sum(
        r['position_size'] for r in recommendations
        if r['conviction'] != 'PASS'
    )

    # Build metadata
    scaling_metadata = {
        'total_raw': total_raw_allocation,
        'total_scaled': total_scaled_allocation,
        'scale_factor': scale_factor,
        'was_scaled': scale_factor < 1.0
    }

    return recommendations, scaling_metadata


def calculate_time_adjusted_limit(
    fair_value: float,
    best_bid: float,
    best_ask: float,
    days_until: float
) -> float:
    """
    Calculate time-adjusted limit price with progressive aggressiveness.

    IMPLEMENTS Phase 4.5, Step 3 (lines 2107-2119 in implementation plan)

    Problem: Static limit orders placed 5 days before earnings get skipped when
             market makers arrive 1-2 days before and spreads tighten.

    Solution: Step function that increases aggressiveness as earnings approaches,
              balancing profit margin vs execution probability.

    Time-Based Aggressiveness:
        5+ days:  bid + 2¢          (Conservative: 60% fill rate, maximize profit)
        3 days:   bid + 20% spread  (Slightly aggressive: 70% fill rate)
        1 day:    bid + 40% spread  (Competitive: 85% fill rate)
        0 days:   bid + 80% spread  (Very aggressive: 95% fill rate, prioritize execution)

    Safety Rails:
        1. Never exceed (fair_value - 5¢) → Maintain minimum profit margin
        2. Never bid below (best_bid + 1¢) → Must be better than current best bid

    Example:
        fair_value = $1.00, best_bid = $0.60, best_ask = $0.80

        Day 5: limit = $0.60 + $0.02 = $0.62 (below safety max of $0.95) ✓
        Day 3: limit = $0.60 + 20% × $0.20 = $0.64 ✓
        Day 1: limit = $0.60 + 40% × $0.20 = $0.68 ✓
        Day 0: limit = $0.60 + 80% × $0.20 = $0.76 ✓

    Args:
        fair_value: Our calculated fair value (doesn't change, based on historical + news)
        best_bid: Current best bid on order book
        best_ask: Current best ask on order book
        days_until: Days until earnings (can be fractional, e.g., 1.5)

    Returns:
        Recommended limit price (constrained by safety rails)
    """
    spread = best_ask - best_bid

    # Step function: Determine add amount based on time until earnings
    if days_until >= 5:
        # Very conservative: maximize profit, accept lower fill rate
        add_amount = 0.02
    elif days_until >= 3:
        # Slightly aggressive: early liquidity may be arriving
        add_amount = spread * 0.20
    elif days_until >= 1:
        # Competitive: market makers likely arriving, move toward midpoint
        add_amount = spread * 0.40
    else:
        # Very aggressive: last chance before earnings, prioritize execution
        add_amount = spread * 0.80

    # Calculate target limit price
    target = best_bid + add_amount

    # Safety rail #1: Never exceed fair value minus 5¢ buffer
    # This maintains a minimum profit margin even in aggressive scenarios
    safety_max = fair_value - 0.05
    target = min(target, safety_max)

    # Safety rail #2: Never bid below best_bid (must improve the market)
    # Add 1¢ to ensure we're actually better than current best bid
    safety_min = best_bid + 0.01
    target = max(target, safety_min)

    return target


def generate_change_log(
    baseline_recs: List[Dict[str, Any]],
    updated_recs: List[Dict[str, Any]],
    days_until: float,
    baseline_metadata: Dict[str, Any],
    updated_metadata: Dict[str, Any]
) -> str:
    """
    Generate markdown change log comparing baseline vs updated recommendations.

    IMPLEMENTS Phase 4.5, Step 4 (lines 2121-2134 in implementation plan)

    This is a FOCUSED report showing only what changed, NOT a comprehensive report.
    Different from Phase 5's full report - this is for monitoring checkpoints.

    Reports:
    - Conviction tier changes (STRONG → MODERATE → PASS)
    - Significant repricing (spread tightened >30%, limit changed >10¢)
    - Edge deterioration (>5pp decrease)
    - High-priority actions ranked by urgency
    - Summary statistics

    Args:
        baseline_recs: Original recommendations from edges_initial.json
        updated_recs: Updated recommendations after monitoring
        days_until: Days until earnings (for context)
        baseline_metadata: Baseline metadata (timestamps, allocation)
        updated_metadata: Updated metadata

    Returns:
        Markdown-formatted change log string
    """
    lines = []

    # Header
    lines.append("# Market Monitor Change Log")
    lines.append("")
    lines.append(f"**Monitoring Run:** {updated_metadata['monitoring_timestamp']}")
    lines.append(f"**Baseline Analysis:** {baseline_metadata.get('generated_at', 'Unknown')}")
    lines.append(f"**Days Until Earnings:** {days_until:.1f}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Executive Summary
    lines.append("## Executive Summary")
    lines.append("")

    # Count changes
    conviction_changes = [r for r in updated_recs if r.get('changes', {}).get('conviction', {}).get('changed', False)]

    repricing_needed = []
    for rec in updated_recs:
        if rec['conviction'] == 'PASS':
            continue
        limit_repricing = rec.get('limit_repricing', {})
        old_limit = limit_repricing.get('old_limit', 0)
        new_limit = limit_repricing.get('new_limit', 0)
        if old_limit and new_limit:
            delta = new_limit - old_limit
            if abs(delta) > 0.10:  # >10¢ change
                repricing_needed.append(rec)

    spread_tightened = [
        r for r in updated_recs
        if r.get('changes', {}).get('spread', {}).get('pct_change', 0) < -30  # >30% tightening
    ]

    edge_deteriorated = [
        r for r in updated_recs
        if r.get('changes', {}).get('edge_pct', {}).get('delta', 0) < -5  # >5pp drop
    ]

    lines.append(f"- **Conviction changes:** {len(conviction_changes)} markets")
    lines.append(f"- **Repricing needed:** {len(repricing_needed)} markets (limit changed >10¢)")
    lines.append(f"- **Spread tightened:** {len(spread_tightened)} markets (>30% tighter)")
    lines.append(f"- **Edge deteriorated:** {len(edge_deteriorated)} markets (>5pp drop)")
    lines.append("")

    # Portfolio allocation changes
    baseline_alloc = baseline_metadata.get('allocation', {})
    updated_alloc = updated_metadata.get('allocation', {})
    scale_change = updated_alloc.get('scale_factor', 1.0) - baseline_alloc.get('scale_factor', 1.0)

    lines.append(f"**Portfolio Allocation:**")
    lines.append(f"- Baseline: {baseline_alloc.get('total_scaled', 0):.1%} ({baseline_alloc.get('scale_factor', 1.0):.3f} scale factor)")
    lines.append(f"- Updated: {updated_alloc.get('total_scaled', 0):.1%} ({updated_alloc.get('scale_factor', 1.0):.3f} scale factor)")
    if abs(scale_change) > 0.01:
        lines.append(f"- **⚠️ Scale factor changed by {scale_change:+.3f}** - affects ALL position sizes")
    lines.append("")
    lines.append("---")
    lines.append("")

    # High-Priority Changes
    if conviction_changes or repricing_needed:
        lines.append("## High-Priority Changes")
        lines.append("")

        # Conviction changes
        if conviction_changes:
            lines.append("### Conviction Tier Changes")
            lines.append("")
            lines.append("| Market | Old → New | Edge Change | Action Required |")
            lines.append("|--------|-----------|-------------|-----------------|")

            for rec in conviction_changes:
                market = rec['market_question'][:50]
                old_conv = rec['changes']['conviction']['old']
                new_conv = rec['changes']['conviction']['new']
                edge_delta = rec['changes']['edge_pct']['delta']

                # Determine action
                if new_conv == 'PASS':
                    action = "❌ Close position"
                elif old_conv == 'PASS':
                    action = "✅ Open position"
                elif old_conv == 'STRONG' and new_conv == 'MODERATE':
                    action = "⬇️ Reduce size"
                elif old_conv == 'MODERATE' and new_conv == 'STRONG':
                    action = "⬆️ Increase size"
                else:
                    action = "Review"

                lines.append(f"| {market}... | {old_conv} → {new_conv} | {edge_delta:+.1f}pp | {action} |")

            lines.append("")

        # Repricing needed
        if repricing_needed:
            lines.append("### Markets Requiring Repricing")
            lines.append("")
            lines.append("| Market | Side | Old Limit | New Limit | Change | Skip Risk |")
            lines.append("|--------|------|-----------|-----------|--------|-----------|")

            for rec in sorted(repricing_needed, key=lambda r: abs(r['limit_repricing']['delta']), reverse=True)[:10]:
                market = rec['market_question'][:50]
                side = rec.get('side', 'YES')
                old_limit = rec['limit_repricing']['old_limit']
                new_limit = rec['limit_repricing']['new_limit']
                delta = rec['limit_repricing']['delta']

                # Assess skip risk
                best_bid = rec['best_bid']
                if best_bid > new_limit:
                    skip_risk = "🔴 HIGH"
                elif best_bid > old_limit:
                    skip_risk = "🟡 MEDIUM"
                else:
                    skip_risk = "🟢 LOW"

                lines.append(f"| {market}... | {side} | ${old_limit:.2f} | ${new_limit:.2f} | {delta:+.2f} | {skip_risk} |")

            lines.append("")

        lines.append("---")
        lines.append("")

    # Detailed Changes by Market
    if spread_tightened or edge_deteriorated:
        lines.append("## Market Condition Changes")
        lines.append("")

        if spread_tightened:
            lines.append("### Spreads Tightened (>30%)")
            lines.append("")
            lines.append("*Market makers may be arriving - consider repricing*")
            lines.append("")
            for rec in spread_tightened[:5]:
                market = rec['market_question']
                old_spread = rec['changes']['spread']['old']
                new_spread = rec['changes']['spread']['new']
                pct_change = rec['changes']['spread']['pct_change']
                lines.append(f"- **{market}**")
                lines.append(f"  - Spread: {old_spread*100:.0f}% → {new_spread*100:.0f}% ({pct_change:.0f}% change)")
                lines.append("")

        if edge_deteriorated:
            lines.append("### Edge Deteriorated (>5pp)")
            lines.append("")
            lines.append("*Consider news refresh for these markets*")
            lines.append("")
            for rec in edge_deteriorated[:5]:
                market = rec['market_question']
                old_edge = rec['changes']['edge_pct']['old']
                new_edge = rec['changes']['edge_pct']['new']
                delta = rec['changes']['edge_pct']['delta']
                lines.append(f"- **{market}**")
                lines.append(f"  - Edge: {old_edge:+.1f}% → {new_edge:+.1f}% ({delta:+.1f}pp)")
                lines.append("")

        lines.append("---")
        lines.append("")

    # Next Steps
    lines.append("## Next Steps")
    lines.append("")

    if conviction_changes:
        lines.append(f"1. **Update {len(conviction_changes)} positions** for conviction tier changes")
    if repricing_needed:
        lines.append(f"2. **Reprice {len(repricing_needed)} limit orders** (see table above)")
    if edge_deteriorated:
        lines.append(f"3. **Consider news refresh** for {len(edge_deteriorated)} markets with edge deterioration")

    lines.append(f"4. **Re-run monitor** in {12 if days_until > 1 else 6} hours for next checkpoint")

    if days_until <= 0.5:
        lines.append("5. **⚠️ EARNINGS IMMINENT** - Final review and position adjustments")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"*Generated by monitor_markets.py - Phase 4.5*")

    return "\n".join(lines)


def main():
    """Main execution function."""
    try:
        # Parse and validate arguments
        args = parse_arguments()

        print("=" * 70)
        print("PHASE 4.5: MARKET MONITOR WITH DYNAMIC REPRICING")
        print("=" * 70)
        print(f"Baseline: {args.baseline}")
        print(f"Event URL: {args.event_url}")
        print(f"Days Until Earnings: {args.days_until_earnings}")
        print(f"Output: {args.output}")
        print(f"Changes Report: {args.changes}")
        print(f"Max Allocation: {args.max_allocation:.0%}")
        print()

        # Validate arguments
        validate_arguments(args)
        print("✓ Arguments validated\n")

        # Step 1: Load baseline edges.json
        print("Loading baseline analysis...")
        baseline = load_baseline(args.baseline)
        baseline_recs = baseline['recommendations']['all']
        print(f"✓ Loaded {len(baseline_recs)} baseline recommendations")
        print(f"  Generated: {baseline['metadata'].get('generated_at', 'Unknown')}")
        print(f"  Original allocation: {baseline['metadata']['allocation']['total_scaled']:.1%}")
        print()

        # Step 2: Fetch current market data
        current_markets = fetch_current_markets(args.event_url)

        # Step 3: Process each market - recalculate edges and conviction tiers
        print("Recalculating edges and conviction tiers based on current market state...")
        updated_recommendations = []

        for baseline_rec in baseline_recs:
            question = baseline_rec['market_question']

            # Get current market data
            current_market = current_markets.get(question)
            if not current_market:
                print(f"  ⚠️  Market not found in current data: {question[:60]}...")
                # Keep baseline recommendation as-is
                updated_recommendations.append(baseline_rec.copy())
                continue

            # Determine side from baseline (already calculated in Phase 4)
            baseline_side = baseline_rec.get('side', 'YES')

            # Select correct order book and fair value based on side
            if baseline_side == 'YES':
                # YES-side bet: use YES order book and YES fair value
                order_book = current_market['yes_book']
                fair_value = baseline_rec['fair_value']
                market_price = current_market['yes_price']
            else:
                # NO-side bet: use NO order book and invert fair value
                order_book = current_market['no_book']
                fair_value = 1.0 - baseline_rec['fair_value']  # NO fair value = 1 - YES fair value
                market_price = current_market['no_price']

            # Validation: Check if order book has valid data
            if order_book['best_bid'] == 0 and order_book['best_ask'] == 0:
                print(f"  ⚠️  Empty order book for {baseline_side} side: {question[:60]}...")
                # Keep baseline recommendation as-is
                updated_recommendations.append(baseline_rec.copy())
                continue

            # Validation: Check YES/NO price consistency (should sum to ~$1.00)
            yes_mid = (current_market['yes_book']['best_bid'] + current_market['yes_book']['best_ask']) / 2
            no_mid = (current_market['no_book']['best_bid'] + current_market['no_book']['best_ask']) / 2
            price_sum = yes_mid + no_mid

            if abs(price_sum - 1.0) > 0.20:  # More than 20¢ off (allow for wide spreads)
                print(f"  ⚠️  Pricing anomaly: {question[:60]}...")
                print(f"     YES mid: ${yes_mid:.2f}, NO mid: ${no_mid:.2f}, Sum: ${price_sum:.2f}")

            # Recalculate edge using CURRENT market price
            edge = fair_value - market_price
            edge_pct = edge * 100
            abs_edge = abs(edge)
            abs_edge_pct = abs(edge_pct)

            # Determine side and market type (should match baseline, but recalculate)
            if edge > 0:
                side = baseline_side  # Use baseline side (YES or NO)
                market_type = 'UNDERPRICED' if side == 'YES' else 'OVERPRICED'
            else:
                # Edge flipped - shouldn't happen often, but handle it
                side = 'NO' if baseline_side == 'YES' else 'YES'
                market_type = 'OVERPRICED' if side == 'YES' else 'UNDERPRICED'

            # Recalculate conviction tier based on NEW edge
            new_conviction, new_position_size = determine_conviction(abs_edge)

            # Store old values for comparison (will be used in change log)
            old_conviction = baseline_rec['conviction']
            old_position_size = baseline_rec['position_size']
            old_edge_pct = baseline_rec['edge_pct']
            old_spread = baseline_rec.get('spread', 0)
            old_side = baseline_rec.get('side', 'YES')

            # Build updated recommendation (will add time-adjusted limit prices in Step 3)
            updated_rec = baseline_rec.copy()
            updated_rec.update({
                # Updated market state
                'market_price': market_price,
                'market_yes_price': current_market['yes_price'],
                'market_no_price': current_market['no_price'],
                'best_bid': order_book['best_bid'],
                'best_ask': order_book['best_ask'],
                'spread': order_book['spread'],

                # Store both books for reference
                'yes_book': current_market['yes_book'],
                'no_book': current_market['no_book'],

                # Recalculated edge (from perspective of chosen side)
                'edge': edge,
                'edge_pct': edge_pct,
                'abs_edge': abs_edge,
                'abs_edge_pct': abs_edge_pct,
                'side': side,
                'market_type': market_type,
                'fair_value': fair_value,  # Update fair value for NO-side

                # Recalculated conviction
                'conviction': new_conviction,
                'position_size': new_position_size,
                'raw_position_size': new_position_size,  # Before portfolio scaling

                # Track changes for reporting
                'changes': {
                    'conviction': {
                        'old': old_conviction,
                        'new': new_conviction,
                        'changed': old_conviction != new_conviction
                    },
                    'edge_pct': {
                        'old': old_edge_pct,
                        'new': edge_pct,
                        'delta': edge_pct - old_edge_pct
                    },
                    'spread': {
                        'old': old_spread,
                        'new': order_book['spread'],
                        'delta': order_book['spread'] - old_spread,
                        'pct_change': ((order_book['spread'] - old_spread) / old_spread * 100) if old_spread > 0 else 0
                    },
                    'side': {
                        'old': old_side,
                        'new': side,
                        'changed': old_side != side
                    }
                }
            })

            updated_recommendations.append(updated_rec)

        print(f"✓ Recalculated {len(updated_recommendations)} recommendations\n")

        # Show conviction tier changes
        conviction_changes = [
            rec for rec in updated_recommendations
            if rec.get('changes', {}).get('conviction', {}).get('changed', False)
        ]

        if conviction_changes:
            print(f"⚠️  Conviction tier changes detected: {len(conviction_changes)} markets")
            for rec in conviction_changes[:5]:  # Show top 5
                old = rec['changes']['conviction']['old']
                new = rec['changes']['conviction']['new']
                print(f"  {rec['market_question'][:60]}...")
                print(f"    {old} → {new} (edge: {rec['edge_pct']:+.1f}%)")
        else:
            print("✓ No conviction tier changes")

        print()

        # Step 2: Portfolio Rescaling
        print("=" * 70)
        print("STEP 2: PORTFOLIO RESCALING")
        print("=" * 70)
        print("Recalculating portfolio allocation based on updated conviction tiers...")
        print()

        # Get baseline allocation for comparison
        baseline_allocation = baseline['metadata'].get('allocation', {})
        baseline_total_raw = baseline_allocation.get('total_raw', 0)
        baseline_scale_factor = baseline_allocation.get('scale_factor', 1.0)

        print(f"Baseline allocation:")
        print(f"  Total raw: {baseline_total_raw:.1%}")
        print(f"  Scale factor: {baseline_scale_factor:.3f}")
        print()

        # Apply portfolio scaling to updated recommendations
        scaled_recommendations, scaling_metadata = apply_portfolio_scaling(
            updated_recommendations,
            args.max_allocation
        )

        # Show updated allocation
        print(f"Updated allocation:")
        print(f"  Total raw: {scaling_metadata['total_raw']:.1%}")
        print(f"  Scale factor: {scaling_metadata['scale_factor']:.3f}")
        print(f"  Total scaled: {scaling_metadata['total_scaled']:.1%}")

        if scaling_metadata['was_scaled']:
            print(f"  ⚠️  Scaling applied: positions scaled by {scaling_metadata['scale_factor']:.1%}")
        else:
            print(f"  ✓ No scaling needed: raw allocation within max")
        print()

        # Check if scale factor changed significantly
        scale_factor_change = scaling_metadata['scale_factor'] - baseline_scale_factor
        if abs(scale_factor_change) > 0.01:  # 1% threshold
            print(f"⚠️  Scale factor changed by {scale_factor_change:+.1%}")
            print(f"   This affects ALL position sizes proportionally")
            print()

        # Show conviction tier breakdown
        strong_count = len([r for r in scaled_recommendations if r['conviction'] == 'STRONG'])
        moderate_count = len([r for r in scaled_recommendations if r['conviction'] == 'MODERATE'])
        pass_count = len([r for r in scaled_recommendations if r['conviction'] == 'PASS'])

        strong_allocation = sum(r['position_size'] for r in scaled_recommendations if r['conviction'] == 'STRONG')
        moderate_allocation = sum(r['position_size'] for r in scaled_recommendations if r['conviction'] == 'MODERATE')

        print(f"Conviction tier breakdown:")
        print(f"  STRONG: {strong_count} markets, {strong_allocation:.1%} total allocation")
        print(f"  MODERATE: {moderate_count} markets, {moderate_allocation:.1%} total allocation")
        print(f"  PASS: {pass_count} markets, 0% allocation")
        print()

        print("✓ Step 2 complete! Portfolio rescaling applied")
        print()

        # Step 3: Time-Based Repricing
        print("=" * 70)
        print("STEP 3: TIME-BASED REPRICING")
        print("=" * 70)
        print(f"Calculating limit prices for {args.days_until_earnings:.1f} days until earnings...")
        print()

        # Determine aggressiveness level based on days_until
        if args.days_until_earnings >= 5:
            aggressiveness = "CONSERVATIVE (bid + 2¢)"
        elif args.days_until_earnings >= 3:
            aggressiveness = "SLIGHTLY AGGRESSIVE (bid + 20% spread)"
        elif args.days_until_earnings >= 1:
            aggressiveness = "COMPETITIVE (bid + 40% spread)"
        else:
            aggressiveness = "VERY AGGRESSIVE (bid + 80% spread)"

        print(f"Aggressiveness level: {aggressiveness}")
        print()

        # Calculate time-adjusted limits for each recommendation
        repricing_changes = []
        for rec in scaled_recommendations:
            # Skip PASS markets (no position)
            if rec['conviction'] == 'PASS':
                rec['limit_price_target'] = None
                rec['limit_repricing'] = {
                    'old_limit': rec.get('limit_price_target'),
                    'new_limit': None,
                    'delta': None,
                    'reason': 'PASS conviction - no position'
                }
                continue

            # Get baseline limit price for comparison
            baseline_limit = rec.get('limit_price_target', 0.0)

            # Calculate new time-adjusted limit
            new_limit = calculate_time_adjusted_limit(
                fair_value=rec['fair_value'],
                best_bid=rec['best_bid'],
                best_ask=rec['best_ask'],
                days_until=args.days_until_earnings
            )

            # Store old and new limits
            rec['limit_price_target'] = new_limit
            rec['limit_repricing'] = {
                'old_limit': baseline_limit,
                'new_limit': new_limit,
                'delta': new_limit - baseline_limit if baseline_limit else None,
                'applied_formula': aggressiveness
            }

            # Track significant repricing changes (>10¢ or >50% change)
            if baseline_limit > 0:
                delta = new_limit - baseline_limit
                pct_change = (delta / baseline_limit) * 100
                if abs(delta) > 0.10 or abs(pct_change) > 50:
                    repricing_changes.append({
                        'market': rec['market_question'],
                        'conviction': rec['conviction'],
                        'old_limit': baseline_limit,
                        'new_limit': new_limit,
                        'delta': delta,
                        'pct_change': pct_change
                    })

        print(f"✓ Calculated time-adjusted limits for {len(scaled_recommendations)} markets")
        print()

        # Show significant repricing changes
        if repricing_changes:
            print(f"⚠️  Significant repricing detected: {len(repricing_changes)} markets")
            print(f"   (change >10¢ or >50%)")
            print()
            for change in repricing_changes[:5]:  # Show top 5
                print(f"  {change['market'][:60]}...")
                print(f"    Old limit: ${change['old_limit']:.2f} → New limit: ${change['new_limit']:.2f}")
                print(f"    Change: {change['delta']:+.2f} ({change['pct_change']:+.1f}%)")
            if len(repricing_changes) > 5:
                print(f"  ... and {len(repricing_changes) - 5} more")
        else:
            print("✓ No significant repricing changes needed")

        print()
        print("✓ Step 3 complete! Time-based repricing applied")
        print()

        # Step 4: Change Log Generation
        print("=" * 70)
        print("STEP 4: CHANGE LOG GENERATION")
        print("=" * 70)
        print("Generating markdown change log comparing baseline vs current state...")
        print()

        # Build updated metadata for change log
        updated_metadata = {
            'generated_at': datetime.now().isoformat(),
            'monitoring_timestamp': datetime.now().isoformat(),
            'allocation': scaling_metadata
        }

        # Generate change log
        change_log = generate_change_log(
            baseline_recs=baseline_recs,
            updated_recs=scaled_recommendations,
            days_until=args.days_until_earnings,
            baseline_metadata=baseline['metadata'],
            updated_metadata=updated_metadata
        )

        # Write change log to file
        changes_path = Path(args.changes)
        changes_path.parent.mkdir(parents=True, exist_ok=True)
        with open(changes_path, 'w', encoding='utf-8') as f:
            f.write(change_log)

        print(f"✓ Change log written to {args.changes}")
        print()

        # Show preview of key changes
        if conviction_changes:
            print(f"📊 Key highlights:")
            print(f"   • {len(conviction_changes)} conviction tier changes")
        if repricing_changes:
            print(f"   • {len(repricing_changes)} markets need repricing (>10¢ or >50% change)")
        if not conviction_changes and not repricing_changes:
            print(f"✓ No major changes detected")

        print()
        print("✓ Step 4 complete! Change log generated")
        print()

        # Step 5: Conditional News Refresh
        print("=" * 70)
        print("STEP 5: CONDITIONAL NEWS REFRESH CHECK")
        print("=" * 70)
        print("Checking for markets with significant price moves (>30%)...")
        print()

        # Detect markets with >30% price moves since baseline
        news_refresh_candidates = []
        for rec in scaled_recommendations:
            old_price = None
            new_price = rec.get('market_price', 0)

            # Find old price from baseline
            for baseline_rec in baseline_recs:
                if baseline_rec['market_question'] == rec['market_question']:
                    old_price = baseline_rec.get('market_price', 0)
                    break

            if old_price and new_price:
                price_change = abs(new_price - old_price)
                pct_change = (price_change / old_price) * 100 if old_price > 0 else 0

                if pct_change > 30:
                    news_refresh_candidates.append({
                        'market': rec['market_question'],
                        'old_price': old_price,
                        'new_price': new_price,
                        'change': price_change,
                        'pct_change': pct_change
                    })

        if news_refresh_candidates:
            print(f"⚠️  {len(news_refresh_candidates)} markets moved >30% - consider news refresh")
            print()
            for candidate in news_refresh_candidates[:5]:
                print(f"  • {candidate['market'][:60]}...")
                print(f"    Price: ${candidate['old_price']:.2f} → ${candidate['new_price']:.2f} ({candidate['pct_change']:+.1f}%)")
            if len(news_refresh_candidates) > 5:
                print(f"  ... and {len(news_refresh_candidates) - 5} more")
            print()
            print("💡 Recommended action:")
            print("   Run search_news.py for these markets to refresh sentiment analysis")
            print("   Then re-run calculate_edges.py with updated news data")
        else:
            print("✓ No markets with >30% price moves")

        print()
        print("✓ Step 5 complete! News refresh check done")
        print()

        # Build output structure
        output = {
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'baseline_file': args.baseline,
                'baseline_generated_at': baseline['metadata'].get('generated_at', 'Unknown'),
                'event_url': args.event_url,
                'days_until_earnings': args.days_until_earnings,
                'monitoring_timestamp': datetime.now().isoformat(),
                'configuration': {
                    'max_allocation': args.max_allocation,
                },
                'allocation': scaling_metadata,
                'allocation_comparison': {
                    'baseline_total_raw': baseline_total_raw,
                    'baseline_scale_factor': baseline_scale_factor,
                    'current_total_raw': scaling_metadata['total_raw'],
                    'current_scale_factor': scaling_metadata['scale_factor'],
                    'scale_factor_delta': scale_factor_change
                },
                'summary': {
                    'total_markets': len(scaled_recommendations),
                    'strong_conviction': strong_count,
                    'moderate_conviction': moderate_count,
                    'pass': pass_count,
                    'conviction_changes': len(conviction_changes)
                }
            },
            'recommendations': {
                'all': scaled_recommendations,
                'by_conviction': {
                    'high_conviction': [r for r in scaled_recommendations if r['conviction'] == 'STRONG'],
                    'moderate_conviction': [r for r in scaled_recommendations if r['conviction'] == 'MODERATE'],
                    'pass': [r for r in scaled_recommendations if r['conviction'] == 'PASS']
                }
            }
        }

        # Write output
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        print("=" * 70)
        print("MONITORING COMPLETE")
        print("=" * 70)
        print()
        print(f"✅ Updated edges written to: {args.output}")
        print(f"✅ Change log written to: {args.changes}")
        print()
        print("📊 Summary:")
        print(f"   • Analyzed: {len(scaled_recommendations)} markets")
        print(f"   • Conviction changes: {len(conviction_changes)}")
        print(f"   • Repricing needed: {len(repricing_changes)}")
        if news_refresh_candidates:
            print(f"   • News refresh recommended: {len(news_refresh_candidates)}")
        print()
        print(f"💡 Next steps:")
        print(f"   1. Review change log: {args.changes}")
        print(f"   2. Update limit orders on Polymarket as needed")
        if args.days_until_earnings > 1:
            print(f"   3. Re-run monitor in 12 hours")
        else:
            print(f"   3. Re-run monitor in 6 hours (earnings approaching!)")
        print()
        print("=" * 70)

    except FileNotFoundError as e:
        print(f"❌ ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    except ValueError as e:
        print(f"❌ ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    except Exception as e:
        print(f"❌ UNEXPECTED ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
