"""
Parse Polymarket market criteria to extract target words and thresholds.

Port of TypeScript implementation from src/utils/marketParser.ts:8-71

This parser handles various patterns:
- "Word 5+ times" → {words: ["word"], threshold: 5}
- "A or B" → {words: ["a", "b"], threshold: 1}
- "A/B" → {words: ["a", "b"], threshold: 1}
- "AI or Artificial Intelligence" → {words: ["ai", "artificial intelligence"], threshold: 1}

Usage:
    from lib.criteria_parser import parse_criteria

    result = parse_criteria("Robotaxi 5+ times")
    # Returns: {"words": ["robotaxi"], "threshold": 5}
"""

import re
from typing import List, Dict, Any


def parse_criteria(criteria: str) -> Dict[str, Any]:
    """
    Parse market criteria string to extract target words and count threshold.

    Args:
        criteria: The market question/outcome (e.g., "Israel 7+ times", "Palestine")

    Returns:
        Dictionary with:
            - words: List of target words to detect (lowercase)
            - threshold: Minimum count required (default: 1)

    Examples:
        >>> parse_criteria("Robotaxi 5+ times")
        {"words": ["robotaxi"], "threshold": 5}

        >>> parse_criteria("Penalty or Flag 30+ times")
        {"words": ["penalty", "flag"], "threshold": 30}

        >>> parse_criteria("AI or Artificial Intelligence")
        {"words": ["ai", "artificial intelligence"], "threshold": 1}

        >>> parse_criteria("UN/United Nations")
        {"words": ["un", "united", "nations"], "threshold": 1}

        >>> parse_criteria("Palestine")
        {"words": ["palestine"], "threshold": 1}
    """
    words: List[str] = []
    threshold = 1

    # First, check for quoted content in questions like:
    # "Will Microsoft say \"Copilot\" during earnings call?"
    # This handles both \" escaped quotes and regular " quotes
    quoted_match = re.search(r'["\"]([^"\"]+)["\"]', criteria)

    if quoted_match:
        # Extract the quoted content
        quoted_content = quoted_match.group(1)

        # Check if quoted content has a threshold pattern
        times_in_quotes = re.search(r'(.+?)\s+(\d+)\+\s+times?', quoted_content, re.IGNORECASE)
        if times_in_quotes:
            word_part = times_in_quotes.group(1)
            threshold = int(times_in_quotes.group(2))
        else:
            word_part = quoted_content
            threshold = 1

        # Apply same parsing logic to quoted content
        # Handle "or" cases like "AI or Artificial Intelligence"
        if ' or ' in word_part.lower():
            parts = re.split(r'\s+or\s+', word_part, flags=re.IGNORECASE)
            for part in parts:
                words.append(part.lower().strip())
        # Handle "/" cases like "M365 / Microsoft 365" or "Shutdown / Shut Down"
        elif '/' in word_part:
            for part in word_part.split('/'):
                words.append(part.lower().strip())
        else:
            words.append(word_part.lower().strip())

        return {
            "words": words,
            "threshold": threshold
        }

    # If no quoted content, proceed with original logic
    # Extract pattern: "Word(s) N+ times" or just word
    times_match = re.search(r'(.+?)\s+(\d+)\+\s+times?', criteria, re.IGNORECASE)

    if times_match:
        # Has a count requirement (e.g., "Israel 7+ times")
        word_part = times_match.group(1)
        threshold = int(times_match.group(2))

        # Handle "or" cases like "Penalty or Flag 30+ times"
        if ' or ' in word_part.lower():
            parts = re.split(r'\s+or\s+', word_part, flags=re.IGNORECASE)
            for part in parts:
                words.append(part.lower().strip())
        # Handle compound words like "Thousand/Million/Billion"
        elif '/' in word_part:
            for word in word_part.split('/'):
                words.append(word.lower().strip())
        else:
            words.append(word_part.lower().strip())
    else:
        # No count specified, default to 1 mention (e.g., "Palestine", "TikTok")

        # Handle special cases
        if ' or ' in criteria.lower():
            # Handle "or" cases like "AI or Artificial Intelligence"
            parts = re.split(r'\s+or\s+', criteria, flags=re.IGNORECASE)
            for part in parts:
                clean_part = part.lower().strip()
                # Track each alternative as-is (including multi-word phrases)
                words.append(clean_part)
        elif '/' in criteria:
            # Handle slashes like "Erdogan/Turkey" or "UN/United Nations"
            for part in criteria.split('/'):
                clean_part = part.lower().strip()
                if ' ' in clean_part:
                    # Multi-word part - split into individual words
                    for word in clean_part.split():
                        if word:
                            words.append(word)
                else:
                    words.append(clean_part)
        elif 'young people' in criteria.lower():
            # Special case for phrases that should be tracked as whole
            words.append('young')
            words.append('people')
        else:
            # Single word outcomes
            words.append(criteria.lower().strip())

    return {
        "words": words,
        "threshold": threshold
    }


