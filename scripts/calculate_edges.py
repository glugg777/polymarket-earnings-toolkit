#!/usr/bin/env python3
"""
Phase 4: Edge Calculator
Calculates betting edges by combining historical analysis, current markets, and news research.

This script synthesizes data from Phases 1-3 to produce actionable betting recommendations:
- Historical patterns (Phase 2): Baseline probabilities from transcript analysis
- Current market prices (Phase 1): Live YES/NO pricing and spreads
- News insights (Phase 3): Recent developments that may shift probabilities
- Output: Recommended bet prices and edge calculations for each market

Usage:
    python scripts/calculate_edges.py \
        --historical data/test_microsoft/historical.json \
        --markets data/test_microsoft/markets.json \
        --news data/test_microsoft/news.json \
        --news-weight 0.3 \
        --max-spread-cross 0.03 \
        --output data/test_microsoft/edges.json

Output:
    Creates edges.json with:
    - Edge calculations (difference between fair value and market price)
    - Recommended bet prices (YES/NO)
    - Confidence scores based on historical data quality
    - News-adjusted probabilities with justifications
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple


def parse_arguments() -> argparse.Namespace:
    """
    Parse command line arguments.

    Returns:
        Parsed arguments namespace

    CLI Arguments:
        --historical: Path to historical.json (Phase 2 output)
        --markets: Path to markets.json (Phase 1 output)
        --news: Path to news.json (Phase 3 output)
        --news-weight: Weight for news adjustments (0.0-1.0, default: 0.3)
        --max-spread-cross: Maximum spread to cross for recommendations (default: 0.03)
        --output: Path for output edges.json file
    """
    parser = argparse.ArgumentParser(
        description='Calculate betting edges from historical analysis, markets, and news',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Calculate edges with default news weight (30%)
    python scripts/calculate_edges.py \\
        --historical data/test_microsoft/historical.json \\
        --markets data/test_microsoft/markets.json \\
        --news data/test_microsoft/news.json \\
        --output data/test_microsoft/edges.json

    # Calculate edges with higher news influence (50%)
    python scripts/calculate_edges.py \\
        --historical data/test_microsoft/historical.json \\
        --markets data/test_microsoft/markets.json \\
        --news data/test_microsoft/news.json \\
        --news-weight 0.5 \\
        --output data/test_microsoft/edges.json

    # Calculate edges with no spread crossing allowed (only bet when market is mispriced)
    python scripts/calculate_edges.py \\
        --historical data/test_microsoft/historical.json \\
        --markets data/test_microsoft/markets.json \\
        --news data/test_microsoft/news.json \\
        --max-spread-cross 0.0 \\
        --output data/test_microsoft/edges.json
        """
    )

    parser.add_argument(
        '--historical',
        required=True,
        help='Path to historical.json from Phase 2 (transcript analysis)'
    )

    parser.add_argument(
        '--markets',
        required=True,
        help='Path to markets.json from Phase 1 (current market data)'
    )

    parser.add_argument(
        '--news',
        required=True,
        help='Path to news.json from Phase 3 (news research)'
    )

    parser.add_argument(
        '--news-weight',
        type=float,
        default=0.3,
        help='Weight for news adjustments (0.0-1.0, default: 0.3). Higher values give more influence to recent news vs historical patterns.'
    )

    parser.add_argument(
        '--max-spread-cross',
        type=float,
        default=0.03,
        help='Maximum spread to cross for bet recommendations (default: 0.03 = 3%%). Set to 0.0 to only recommend bets when market is clearly mispriced.'
    )

    parser.add_argument(
        '--max-allocation',
        type=float,
        default=1.0,
        help='Maximum total portfolio allocation as fraction of bankroll (default: 1.0 = 100%%). Positions will be scaled proportionally if total exceeds this limit.'
    )

    parser.add_argument(
        '--output',
        required=True,
        help='Output path for edges.json file'
    )

    return parser.parse_args()


