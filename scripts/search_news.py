#!/usr/bin/env python3
"""
Phase 3: News Researcher
Searches recent news for market topics using Perplexity API.

Usage:
    python scripts/search_news.py \
        --words data/tesla_q3_2025/markets.json \
        --company "Tesla" \
        --date "2025-10-22" \
        --output data/tesla_q3_2025/news.json

Output:
    Creates news.json with comprehensive research findings for each market
    and macro economic context.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables from .env file
load_dotenv()


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Search recent news for earnings call market topics',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Search news for Tesla earnings
    python scripts/search_news.py \\
        --words data/tesla_q3_2025/markets.json \\
        --company "Tesla" \\
        --date "2025-10-22" \\
        --output data/tesla_q3_2025/news.json

    # Search with custom delay
    python scripts/search_news.py \\
        --words data/microsoft_q1_2025/markets.json \\
        --company "Microsoft" \\
        --date "2025-10-29" \\
        --delay 3 \\
        --output data/microsoft_q1_2025/news.json
        """
    )

    parser.add_argument(
        '--words',
        required=True,
        help='Path to markets.json file (output from Phase 1)'
    )

    parser.add_argument(
        '--company',
        required=True,
        help='Company name for search context (e.g., "Tesla", "Microsoft")'
    )

    parser.add_argument(
        '--date',
        required=True,
        help='Earnings call date in YYYY-MM-DD format (e.g., "2025-10-22")'
    )

    parser.add_argument(
        '--output',
        required=True,
        help='Output path for news.json file'
    )

    parser.add_argument(
        '--delay',
        type=float,
        default=2.5,
        help='Delay in seconds between API calls (default: 2.5, recommended: 2-3 to avoid rate limits)'
    )

    parser.add_argument(
        '--max-retries',
        type=int,
        default=1,
        help='Maximum number of retries for failed API calls (default: 1)'
    )

    return parser.parse_args()


def load_markets_data(file_path: str) -> Dict:
    """
    Load markets.json file from Phase 1 output.

    Args:
        file_path: Path to markets.json file

    Returns:
        Dictionary containing event and markets data

    Raises:
        FileNotFoundError: If markets.json doesn't exist
        json.JSONDecodeError: If JSON is malformed
        ValueError: If required fields are missing
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Markets file not found: {file_path}")

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Validate structure
    if 'markets' not in data:
        raise ValueError(f"Invalid markets.json: missing 'markets' field")

    if not isinstance(data['markets'], list):
        raise ValueError(f"Invalid markets.json: 'markets' must be a list")

    print(f"✓ Loaded {len(data['markets'])} markets from {file_path}")
    return data


def initialize_perplexity_client(api_key: str) -> OpenAI:
    """
    Initialize Perplexity API client using OpenAI-compatible interface.

    Args:
        api_key: Perplexity API key

    Returns:
        OpenAI client configured for Perplexity API

    Reference:
        Perplexity API uses OpenAI-compatible endpoint at:
        https://api.perplexity.ai
    """
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.perplexity.ai"
    )
    print("✓ Perplexity API client initialized")
    return client


def generate_search_query(
    market_question: str,
    company: str,
    event_date: str
) -> str:
    """
    Generate optimized search query for a market topic.

    Args:
        market_question: The full market question (e.g., "Will Tesla mention Robotaxi 5+ times?")
        company: Company name (e.g., "Tesla")
        event_date: Event date in YYYY-MM-DD format

    Returns:
        Optimized search query string

    Example:
        Input: "Will Tesla mention Robotaxi 5+ times?", "Tesla", "2025-10-22"
        Output: "Tesla Robotaxi October 2025 news updates announcements developments"

    Why this format:
        - Extracts key topic from question (e.g., "Robotaxi" from quoted text)
        - Adds company name for context
        - Adds month/year from event date
        - Adds semantic keywords to broaden relevant results
    """
    # Extract main topic from question
    # Common patterns: "Will X say 'TOPIC'" or "Will X mention TOPIC"
    topic = market_question

    # Remove common question prefixes
    prefixes_to_remove = [
        f"Will {company} say",
        f"Will {company} mention",
        "during earnings call",
        "during their next earnings call",
        "?",
        '"',
    ]

    for prefix in prefixes_to_remove:
        topic = topic.replace(prefix, "").strip()

    # Parse date for month/year
    try:
        date_obj = datetime.strptime(event_date, '%Y-%m-%d')
        month = date_obj.strftime('%B')  # Full month name
        year = date_obj.year
    except ValueError:
        # Fallback to just the year if date parsing fails
        month = ""
        year = event_date.split('-')[0]

    # Build comprehensive search query
    query = f"{company} {topic} {month} {year} news updates announcements developments"

    # Clean up extra spaces
    query = ' '.join(query.split())

    return query


def search_perplexity(
    client: OpenAI,
    query: str,
    max_retries: int = 1
) -> Dict:
    """
    Search Perplexity API for comprehensive results.

    Args:
        client: Initialized Perplexity OpenAI client
        query: Search query string
        max_retries: Maximum retry attempts on failure

    Returns:
        Dictionary with:
            - content: The full response text
            - success: Boolean indicating if search succeeded
            - error: Error message if failed (None if successful)

    API Model:
        Uses 'sonar-reasoning-pro' (DeepSeek-R1 with Chain of Thought) for analytical reasoning.
        Alternative models: 'sonar-pro' (search-focused), 'sonar-reasoning' (faster reasoning)

    Retry Logic:
        - Retries once on failure (configurable)
        - 3-second delay between retries
        - Returns error dict if all retries fail
    """
    system_prompt = """You are an earnings call news researcher analyzing information relevant to quarterly earnings discussions.

