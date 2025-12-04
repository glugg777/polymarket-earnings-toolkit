#!/usr/bin/env python3
"""
Polymarket Market Data Fetcher

Phase 1 of Earnings Analysis Scripts
Fetches market data from Polymarket Gamma API and CLOB API

Usage:
    python scripts/fetch_market.py \
        --event-url "https://polymarket.com/event/tesla-q3-earnings" \
        --output data/tesla_q3_2025/markets.json

Output:
    JSON file with event metadata, market pricing, and order book data
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

import requests
from lib.url_parser import extract_slug
from lib.criteria_parser import parse_criteria


# API Base URLs
GAMMA_API_BASE = "https://gamma-api.polymarket.com"
CLOB_API_BASE = "https://clob.polymarket.com"


def fetch_event_data(slug: str) -> Dict[str, Any]:
    """
    Fetch event and market data from Polymarket Gamma API.

    Step 1: Get event by slug
    Step 2: Get full event details with all markets

    Args:
        slug: Event slug (e.g., "tesla-q3-earnings")

    Returns:
        Full event data with markets array

    Raises:
        requests.HTTPError: If API call fails
        ValueError: If no event found for slug
    """
    print(f"Fetching event data for slug: {slug}")

    # Step 1: Get event by slug
    events_url = f"{GAMMA_API_BASE}/events?slug={slug}"
    response = requests.get(events_url)
    response.raise_for_status()
    events = response.json()

    if not events or len(events) == 0:
        raise ValueError(f"No event found for slug: {slug}")

    event = events[0]
    event_id = event['id']

    print(f"✓ Found event: {event.get('title', 'Unknown')}")

    # Step 2: Get full event with all markets
    full_url = f"{GAMMA_API_BASE}/events/{event_id}"
    full_response = requests.get(full_url)
    full_response.raise_for_status()

    full_event = full_response.json()
    num_markets = len(full_event.get('markets', []))
    print(f"✓ Found {num_markets} markets")

    return full_event


def fetch_order_books_batch(token_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Fetch order books for multiple tokens in a single batch call.

    Uses POST /books endpoint (supports up to 500 tokens per request)
    More efficient than individual GET /book calls

    Args:
        token_ids: List of token IDs to fetch order books for

    Returns:
        Dictionary mapping token_id → order book data

    Raises:
        requests.HTTPError: If API call fails
    """
    if not token_ids:
        return {}

    print(f"Fetching order books for {len(token_ids)} markets...")

    # Build request payload
    payload = [{"token_id": token_id} for token_id in token_ids]

    # POST /books endpoint
    url = f"{CLOB_API_BASE}/books"
    response = requests.post(url, json=payload)
    response.raise_for_status()

    order_books = response.json()

    # Convert array response to dictionary keyed by asset_id (token_id)
    order_book_map = {}
    for book in order_books:
        asset_id = book.get('asset_id')
        if asset_id:
            order_book_map[asset_id] = book

    print(f"✓ Fetched {len(order_book_map)} order books")

    return order_book_map