def validate_arguments(args: argparse.Namespace) -> None:
    """
    Validate parsed arguments.

    Args:
        args: Parsed arguments namespace

    Raises:
        ValueError: If arguments are invalid

    Validations:
        - news_weight must be between 0.0 and 1.0
        - max_spread_cross must be >= 0.0
        - Input files must exist
    """
    # Validate news_weight range
    if not 0.0 <= args.news_weight <= 1.0:
        raise ValueError(
            f"--news-weight must be between 0.0 and 1.0, got: {args.news_weight}"
        )

    # Validate max_spread_cross
    if args.max_spread_cross < 0.0:
        raise ValueError(
            f"--max-spread-cross must be >= 0.0, got: {args.max_spread_cross}"
        )

    # Validate max_allocation
    if not 0.0 < args.max_allocation <= 1.0:
        raise ValueError(
            f"--max-allocation must be between 0.0 and 1.0, got: {args.max_allocation}"
        )

    # Validate input files exist
    input_files = {
        'historical': args.historical,
        'markets': args.markets,
        'news': args.news
    }

    for file_type, file_path in input_files.items():
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(
                f"{file_type} file not found: {file_path}"
            )


def load_json_file(file_path: str, file_type: str) -> Dict[str, Any]:
    """
    Load and parse JSON file with error handling.

    Args:
        file_path: Path to JSON file
        file_type: Type of file for error messages ('historical', 'markets', 'news')

    Returns:
        Parsed JSON data as dictionary

    Raises:
        ValueError: If JSON is invalid or missing required fields
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {file_type} file: {e}")

    return data


def validate_historical_data(data: Dict[str, Any]) -> None:
    """
    Validate historical analysis data structure.

    Args:
        data: Historical analysis JSON data

    Raises:
        KeyError: If required fields are missing
        ValueError: If data structure is invalid
    """
    # Check top-level structure
    if 'analysis' not in data:
        raise KeyError("historical data missing 'analysis' field")

    if not isinstance(data['analysis'], list):
        raise ValueError("'analysis' field must be a list")

    if len(data['analysis']) == 0:
        raise ValueError("'analysis' field is empty - no historical data found")

    # Validate first item to check structure
    first_item = data['analysis'][0]
    required_fields = ['market_question', 'threshold', 'historical_probability', 'mention_rate']
    for field in required_fields:
        if field not in first_item:
            raise KeyError(f"historical analysis item missing required field: '{field}'")

    # Validate probability ranges
    for item in data['analysis']:
        prob = item.get('historical_probability', -1)
        if not 0.0 <= prob <= 1.0:
            raise ValueError(
                f"historical_probability must be 0.0-1.0, got {prob} for '{item.get('market_question', 'unknown')}'"
            )


def validate_markets_data(data: Dict[str, Any]) -> None:
    """
    Validate markets data structure.

    Args:
        data: Markets JSON data

    Raises:
        KeyError: If required fields are missing
        ValueError: If data structure is invalid
    """
    # Check top-level structure
    if 'markets' not in data:
        raise KeyError("markets data missing 'markets' field")

    if not isinstance(data['markets'], list):
        raise ValueError("'markets' field must be a list")

    if len(data['markets']) == 0:
        raise ValueError("'markets' field is empty - no market data found")

    # Validate first item to check structure
    first_market = data['markets'][0]
    required_fields = ['market_question', 'yes_price', 'no_price', 'best_bid', 'best_ask']
    for field in required_fields:
        if field not in first_market:
            raise KeyError(f"market item missing required field: '{field}'")

    # Validate price ranges
    for market in data['markets']:
        for price_field in ['yes_price', 'no_price', 'best_bid', 'best_ask']:
            price = market.get(price_field, -1)
            if not 0.0 <= price <= 1.0:
                raise ValueError(
                    f"{price_field} must be 0.0-1.0, got {price} for '{market.get('market_question', 'unknown')}'"
                )


def validate_news_data(data: Dict[str, Any]) -> None:
    """
    Validate news research data structure.

    Args:
        data: News JSON data

    Raises:
        KeyError: If required fields are missing
        ValueError: If data structure is invalid
    """
    # Check top-level structure
    if 'news' not in data:
        raise KeyError("news data missing 'news' field")

    if not isinstance(data['news'], list):
        raise ValueError("'news' field must be a list")

    if len(data['news']) == 0:
        raise ValueError("'news' field is empty - no news data found")

    # Validate first item to check structure
    first_item = data['news'][0]
    required_fields = ['market_question', 'summary', 'success']
    for field in required_fields:
        if field not in first_item:
            raise KeyError(f"news item missing required field: '{field}'")


def create_lookup_maps(
    historical_data: Dict[str, Any],
    markets_data: Dict[str, Any],
    news_data: Dict[str, Any]
) -> Tuple[Dict[str, Dict], Dict[str, Dict], Dict[str, Dict]]:
    """
    Create lookup dictionaries keyed by market question for efficient matching.

    Args:
        historical_data: Historical analysis data
        markets_data: Markets data
        news_data: News research data

    Returns:
        Tuple of (historical_map, markets_map, news_map) dictionaries
    """
    # Create historical lookup (keyed by 'market_question' which contains the question)
    historical_map = {
        item['market_question']: item
        for item in historical_data['analysis']
    }

    # Create markets lookup (keyed by 'market_question')
    markets_map = {
        item['market_question']: item
        for item in markets_data['markets']
    }

    # Create news lookup (keyed by 'market_question')
    news_map = {
        item['market_question']: item
        for item in news_data['news']
    }

    return historical_map, markets_map, news_map


def parse_earnings_relevance(summary: str) -> Optional[int]:
    """
    Extract EARNINGS RELEVANCE score from news summary.

    Args:
        summary: News summary text containing structured scoring

    Returns:
        Relevance score (1-10) or None if not found

    Example:
        "...EARNINGS RELEVANCE:** 9..." → 9
    """
    # Pattern: "EARNINGS RELEVANCE:** {number}" or "EARNINGS RELEVANCE: {number}"
    pattern = r'EARNINGS RELEVANCE[:\*\s]+(\d+)'
    match = re.search(pattern, summary, re.IGNORECASE)

    if match:
        score = int(match.group(1))
        # Validate range
        if 1 <= score <= 10:
            return score

    return None


def parse_mention_direction(summary: str) -> str:
    """
    Extract MENTION DIRECTION from news summary.

    Args:
        summary: News summary text containing structured scoring

    Returns:
        Direction: "Increased", "Decreased", "Neutral", or "Mixed"

    Example:
        "...MENTION DIRECTION:** Increased..." → "Increased"
    """
    # Pattern: "MENTION DIRECTION:** {word}" or "MENTION DIRECTION: {word}"
    pattern = r'MENTION DIRECTION[:\*\s]+(Increased|Decreased|Neutral|Mixed)'
    match = re.search(pattern, summary, re.IGNORECASE)

    if match:
        direction = match.group(1).capitalize()
        return direction

    # Default to Neutral if not found
    return "Neutral"


def calculate_news_adjustment(
    historical_probability: float,
    news_item: Optional[Dict[str, Any]],
    news_weight: float
) -> Tuple[float, Dict[str, Any]]:
    """
    Calculate fair value adjusted for recent news.

    Uses the formula: news_adjustment = (relevance/10) * news_weight * direction_multiplier
    where direction_multiplier is:
        +1 for "Increased" (bullish)
        -1 for "Decreased" (bearish)
         0 for "Neutral" or "Mixed"

    Args:
        historical_probability: Base probability from historical analysis (0.0-1.0)
        news_item: News research item (or None if no news available)
        news_weight: Weight to apply to news adjustment (0.0-1.0)

    Returns:
        Tuple of (adjusted_fair_value, adjustment_details)
        - adjusted_fair_value: Historical probability + news adjustment (clamped to 0.0-1.0)
        - adjustment_details: Dict with relevance, direction, raw_adjustment, applied_adjustment
    """
    # Default: no news adjustment
    if news_item is None or not news_item.get('success', False):
        return historical_probability, {
            'relevance': 0,
            'direction': 'No News',
            'raw_adjustment': 0.0,
            'applied_adjustment': 0.0,
            'fair_value': historical_probability
        }

    summary = news_item.get('summary', '')

    # Parse structured scoring from summary
    relevance = parse_earnings_relevance(summary)
    direction = parse_mention_direction(summary)

    # Default to neutral if parsing failed
    if relevance is None:
        relevance = 5  # Default to middle relevance
        direction = 'Neutral'

    # Map direction to multiplier
    direction_multiplier = {
        'Increased': +1.0,
        'Decreased': -1.0,
        'Neutral': 0.0,
        'Mixed': 0.0
    }.get(direction, 0.0)

    # Calculate adjustment: (relevance/10) * news_weight * direction_multiplier
    raw_adjustment = (relevance / 10.0) * news_weight * direction_multiplier

    # Apply adjustment to historical probability
    adjusted_fair_value = historical_probability + raw_adjustment

    # Clamp to valid probability range [0.0, 1.0]
    clamped_fair_value = max(0.0, min(1.0, adjusted_fair_value))

    # Track how much we actually applied (after clamping)
    applied_adjustment = clamped_fair_value - historical_probability

    return clamped_fair_value, {
        'relevance': relevance,
        'direction': direction,
        'raw_adjustment': raw_adjustment,
        'applied_adjustment': applied_adjustment,
        'fair_value': clamped_fair_value
    }


def calculate_limit_price_yes(
    fair_value: float,
    best_bid: float,
    best_ask: float,
    max_spread_cross: float = 0.03
) -> Dict[str, float]:
    """
    Calculate limit order price for YES shares (enhanced hybrid strategy with safety rails).

    Strategy:
    - Hybrid maker/taker: Considers both bid (maker) and ask (taker) sides
    - Safety rail: Won't cross spread if it's wider than max_spread_cross
    - Target: min(fair_value - 0.05, best_bid + 0.02, best_ask - 0.02)

    Args:
        fair_value: News-adjusted fair value probability (0.0-1.0)
        best_bid: Current best bid price (0.0-1.0)
        best_ask: Current best ask price (0.0-1.0)
        max_spread_cross: Maximum spread willing to cross (default: 0.03 = 3%)

    Returns:
        Dict with 'min', 'max', 'target' prices for limit order range

    Example:
        fair_value=0.70, bid=0.60, ask=0.62, max_spread=0.03
        → spread=0.02 (< 0.03), so consider ask
        → target = min(0.65, 0.62, 0.60) = 0.60
        → range: 0.58-0.62
    """
    spread = best_ask - best_bid

    # Base target: fair value minus safety buffer
    fair_value_target = fair_value - 0.05

    # Maker target: slightly above best bid
    maker_target = best_bid + 0.02

    # Taker target: slightly below best ask (only if spread is reasonable)
    if spread <= max_spread_cross:
        # Spread is tight enough - consider crossing it
        taker_target = best_ask - 0.02
        target = min(fair_value_target, maker_target, taker_target)
    else:
        # Spread too wide - fall back to maker-only strategy
        target = min(fair_value_target, maker_target)

    # Create limit order range (±2 cents around target)
    return {
        'target': max(0.01, min(0.99, target)),
        'min': max(0.01, target - 0.02),
        'max': min(0.99, target + 0.02)
    }


def calculate_limit_price_no(
    fair_value: float,
    best_bid: float,
    best_ask: float,
    current_no_price: float,
    max_spread_cross: float = 0.03
) -> Dict[str, float]:
    """
    Calculate limit order price for NO shares (enhanced hybrid strategy with safety rails).

    Strategy:
    - Convert YES fair value to NO fair value: (1 - fair_value)
    - Apply same hybrid maker/taker logic as YES shares
    - NO side has inverted bid/ask (best NO bid ≈ 1 - best YES ask)

    Args:
        fair_value: YES fair value probability (0.0-1.0)
        best_bid: Current best YES bid (0.0-1.0)
        best_ask: Current best YES ask (0.0-1.0)
        current_no_price: Current NO price (0.0-1.0)
        max_spread_cross: Maximum spread willing to cross (default: 0.03)

    Returns:
        Dict with 'min', 'max', 'target' prices for limit order range

    Example:
        YES fair_value=0.70 → NO fair_value=0.30
        → target NO price = 0.30 - 0.05 = 0.25
    """
    # Convert YES fair value to NO fair value
    no_fair_value = 1.0 - fair_value

    # NO side pricing (inverted from YES side)
    # Best NO bid ≈ 1 - best YES ask
    # Best NO ask ≈ 1 - best YES bid
    no_best_bid = 1.0 - best_ask
    no_best_ask = 1.0 - best_bid

    # Calculate NO spread
    spread = no_best_ask - no_best_bid

    # Base target: NO fair value minus safety buffer
    fair_value_target = no_fair_value - 0.05

    # Maker target: slightly above best NO bid
    maker_target = no_best_bid + 0.02

    # Taker target: slightly below best NO ask (only if spread is reasonable)
    if spread <= max_spread_cross:
        taker_target = no_best_ask - 0.02
        target = min(fair_value_target, maker_target, taker_target)
    else:
        # Spread too wide - fall back to maker-only
        target = min(fair_value_target, maker_target)

    # Create limit order range (±2 cents around target)
    return {
        'target': max(0.01, min(0.99, target)),
        'min': max(0.01, target - 0.02),
        'max': min(0.99, target + 0.02)
    }


def calculate_edge(
    fair_value: float,
    market_price: float
) -> Dict[str, Any]:
    """
    Calculate trading edge between fair value and market price.

    Args:
        fair_value: News-adjusted fair value (0.0-1.0)
        market_price: Current YES market price (0.0-1.0)

    Returns:
        Dict with edge (absolute), edge_pct (percentage), side ('YES' or 'NO'),
        market_type ('UNDERPRICED' or 'OVERPRICED')
    """
    edge = fair_value - market_price
    edge_pct = edge * 100  # Convert to percentage points

    # Determine which side to bet
    if edge > 0:
        # Fair value > market price → market underprices YES
        side = 'YES'
        market_type = 'UNDERPRICED'
    else:
        # Fair value < market price → market overprices YES (bet NO)
        side = 'NO'
        market_type = 'OVERPRICED'

    return {
        'edge': edge,
        'edge_pct': edge_pct,
        'abs_edge': abs(edge),
        'abs_edge_pct': abs(edge_pct),
        'side': side,
        'market_type': market_type
    }


def determine_conviction(abs_edge: float) -> Tuple[str, float]:
    """
    Determine conviction tier and position size based on absolute edge magnitude.

    Conviction Tiers (from implementation plan):
    - STRONG: >20% absolute edge → 25% position size
    - MODERATE: >10% absolute edge → 15% position size
    - PASS: <10% absolute edge → 0% position size (no bet)

    Args:
        abs_edge: Absolute edge magnitude (0.0-1.0)

    Returns:
        Tuple of (conviction_tier, position_size)

    Example:
        abs_edge=0.23 → ('STRONG', 0.25)
        abs_edge=0.15 → ('MODERATE', 0.15)
        abs_edge=0.08 → ('PASS', 0.0)
    """
    if abs_edge > 0.20:
        return ('STRONG', 0.25)
    elif abs_edge > 0.10:
        return ('MODERATE', 0.15)
    else:
        return ('PASS', 0.0)


def generate_recommendation(
    edge_data: Dict[str, Any],
    historical_item: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Generate structured trading recommendation from edge data.

    Args:
        edge_data: Calculated edge and limit price data
        historical_item: Historical analysis data for rationale

    Returns:
        Complete recommendation dict with conviction, action, rationale
    """
    # Determine conviction tier
    conviction, position_size = determine_conviction(edge_data['abs_edge'])

    # Format action statement
    if conviction == 'PASS':
        action = 'PASS'
        action_detail = 'Edge too small to justify position'
    else:
        action = f"BUY {edge_data['side']}"
        action_detail = (
            f"Buy {edge_data['side']} shares at "
            f"${edge_data['limit_price_min']:.2f}-${edge_data['limit_price_max']:.2f} "
            f"(target ${edge_data['limit_price_target']:.2f})"
        )

    # Build rationale from historical data
    mention_rate = historical_item.get('mention_rate', 0.0)
    avg_count = historical_item.get('avg_count', 0.0)
    quarters_analyzed = len(historical_item.get('quarters', {}))

    historical_rationale = (
        f"Historical: {mention_rate:.0%} mention rate "
        f"({avg_count:.1f} avg mentions) "
        f"across {quarters_analyzed} quarters"
    )

    market_rationale = (
        f"Market: {edge_data['market_yes_price']:.0%} YES price "
        f"(spread: {edge_data['spread']:.1%})"
    )

    news_adj = edge_data.get('news_adjustment', {})
    if news_adj.get('direction') != 'No News':
        news_rationale = (
            f"News: {news_adj.get('direction')} direction "
            f"(relevance {news_adj.get('relevance')}/10), "
            f"adjusted fair value {news_adj.get('applied_adjustment', 0):+.1%}"
        )
    else:
        news_rationale = "News: No recent coverage"

    # Compile recommendation
    return {
        'market_question': edge_data['market_question'],
        'conviction': conviction,
        'position_size': position_size,
        'action': action,
        'action_detail': action_detail,
        'side': edge_data['side'],
        'fair_value': edge_data['fair_value'],
        'market_price': edge_data['market_yes_price'],
        'edge': edge_data['edge'],
        'edge_pct': edge_data['edge_pct'],
        'abs_edge': edge_data['abs_edge'],
        'abs_edge_pct': edge_data['abs_edge_pct'],
        'market_type': edge_data['market_type'],
        'limit_price_target': edge_data['limit_price_target'],
        'limit_price_min': edge_data['limit_price_min'],
        'limit_price_max': edge_data['limit_price_max'],
        'spread': edge_data['spread'],
        'rationale': {
            'historical': historical_rationale,
            'market': market_rationale,
            'news': news_rationale
        }
    }