Focus on developments likely to be mentioned or addressed in earnings calls:
- Product launches, feature releases, and development updates with specific dates
- Partnerships, acquisitions, regulatory approvals, or legal developments
- Operational metrics (users, revenue, market share when publicly disclosed)
- Strategic initiatives, executive statements, and forward-looking guidance
- Controversies, stock price reactions, and investor concerns (topics management will likely address)
- Analyst focus areas and common questions from recent quarters

Provide specific dates, numbers, and credible sources. Structure information clearly:
- Confirmed announcements (e.g., "announced on Oct 23, 2025")
- Credible reporting (e.g., "according to Bloomberg on Oct 15")
- Market reactions (e.g., "stock fell 8% following...")
- Analyst commentary (e.g., "JPMorgan raised concerns about...")
- Speculation (e.g., "expected to launch in Q4")

For each development, indicate:
- Whether it represents NEW activity since last earnings (more likely to be discussed) or ongoing/historical context
- The magnitude/significance of the development
- Any management commentary or official statements"""

    # Enhance query with structured assessment request
    enhanced_query = f"""{query}

After your comprehensive summary, provide a structured assessment for earnings call analysis:

**EARNINGS RELEVANCE:** [Score 1-10] - How likely is this specific topic to be mentioned or discussed on the earnings call?
**MENTION DIRECTION:** [Increased/Decreased/Neutral] - Compared to historical patterns, does recent news make mentions more likely, less likely, or neutral?
**KEY SIGNAL:** [2-3 sentences] - What is the most important factor influencing whether this topic gets airtime on the call? Consider new developments, controversies, investor focus, and management priorities."""

    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model="sonar-reasoning-pro",  # Chain of Thought reasoning for analytical tasks
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": enhanced_query}
                ],
                # No max_tokens limit - let API return comprehensive results
            )

            content = response.choices[0].message.content

            return {
                'content': content,
                'success': True,
                'error': None
            }

        except Exception as e:
            if attempt < max_retries:
                print(f"  ⚠ API error (attempt {attempt + 1}/{max_retries + 1}): {str(e)}")
                print(f"  ⏳ Retrying in 3 seconds...")
                time.sleep(3)
            else:
                print(f"  ✗ API error after {max_retries + 1} attempts: {str(e)}")
                return {
                    'content': '',
                    'success': False,
                    'error': str(e)
                }

    # Should never reach here, but safety fallback
    return {
        'content': '',
        'success': False,
        'error': 'Unknown error'
    }


def main():
    """Main execution function."""
    # Parse arguments
    args = parse_arguments()

    # Verify API key is set
    api_key = os.getenv('PERPLEXITY_API_KEY')
    if not api_key or api_key == 'your_api_key_here':
        print("ERROR: PERPLEXITY_API_KEY not set in environment")
        print("Please set your API key in .env file")
        sys.exit(1)

    print("=" * 60)
    print("PHASE 3: NEWS RESEARCHER")
    print("=" * 60)
    print(f"Company: {args.company}")
    print(f"Event Date: {args.date}")
    print(f"Markets Source: {args.words}")
    print(f"Output: {args.output}")
    print(f"API Delay: {args.delay}s between calls")
    print(f"Max Retries: {args.max_retries}")
    print()

    # Load markets data
    try:
        markets_data = load_markets_data(args.words)
    except Exception as e:
        print(f"ERROR: Failed to load markets data: {e}")
        sys.exit(1)

    # Initialize Perplexity client
    client = initialize_perplexity_client(api_key)

    # Step 4: Search for each market topic
    print(f"\n{'=' * 60}")
    print(f"SEARCHING NEWS FOR {len(markets_data['markets'])} MARKETS")
    print(f"{'=' * 60}\n")

    news_results = []
    successful_searches = 0
    failed_searches = 0

    for idx, market in enumerate(markets_data['markets'], 1):
        market_question = market.get('market_question', market.get('word', 'Unknown'))

        print(f"[{idx}/{len(markets_data['markets'])}] {market_question}")

        # Generate search query
        query = generate_search_query(market_question, args.company, args.date)
        print(f"  Query: {query}")
        print(f"  🔍 Searching Perplexity API...")

        # Search Perplexity
        result = search_perplexity(client, query, args.max_retries)

        if result['success']:
            print(f"  ✓ Found {len(result['content'])} characters of news")
            successful_searches += 1

            news_results.append({
                'market_question': market_question,
                'query': query,
                'summary': result['content'],
                'success': True,
                'error': None
            })
        else:
            print(f"  ✗ Search failed: {result['error']}")
            failed_searches += 1

            # Still add to results, but mark as failed
            news_results.append({
                'market_question': market_question,
                'query': query,
                'summary': '',
                'success': False,
                'error': result['error']
            })

        # Rate limiting: delay between searches (except after last one)
        if idx < len(markets_data['markets']):
            print(f"  ⏳ Waiting {args.delay}s before next search...\n")
            time.sleep(args.delay)
        else:
            print()  # Just a newline after last search

    # Step 5: Search macro context
    print(f"{'=' * 60}")
    print("SEARCHING MACRO ECONOMIC CONTEXT")
    print(f"{'=' * 60}\n")

    # Parse date for macro query
    try:
        date_obj = datetime.strptime(args.date, '%Y-%m-%d')
        month = date_obj.strftime('%B')
        year = date_obj.year
    except ValueError:
        month = "recent"
        year = ""

    macro_query = f"US economy inflation recession tariffs {month} {year} economic outlook GDP interest rates Federal Reserve"
    print(f"Query: {macro_query}")

    macro_result = search_perplexity(client, macro_query, args.max_retries)

    if macro_result['success']:
        print(f"✓ Found {len(macro_result['content'])} characters of macro context\n")
        macro_context = {
            'query': macro_query,
            'summary': macro_result['content'],
            'success': True,
            'error': None
        }
    else:
        print(f"✗ Macro search failed: {macro_result['error']}\n")
        macro_context = {
            'query': macro_query,
            'summary': '',
            'success': False,
            'error': macro_result['error']
        }

    # Step 6: Save results to JSON
    print(f"{'=' * 60}")
    print("SAVING RESULTS")
    print(f"{'=' * 60}\n")

    output_data = {
        'metadata': {
            'company': args.company,
            'event_date': args.date,
            'generated_at': datetime.now().isoformat(),
            'total_markets': len(markets_data['markets']),
            'successful_searches': successful_searches,
            'failed_searches': failed_searches
        },
        'news': news_results,
        'macro_context': macro_context
    }

    # Create output directory if needed
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write JSON
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"✓ Saved {len(news_results)} market news results")
    print(f"✓ Saved macro economic context")
    print(f"✓ Results written to {args.output}")

    # Summary
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    print(f"Total Markets: {len(markets_data['markets'])}")
    print(f"Successful: {successful_searches}")
    print(f"Failed: {failed_searches}")
    print(f"Success Rate: {successful_searches / len(markets_data['markets']) * 100:.1f}%")
    print()

    if failed_searches > 0:
        print("⚠ Some searches failed. Check the output JSON for error details.")
        print("  Consider increasing --max-retries or --delay parameters.")

    print("\n✓ Phase 3 complete!")


if __name__ == '__main__':
    main()