def detect_words_in_transcript(transcript: str, words: List[str]) -> int:
    """
    Count occurrences of target words in transcript.

    Port of TypeScript implementation from src/utils/marketParser.ts:73-107

    Args:
        transcript: The full transcript text
        words: List of target words to detect

    Returns:
        Total count of detections across all words

    Examples:
        >>> detect_words_in_transcript("Robotaxi is coming. Robotaxi launch soon.", ["robotaxi"])
        2

        >>> detect_words_in_transcript("We have AI and artificial intelligence.", ["ai", "artificial intelligence"])
        2
    """
    lower_transcript = transcript.lower()

    # Normalize common speech recognition quirks
    # "on side kick" → "onside kick"
    lower_transcript = re.sub(r'\bon\s+side\s+kick\b', 'onside kick', lower_transcript, flags=re.IGNORECASE)

    detection_count = 0

    for word in words:
        # Escape special regex characters
        escaped = re.escape(word)

        # For multi-word phrases, match the complete phrase
        if ' ' in word:
            phrase_regex = re.compile(rf'\b{escaped}\b', re.IGNORECASE)
            matches = phrase_regex.findall(lower_transcript)
            if matches:
                detection_count += len(matches)
        else:
            # For single words, use word boundaries
            word_regex = re.compile(rf'\b{escaped}\b', re.IGNORECASE)
            matches = word_regex.findall(lower_transcript)
            if matches:
                detection_count += len(matches)

    return detection_count


if __name__ == '__main__':
    # Test cases matching TypeScript implementation + new quoted format
    test_cases = [
        # Original patterns
        "Robotaxi 5+ times",
        "Israel 7+ times",
        "Penalty or Flag 30+ times",
        "AI or Artificial Intelligence",
        "UN/United Nations",
        "Palestine",
        "TikTok",
        "Thousand/Million/Billion 3+ times",
        # New: Quoted words in questions (Microsoft format)
        'Will Microsoft say "Copilot" during earnings call?',
        'Will Microsoft say "AI / Artificial Intelligence" during earnings call?',
        'Will Microsoft say "M365 / Microsoft 365" during earnings call?',
        'Will Microsoft say "Shutdown / Shut Down" during earnings call?',
        'Will Microsoft say "OpenAI" during earnings call?',
    ]

    print("Testing criteria parser:")
    print("\n=== Original Patterns ===")
    for criteria in test_cases[:8]:
        result = parse_criteria(criteria)
        print(f"  {criteria:50} → words={result['words']}, threshold={result['threshold']}")

    print("\n=== New: Quoted Words in Questions ===")
    for criteria in test_cases[8:]:
        result = parse_criteria(criteria)
        print(f"  {criteria:70} → words={result['words']}, threshold={result['threshold']}")

    # Test detection
    print("\nTesting word detection:")
    transcript = "We talked about robotaxi twice. The robotaxi is important. AI and artificial intelligence matter."
    test_words = [
        (["robotaxi"], "robotaxi"),
        (["ai", "artificial intelligence"], "ai or artificial intelligence")
    ]

    for words, label in test_words:
        count = detect_words_in_transcript(transcript, words)
        print(f"  {label:30} → detected {count} times")