def main():
    """Main execution function."""
    try:
        # Parse and validate arguments
        args = parse_arguments()

        print("=" * 60)
        print("PHASE 4: EDGE CALCULATOR")
        print("=" * 60)
        print(f"Historical Data: {args.historical}")
        print(f"Markets Data: {args.markets}")
        print(f"News Data: {args.news}")
        print(f"News Weight: {args.news_weight:.0%}")
        print(f"Max Spread Cross: {args.max_spread_cross:.1%}")
        print(f"Max Portfolio Allocation: {args.max_allocation:.0%}")
        print(f"Output: {args.output}")
        print()

        # Validate arguments
        validate_arguments(args)
        print("✓ All input files validated\n")

        # Step 2: Load and validate input JSON files
        print("Loading input data...")
        historical_data = load_json_file(args.historical, 'historical')
        validate_historical_data(historical_data)
        print(f"✓ Loaded {len(historical_data['analysis'])} historical analysis items")

        markets_data = load_json_file(args.markets, 'markets')
        validate_markets_data(markets_data)
        print(f"✓ Loaded {len(markets_data['markets'])} markets")

        news_data = load_json_file(args.news, 'news')
        validate_news_data(news_data)
        print(f"✓ Loaded {len(news_data['news'])} news items")

        # Create lookup maps for efficient matching
        historical_map, markets_map, news_map = create_lookup_maps(
            historical_data, markets_data, news_data
        )
        print(f"✓ Created lookup maps for {len(markets_map)} markets\n")

        # Step 3: Calculate news-adjusted fair values
        print("Calculating news-adjusted fair values...")
        fair_values = {}
        news_adjustments = {}

        for question, historical_item in historical_map.items():
            # Get historical probability
            hist_prob = historical_item['historical_probability']

            # Get news item (may be None if news doesn't cover this market)
            news_item = news_map.get(question)

            # Calculate adjusted fair value
            fair_value, adjustment_details = calculate_news_adjustment(
                hist_prob, news_item, args.news_weight
            )

            fair_values[question] = fair_value
            news_adjustments[question] = adjustment_details

            # Show summary for markets with news
            if news_item and news_item.get('success'):
                direction_symbol = {
                    'Increased': '↑',
                    'Decreased': '↓',
                    'Neutral': '→',
                    'Mixed': '↔',
                    'No News': '-'
                }.get(adjustment_details['direction'], '?')

                print(f"  {question[:60]}...")
                print(f"    Historical: {hist_prob:.1%} | "
                      f"News: {adjustment_details['direction']} (R={adjustment_details['relevance']}/10) | "
                      f"Adjustment: {adjustment_details['applied_adjustment']:+.1%} {direction_symbol} | "
                      f"Fair Value: {fair_value:.1%}")

        print(f"\n✓ Calculated {len(fair_values)} fair values with news adjustments\n")

        # Step 4: Calculate edges and limit prices for all markets
        print("Calculating edges and limit prices...")
        edges_data = []

        for question in markets_map.keys():
            # Get required data
            market = markets_map[question]
            fair_value = fair_values.get(question, 0.5)  # Default to 50% if missing
            news_adjustment = news_adjustments.get(question, {})

            # Calculate edge
            edge_info = calculate_edge(fair_value, market['yes_price'])

            # Calculate limit prices based on which side we're betting
            if edge_info['side'] == 'YES':
                limit_prices = calculate_limit_price_yes(
                    fair_value,
                    market['best_bid'],
                    market['best_ask'],
                    args.max_spread_cross
                )
            else:  # NO
                limit_prices = calculate_limit_price_no(
                    fair_value,
                    market['best_bid'],
                    market['best_ask'],
                    market['no_price'],
                    args.max_spread_cross
                )

            # Compile edge data
            edge_data = {
                'market_question': question,
                'fair_value': fair_value,
                'market_yes_price': market['yes_price'],
                'market_no_price': market['no_price'],
                'edge': edge_info['edge'],
                'edge_pct': edge_info['edge_pct'],
                'abs_edge': edge_info['abs_edge'],
                'abs_edge_pct': edge_info['abs_edge_pct'],
                'side': edge_info['side'],
                'market_type': edge_info['market_type'],
                'limit_price_target': limit_prices['target'],
                'limit_price_min': limit_prices['min'],
                'limit_price_max': limit_prices['max'],
                'best_bid': market['best_bid'],
                'best_ask': market['best_ask'],
                'spread': market['spread'],
                'news_adjustment': news_adjustment
            }

            edges_data.append(edge_data)

        # Sort by absolute edge (largest opportunities first)
        edges_data.sort(key=lambda x: x['abs_edge'], reverse=True)

        print(f"✓ Calculated edges for {len(edges_data)} markets")
        print(f"\nTop 3 opportunities by edge:")
        for i, edge in enumerate(edges_data[:3], 1):
            print(f"  {i}. {edge['market_question'][:60]}...")
            print(f"     Edge: {edge['edge_pct']:+.1f}% | "
                  f"Side: {edge['side']} | "
                  f"Fair: {edge['fair_value']:.1%} | "
                  f"Market: {edge['market_yes_price']:.1%} | "
                  f"Limit: ${edge['limit_price_target']:.2f}")

        print()

        # Step 5: Generate recommendations with conviction tiers
        print("Generating recommendations...")
        recommendations = []

        for edge_data in edges_data:
            # Get historical data for rationale
            question = edge_data['market_question']
            historical_item = historical_map.get(question, {})

            # Generate recommendation
            recommendation = generate_recommendation(edge_data, historical_item)
            recommendations.append(recommendation)

        # Categorize by conviction tier
        strong_conviction = [r for r in recommendations if r['conviction'] == 'STRONG']
        moderate_conviction = [r for r in recommendations if r['conviction'] == 'MODERATE']
        pass_recommendations = [r for r in recommendations if r['conviction'] == 'PASS']

        print(f"✓ Generated {len(recommendations)} recommendations")
        print(f"  STRONG conviction: {len(strong_conviction)} markets")
        print(f"  MODERATE conviction: {len(moderate_conviction)} markets")
        print(f"  PASS (edge <10%): {len(pass_recommendations)} markets")
        print()

        # Display strong conviction recommendations
        if strong_conviction:
            print("STRONG Conviction Opportunities (>20% edge, 25% position size):")
            for i, rec in enumerate(strong_conviction[:5], 1):  # Show top 5
                print(f"\n  {i}. {rec['market_question'][:70]}")
                print(f"     Action: {rec['action_detail']}")
                print(f"     Edge: {rec['edge_pct']:+.1f}% | Fair: {rec['fair_value']:.1%} | Market: {rec['market_price']:.1%}")
                print(f"     {rec['rationale']['historical']}")
                print(f"     {rec['rationale']['news']}")
        else:
            print("No STRONG conviction opportunities found (all edges <20%)")

        print()

        # Display moderate conviction recommendations (brief)
        if moderate_conviction:
            print(f"MODERATE Conviction Opportunities ({len(moderate_conviction)} markets, 10-20% edge, 15% position size):")
            for i, rec in enumerate(moderate_conviction[:3], 1):  # Show top 3
                print(f"  {i}. {rec['market_question'][:60]}... | "
                      f"Edge: {rec['edge_pct']:+.1f}% | "
                      f"Action: {rec['action']}")

        print()

        # Step 5.5: Scale positions if total allocation exceeds maximum
        print("Scaling portfolio positions...")

        # Calculate total raw allocation (before scaling)
        total_raw_allocation = sum(r['position_size'] for r in recommendations if r['conviction'] != 'PASS')

        # Determine scale factor
        if total_raw_allocation > args.max_allocation:
            scale_factor = args.max_allocation / total_raw_allocation
            print(f"⚠️  Raw allocation ({total_raw_allocation:.0%}) exceeds max ({args.max_allocation:.0%})")
            print(f"   Scaling all positions by {scale_factor:.1%} to fit within limit")
        else:
            scale_factor = 1.0
            print(f"✓ Raw allocation ({total_raw_allocation:.0%}) within max ({args.max_allocation:.0%})")

        # Apply scaling to all non-PASS recommendations
        for rec in recommendations:
            if rec['conviction'] != 'PASS':
                rec['raw_position_size'] = rec['position_size']  # Store original
                rec['position_size'] = rec['position_size'] * scale_factor  # Apply scale

        # Recalculate conviction tier totals after scaling
        strong_conviction = [r for r in recommendations if r['conviction'] == 'STRONG']
        moderate_conviction = [r for r in recommendations if r['conviction'] == 'MODERATE']

        total_scaled_allocation = sum(r['position_size'] for r in recommendations if r['conviction'] != 'PASS')

        print(f"✓ Scaled portfolio allocation: {total_scaled_allocation:.1%} of bankroll")
        if scale_factor < 1.0:
            print(f"  STRONG positions: 25% → {strong_conviction[0]['position_size']:.1%} each" if strong_conviction else "  No STRONG positions")
            print(f"  MODERATE positions: 15% → {moderate_conviction[0]['position_size']:.1%} each" if moderate_conviction else "  No MODERATE positions")
        print()

        # Step 6: Organize portfolio and write output
        print("Organizing portfolio and writing output...")

        # Create portfolio structure
        portfolio = {
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'historical_data': args.historical,
                'markets_data': args.markets,
                'news_data': args.news,
                'configuration': {
                    'news_weight': args.news_weight,
                    'max_spread_cross': args.max_spread_cross,
                    'max_allocation': args.max_allocation
                },
                'allocation': {
                    'total_raw': total_raw_allocation,
                    'total_scaled': total_scaled_allocation,
                    'scale_factor': scale_factor,
                    'was_scaled': scale_factor < 1.0
                },
                'summary': {
                    'total_markets': len(recommendations),
                    'strong_conviction': len(strong_conviction),
                    'moderate_conviction': len(moderate_conviction),
                    'pass': len(pass_recommendations)
                }
            },
            'recommendations': {
                'all': recommendations,
                'by_conviction': {
                    'high_conviction': strong_conviction,
                    'moderate_conviction': moderate_conviction,
                    'pass': pass_recommendations
                }
            }
        }

        # Write to output file
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(portfolio, f, indent=2, ensure_ascii=False)

        print(f"✓ Portfolio written to {args.output}")
        print(f"\nPortfolio Summary:")
        print(f"  Total markets analyzed: {len(recommendations)}")
        print(f"  STRONG conviction (>20% edge): {len(strong_conviction)} markets, "
              f"{sum(r['position_size'] for r in strong_conviction):.1%} total allocation")
        print(f"  MODERATE conviction (10-20% edge): {len(moderate_conviction)} markets, "
              f"{sum(r['position_size'] for r in moderate_conviction):.1%} total allocation")
        print(f"  PASS (<10% edge): {len(pass_recommendations)} markets, 0% allocation")

        # Show allocation breakdown
        print(f"\nAllocation Breakdown:")
        if scale_factor < 1.0:
            print(f"  Raw total (before scaling): {total_raw_allocation:.1%}")
            print(f"  Scale factor applied: {scale_factor:.1%}")
            print(f"  Final total allocation: {total_scaled_allocation:.1%} of bankroll ✅")
        else:
            print(f"  Total allocation: {total_scaled_allocation:.1%} of bankroll ✅")
        print(f"  Active positions: {len(strong_conviction) + len(moderate_conviction)} markets")
        print(f"  Unused allocation: {args.max_allocation - total_scaled_allocation:.1%}")

        print("\n✓ Phase 4 complete!")

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