def parse_order_book(order_book: Dict[str, Any]) -> Dict[str, float]:
    """
    Parse order book data to extract pricing metrics.

    Calculates:
    - Best bid (highest buy order)
    - Best ask (lowest sell order)
    - Spread (difference between best ask and best bid)
    - Liquidity (sum of top 5 orders on each side)

    Args:
        order_book: Order book data from CLOB API

    Returns:
        Dictionary with best_bid, best_ask, spread, liquidity
    """
    bids = order_book.get('bids', [])
    asks = order_book.get('asks', [])

    # Parse best bid and ask
    best_bid = float(bids[0]['price']) if bids else 0.0
    best_ask = float(asks[0]['price']) if asks else 0.0

    # Calculate spread
    spread = best_ask - best_bid if (best_bid and best_ask) else 0.0

    # Calculate liquidity (sum of top 5 orders)
    bid_liquidity = sum(float(b['size']) for b in bids[:5])
    ask_liquidity = sum(float(a['size']) for a in asks[:5])
    total_liquidity = bid_liquidity + ask_liquidity

    return {
        'best_bid': best_bid,
        'best_ask': best_ask,
        'spread': spread,
        'liquidity': total_liquidity
    }


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description='Fetch Polymarket market data for earnings analysis'
    )
    parser.add_argument(
        '--event-url',
        required=True,
        help='Polymarket event URL (e.g., https://polymarket.com/event/tesla-q3-earnings)'
    )
    parser.add_argument(
        '--output',
        required=True,
        help='Output JSON file path (e.g., data/tesla_q3_2025/markets.json)'
    )
    args = parser.parse_args()

    try:
        # Step 1: Extract slug from URL
        print("\n=== Phase 1: Market Data Fetcher ===\n")
        slug = extract_slug(args.event_url)
        print(f"Extracted slug: {slug}")

        # Step 2: Fetch event data from Gamma API
        event_data = fetch_event_data(slug)

        # Step 3: Build output structure
        output = {
            'event': {
                'title': event_data.get('title', ''),
                'slug': slug,
                'date': event_data.get('endDate', ''),
                'volume': event_data.get('volume', 0),
                'active': event_data.get('active', True),
                'closed': event_data.get('closed', False)
            },
            'markets': []
        }

        # Step 4: Collect token IDs for batch order book fetch
        markets = event_data.get('markets', [])
        token_ids = []
        market_token_map = {}  # Map market to its token_id

        for market in markets:
            # clobTokenIds is a JSON array string like '["123", "456"]'
            clob_token_ids_str = market.get('clobTokenIds', '[]')
            try:
                clob_token_ids = json.loads(clob_token_ids_str)
                if clob_token_ids and len(clob_token_ids) > 0:
                    # Use first token ID (YES outcome)
                    token_id = clob_token_ids[0]
                    token_ids.append(token_id)
                    market_token_map[market['id']] = token_id
            except (json.JSONDecodeError, IndexError):
                # Skip markets without valid token IDs
                pass

        # Step 5: Batch fetch all order books (ONE API call)
        order_books = fetch_order_books_batch(token_ids)

        # Step 6: Process each market
        print("\nProcessing markets...")
        for market in markets:
            question = market.get('question', '')

            # Parse criteria to extract words and threshold
            parsed = parse_criteria(question)

            # Get pricing data (outcomePrices is a JSON array string like '["0.96", "0.04"]')
            outcome_prices_str = market.get('outcomePrices')
            if not outcome_prices_str:
                raise ValueError(f"No pricing data for market: {question}")

            try:
                outcome_prices = json.loads(outcome_prices_str)
                if len(outcome_prices) < 2:
                    raise ValueError(f"Invalid pricing format for market: {question}")
                yes_price = float(outcome_prices[0])
                no_price = float(outcome_prices[1])
            except (json.JSONDecodeError, ValueError, IndexError) as e:
                raise ValueError(f"Failed to parse pricing for market '{question}': {outcome_prices_str}. Error: {e}")

            # Get order book data (if available)
            order_book_data = {}
            market_id = market.get('id')
            token_id = market_token_map.get(market_id)

            if token_id and token_id in order_books:
                order_book_data = parse_order_book(order_books[token_id])
            else:
                # Fallback if no order book available
                order_book_data = {
                    'best_bid': 0.0,
                    'best_ask': 0.0,
                    'spread': 0.0,
                    'liquidity': 0.0
                }

            # Build market data structure
            market_data = {
                'market_question': question,  # Full question text for clarity
                'yes_price': yes_price,
                'no_price': no_price,
                'best_bid': order_book_data['best_bid'],
                'best_ask': order_book_data['best_ask'],
                'spread': order_book_data['spread'],
                'volume': float(market.get('volume', 0)),
                'liquidity': order_book_data['liquidity'],
                'market_id': market_id,
                'threshold': parsed['threshold'],
                'words': parsed['words']
            }

            output['markets'].append(market_data)
            print(f"  ✓ {question}")

        # Step 7: Write output JSON
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        # Summary
        print(f"\n✅ Success!")
        print(f"✓ Event: {output['event']['title']}")
        print(f"✓ Markets: {len(output['markets'])}")
        print(f"✓ Saved to: {args.output}")

    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
