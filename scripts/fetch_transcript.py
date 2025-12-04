#!/usr/bin/env python3
"""
Fetch earnings call transcript from GuruFocus.

This script automates transcript extraction from GuruFocus pages,
replacing the manual PDF download and conversion workflow.

Enhanced version produces clean markdown output matching the format of
Tesla_Q1_2025_Transcript_PERFECT.md

Usage:
    python scripts/fetch_transcript.py \
        --url "https://www.gurufocus.com/stock/SBUX/transcripts/3015010" \
        --output data/starbucks_q1_2025/transcript.md
"""

import argparse
import re
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright


def extract_transcript_content(page) -> str:
    """
    Extract complete transcript using DOM selectors (robust approach).
    Falls back to text markers only if DOM extraction fails.

    Implementation from EARNINGS_ANALYSIS_SCRIPTS_IMPLEMENTATION_PLAN.md:115-189
    """
    # Method 1: Try DOM-based extraction (most robust)
    transcript = page.evaluate("""
        () => {
            // GuruFocus specific selectors
            const selectors = [
                'article',
                '[class*="transcript"]',
                '[class*="content-main"]',
                'main',
                '.article-content',
                '#transcript-content'
            ];

            for (const selector of selectors) {
                const element = document.querySelector(selector);
                if (element) {
                    const text = element.innerText;
                    // Verify this looks like a transcript (>10,000 chars)
                    if (text.length > 10000) {
                        return text;
                    }
                }
            }

            // If no container found, return null to trigger fallback
            return null;
        }
    """)

    if transcript and len(transcript) > 10000:
        # Clean up by removing footer sections
        transcript = _remove_footer_sections(transcript)
        return transcript.strip()

    # Method 2: Fallback to text-based boundary extraction
    print("Warning: DOM extraction failed, using text boundary fallback...")
    all_text = page.evaluate("() => document.body.innerText")

    # Find transcript start (common earnings call openings)
    start_patterns = [
        r'(?i)(good (morning|afternoon|evening), (everyone|ladies and gentlemen))',
        r'(?i)(thank you for (standing by|joining))',
        r'(?i)(greetings and welcome to)',
        r'(?i)(operator.*instructions)',
    ]

    start_idx = -1
    for pattern in start_patterns:
        match = re.search(pattern, all_text)
        if match and (start_idx == -1 or match.start() < start_idx):
            start_idx = match.start()

    if start_idx == -1:
        raise ValueError("Could not find transcript start (tried DOM and text methods)")

    # Find transcript end (structural markers)
    end_patterns = [
        r'(?i)(call participants|corporate participants|conference call participants)',
        r'(?i)(refinitiv streetevents|thomson reuters)',
        r'(?i)(disclaimer|forward[\-\s]looking statements)',
    ]

    end_idx = len(all_text)
    for pattern in end_patterns:
        match = re.search(pattern, all_text[start_idx:])
        if match and (start_idx + match.start()) < end_idx:
            end_idx = start_idx + match.start()

    transcript = all_text[start_idx:end_idx].strip()
    return transcript


def _remove_footer_sections(text: str) -> str:
    """
    Remove common footer sections that aren't transcript content.

    Implementation from EARNINGS_ANALYSIS_SCRIPTS_IMPLEMENTATION_PLAN.md:191-206
    """
    # Remove participant lists, disclaimers, etc.
    patterns = [
        r'Call Participants.*$',
        r'Corporate Participants.*$',
        r'Conference Call Participants.*$',
        r'Refinitiv StreetEvents.*$',
        r"We'd love to learn more about.*$",
        r'DISCLAIMER.*$',
    ]

    for pattern in patterns:
        text = re.sub(pattern, '', text, flags=re.DOTALL | re.IGNORECASE)

    return text


def _extract_metadata(page, url: str) -> dict:
    """Extract company name, quarter, date, and ticker from the page."""
    metadata = {
        'company': 'Unknown Company',
        'ticker': '',
        'quarter': '',
        'date': '',
        'source': 'GuruFocus'
    }

    # Try to extract from page title
    try:
        title = page.evaluate("() => document.title")

        # Pattern: "Q3 2025 Starbucks Corp Earnings Call Transcript"
        quarter_match = re.search(r'(Q\d)\s+(\d{4})\s+(.+?)\s+(Earnings|Corp)', title)
        if quarter_match:
            metadata['quarter'] = quarter_match.group(1)
            year = quarter_match.group(2)
            metadata['company'] = quarter_match.group(3).strip()
            metadata['quarter'] = f"{metadata['quarter']} {year}"

        # Extract ticker from URL: /stock/SBUX/transcripts/...
        ticker_match = re.search(r'/stock/([A-Z]+)/', url)
        if ticker_match:
            metadata['ticker'] = ticker_match.group(1)
    except Exception as e:
        print(f"Warning: Could not extract metadata: {e}")

    # Try to find date in the page content
    try:
        # Look for date patterns in visible text
        text = page.evaluate("() => document.body.innerText")
        date_patterns = [
            r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}',
            r'\d{1,2}/\d{1,2}/\d{4}'
        ]
        for pattern in date_patterns:
            date_match = re.search(pattern, text[:5000])  # Search first 5000 chars
            if date_match:
                metadata['date'] = date_match.group(0)
                break
    except Exception:
        pass

    return metadata


