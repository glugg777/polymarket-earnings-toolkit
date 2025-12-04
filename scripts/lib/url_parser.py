"""
Extract Polymarket event slug from URLs.

Port of TypeScript implementation from src/utils/marketParser.ts:146-150

Usage:
    from lib.url_parser import extract_slug

    slug = extract_slug("https://polymarket.com/event/tesla-q3-earnings")
    # Returns: "tesla-q3-earnings"
"""

import re
from typing import Optional


def extract_slug(url: str) -> str:
    """
    Extract event slug from Polymarket URL.

    Args:
        url: Polymarket event URL (e.g., "https://polymarket.com/event/tesla-q3-earnings")
             Also accepts just the slug itself (e.g., "tesla-q3-earnings")

    Returns:
        The event slug (e.g., "tesla-q3-earnings")

    Raises:
        ValueError: If URL format is invalid or slug cannot be extracted

    Examples:
        >>> extract_slug("https://polymarket.com/event/tesla-q3-earnings")
        "tesla-q3-earnings"

        >>> extract_slug("https://polymarket.com/event/what-will-tesla-tsla-say-during-their-next-earnings-call")
        "what-will-tesla-tsla-say-during-their-next-earnings-call"

        >>> extract_slug("tesla-q3-earnings")
        "tesla-q3-earnings"

        >>> extract_slug("invalid-url")
        ValueError: Could not extract slug from URL: invalid-url
    """
    # If it's already just a slug (no protocol/domain), return it
    if not url.startswith('http') and '/' not in url:
        slug = url.strip()
        if validate_slug(slug):
            return slug
        raise ValueError(f"Invalid slug format: {slug}")

    # Extract from URL pattern: polymarket.com/event/{slug}
    match = re.search(r'polymarket\.com/event/([^/?#]+)', url)

    if match:
        return match.group(1)

    raise ValueError(f"Could not extract slug from URL: {url}")


def validate_slug(slug: str) -> bool:
    """
    Validate that slug matches expected Polymarket format.

    Polymarket slugs are typically lowercase, hyphen-separated words.

    Args:
        slug: Slug to validate

    Returns:
        True if valid, False otherwise

    Examples:
        >>> validate_slug("tesla-q3-earnings")
        True

        >>> validate_slug("what-will-meta-say")
        True

        >>> validate_slug("INVALID_SLUG")
        False

        >>> validate_slug("ab")
        False
    """
    # Basic validation: alphanumeric + hyphens, 3-200 chars
    pattern = r'^[a-z0-9\-]{3,200}$'
    return bool(re.match(pattern, slug))


if __name__ == '__main__':
    # Test cases
    test_urls = [
        "https://polymarket.com/event/tesla-q3-earnings",
        "https://polymarket.com/event/what-will-tesla-tsla-say-during-their-next-earnings-call",
        "tesla-q3-earnings",
        "https://polymarket.com/event/trump-vp-debate-speech?some=param",
    ]

    print("Testing URL parser:")
    print("✓ Valid URLs:")
    for url in test_urls:
        try:
            slug = extract_slug(url)
            print(f"  {url[:60]:60} → {slug}")
        except ValueError as e:
            print(f"  {url[:60]:60} → ERROR: {e}")

    print("\n✓ Invalid URLs (should raise errors):")
    invalid_urls = ["INVALID_SLUG", "bad_slug_with_underscores", "ab", "http://example.com/wrong", ""]
    for url in invalid_urls:
        try:
            slug = extract_slug(url)
            print(f"  {url[:60]:60} → {slug} (UNEXPECTED SUCCESS)")
        except ValueError as e:
            print(f"  {url[:60]:60} → ✓ Correctly raised error")