def _strip_navigation_content(text: str) -> str:
    """
    Remove GuruFocus navigation, stock info, and transcript lists.
    Keeps only the actual earnings call content.
    """
    # Find where the actual transcript starts (common patterns)
    start_patterns = [
        r'^Operator\s*$',
        r'^Good (morning|afternoon|evening)',
        r'^Thank you for (joining|standing by)',
        r'^Greetings and welcome',
    ]

    lines = text.split('\n')
    start_idx = 0

    # Find first occurrence of transcript start
    for i, line in enumerate(lines):
        for pattern in start_patterns:
            if re.match(pattern, line.strip(), re.IGNORECASE):
                start_idx = i
                break
        if start_idx > 0:
            break

    # If we found a start, use it; otherwise skip first 100 lines as navigation
    if start_idx > 0:
        cleaned_lines = lines[start_idx:]
    else:
        # Fallback: skip everything until we see substantial content
        cleaned_lines = lines[100:]

    return '\n'.join(cleaned_lines)


def _format_speakers_as_headers(text: str) -> str:
    """
    Convert speaker names to markdown headers.

    Input format:
        Speaker Name
        Company Title

        Speech content...

    Output format:
        ### Speaker Name
        Company Title

        Speech content...
    """
    lines = text.split('\n')
    formatted_lines = []
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        # Check if this looks like a speaker name (followed by a title line)
        if line and i + 1 < len(lines):
            next_line = lines[i + 1].strip()

            # Speaker patterns: capitalized name, followed by title line
            # Title patterns: "Company Name - Title" or "Title"
            is_speaker = (
                line and
                not line.startswith('#') and
                len(line) < 50 and  # Names are usually short
                not line.endswith('.') and  # Not a sentence
                (
                    '-' in next_line or  # "Company - Title"
                    any(title_word in next_line.lower() for title_word in [
                        'analyst', 'officer', 'ceo', 'cfo', 'president',
                        'director', 'relations', 'head', 'vice'
                    ])
                )
            )

            if is_speaker and next_line:
                # Format as markdown header
                formatted_lines.append(f"### {line}")
                formatted_lines.append(next_line)
                formatted_lines.append('')  # Blank line after title
                i += 2
                continue

        formatted_lines.append(line)
        i += 1

    return '\n'.join(formatted_lines)


def _build_clean_markdown(raw_transcript: str, metadata: dict) -> str:
    """
    Build final clean markdown with header, sections, and formatted speakers.

    Matches format of Tesla_Q1_2025_Transcript_PERFECT.md
    """
    # Strip navigation content
    clean_text = _strip_navigation_content(raw_transcript)

    # Format speakers as headers
    clean_text = _format_speakers_as_headers(clean_text)

    # Build header
    company = metadata.get('company', 'Unknown Company')
    ticker = metadata.get('ticker', '')
    quarter = metadata.get('quarter', '')
    date = metadata.get('date', '')
    source = metadata.get('source', 'GuruFocus')

    ticker_display = f" ({ticker})" if ticker else ""
    quarter_display = f" {quarter}" if quarter else ""

    header = f"# {company}{ticker_display}{quarter_display} Earnings Call Transcript\n\n"

    if date:
        header += f"**Date:** {date}\n"
    header += f"**Source:** {source}\n\n"
    header += "---\n\n"

    # Add opening remarks section if applicable
    if clean_text.strip().startswith('###') or clean_text.strip().startswith('Operator'):
        header += "## Opening Remarks\n\n"

    # Combine
    full_markdown = header + clean_text

    # Add clean ending
    full_markdown = full_markdown.rstrip() + "\n\n---\n\n**End of Transcript**\n"

    return full_markdown


def fetch_gurufocus_transcript(url: str, output_path: str) -> None:
    """
    Fetch transcript from GuruFocus using Playwright.
    Handles Cloudflare protection and extracts complete content.
    Produces clean markdown output matching Tesla_Q1_2025_Transcript_PERFECT.md format.

    Implementation from EARNINGS_ANALYSIS_SCRIPTS_IMPLEMENTATION_PLAN.md:208-255
    Enhanced with metadata extraction and clean formatting.
    """
    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        )
        page = context.new_page()

        print(f"Navigating to {url}...")
        page.goto(url, wait_until='networkidle', timeout=30000)

        # Wait for content to load
        page.wait_for_timeout(2000)

        # Close registration popup if present
        try:
            close_button = page.locator('button:has-text("×"), [aria-label*="Close"]').first
            if close_button.is_visible():
                close_button.click()
                print("Closed registration popup")
        except Exception:
            pass  # No popup or already closed

        # Extract metadata
        print("Extracting metadata...")
        metadata = _extract_metadata(page, url)
        print(f"✓ Company: {metadata['company']} ({metadata['ticker']})")
        print(f"✓ Quarter: {metadata['quarter']}")

        # Extract transcript
        print("Extracting transcript...")
        raw_transcript = extract_transcript_content(page)

        # Verify extraction
        if len(raw_transcript) < 5000:
            raise ValueError(f"Transcript too short ({len(raw_transcript)} chars). Expected >5000 chars. Check extraction logic.")

        print(f"✓ Extracted {len(raw_transcript):,} characters (raw)")

        # Build clean markdown
        print("Cleaning and formatting...")
        clean_markdown = _build_clean_markdown(raw_transcript, metadata)

        print(f"✓ Cleaned to {len(clean_markdown):,} characters")

        # Save to file
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(clean_markdown)

        print(f"✓ Saved to {output_path}")

        browser.close()


def main():
    parser = argparse.ArgumentParser(
        description='Fetch earnings call transcript from GuruFocus'
    )
    parser.add_argument('--url', required=True, help='GuruFocus transcript URL')
    parser.add_argument('--output', required=True, help='Output markdown file path')
    args = parser.parse_args()

    fetch_gurufocus_transcript(args.url, args.output)


if __name__ == '__main__':
    main()
