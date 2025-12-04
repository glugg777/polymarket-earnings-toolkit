"""
Transcript Analysis Module

This module provides utilities for analyzing historical transcripts and counting
word mentions for prediction market evaluation.

Core functionality ported from the Counter feature's marketParser.ts to enable
batch processing of historical earnings call transcripts.
"""

import re
import glob
from pathlib import Path
from typing import List, Dict


def detect_words_in_transcript(transcript: str, words: List[str]) -> int:
    """
    Count total mentions of target words in a transcript.

    This is a direct port of the TypeScript detectWordsInTranscript() function
    from src/utils/marketParser.ts (lines 73-107). It uses the same word boundary
    matching logic to ensure accurate counting.

    Args:
        transcript: The full text content to search through
        words: List of words/phrases to detect (e.g., ["copilot", "openai"])

    Returns:
        Total count of all word mentions found in the transcript

    Examples:
        >>> detect_words_in_transcript("Microsoft Copilot is great. Copilot helps.", ["copilot"])
        2

        >>> detect_words_in_transcript("AI and Artificial Intelligence", ["ai", "artificial intelligence"])
        2

    Implementation Details:
        - Uses word boundaries (\\b) to match whole words only
        - Case-insensitive matching
        - Handles multi-word phrases
        - Counts all occurrences of all target words

    Why Word Boundaries Matter:
        - "\\bcopilot\\b" matches "Copilot" in "Microsoft Copilot"
        - "\\bcopilot\\b" does NOT match in "MyCopilotApp" (no word boundary)
        - This prevents false positives from partial word matches
    """
    if not transcript or not words:
        return 0

    total_count = 0

    for word in words:
        # Escape special regex characters in the word
        # This allows us to search for things like "M365" or "AI/ML" literally
        escaped_word = re.escape(word)

        # Create regex pattern with word boundaries
        # \\b = word boundary (space, punctuation, start/end of string)
        # re.IGNORECASE = case-insensitive matching
        #
        # Example patterns:
        #   "copilot" → "\\bcopilot\\b"
        #   "artificial intelligence" → "\\bartificial intelligence\\b"
        #   "M365" → "\\bM365\\b"
        pattern = rf'\b{escaped_word}\b'

        # Find all matches in the transcript
        matches = re.findall(pattern, transcript, re.IGNORECASE)

        # Add to total count
        total_count += len(matches)

    return total_count


def extract_quarter_from_filename(filename: str) -> str:
    """
    Extract quarter label from transcript filename.

    This function parses filenames to identify the fiscal quarter and year,
    enabling proper result aggregation by time period.

    Args:
        filename: The filename or full path (e.g., "Microsoft_Q1_2025_Transcript.md")

    Returns:
        Quarter label in format "Q{quarter}_{year}" (e.g., "Q1_2025")
        Returns empty string if no valid quarter pattern found

    Examples:
        >>> extract_quarter_from_filename("Microsoft_Q1_2025_Transcript.md")
        'Q1_2025'

        >>> extract_quarter_from_filename("transcripts/microsoft/Tesla_Q3_2024_Transcript_PERFECT.md")
        'Q3_2024'

        >>> extract_quarter_from_filename("SBUX_Q2_2025.md")
        'Q2_2025'

        >>> extract_quarter_from_filename("invalid_filename.md")
        ''

    Implementation Details:
        - Uses regex pattern: Q(\\d)_(\\d{4})
        - Matches quarter numbers 1-4 and 4-digit years
        - Works with full paths or just filenames
        - Case-insensitive matching (Q1 or q1 both work)

    Why This Format:
        - Standard financial reporting format (Q1, Q2, Q3, Q4)
        - Year included for multi-year analysis
        - Underscore separator prevents ambiguity
    """
    # Extract just the filename if a full path was provided
    # Example: "transcripts/microsoft/Tesla_Q3_2024.md" → "Tesla_Q3_2024.md"
    filename_only = Path(filename).name

    # Regex pattern to match quarter format: Q{1-4}_{YYYY}
    # (\d) captures single digit for quarter (1-4)
    # (\d{4}) captures 4-digit year
    pattern = r'Q(\d)_(\d{4})'

    # Search for the pattern in the filename
    match = re.search(pattern, filename_only, re.IGNORECASE)

    if match:
        quarter = match.group(1)  # Extract quarter number
        year = match.group(2)     # Extract year
        return f"Q{quarter}_{year}"

    # No valid quarter pattern found
    return ""


def load_transcripts(glob_pattern: str) -> Dict[str, str]:
    """
    Load all transcript files matching a glob pattern.

    This function discovers transcript files on disk, extracts their quarter labels,
    and loads their content into memory for batch processing.

    Args:
        glob_pattern: File pattern to match (e.g., "transcripts/microsoft/*.md")

    Returns:
        Dictionary mapping quarter labels to transcript content
        Example: {"Q1_2025": "# Microsoft Q1...", "Q2_2025": "# Microsoft Q2..."}

    Raises:
        FileNotFoundError: If no files match the glob pattern

    Examples:
        >>> transcripts = load_transcripts("transcripts/microsoft/*.md")
        >>> "Q1_2025" in transcripts
        True

        >>> transcripts = load_transcripts("transcripts/tesla/Tesla_*.md")
        >>> len(transcripts)
        4

    Implementation Details:
        - Uses Python's glob module for file discovery
        - Extracts quarter label from each filename
        - Reads entire file content into memory
        - Skips files without valid quarter labels
        - Handles UTF-8 encoding for special characters

    Why Dictionary Structure:
        - Fast lookup by quarter (O(1) access)
        - Natural mapping for result aggregation
        - Easy to iterate and display results chronologically

    Error Handling:
        - Raises FileNotFoundError if no files found (fail fast)
        - Prints warning for files with invalid quarter labels
        - Continues loading other files if one fails
    """
    # Find all files matching the pattern
    # Example: "transcripts/microsoft/*.md" finds all .md files in that directory
    files = glob.glob(glob_pattern)

    # Fail fast if no files found
    if not files:
        raise FileNotFoundError(f"No files found matching pattern: {glob_pattern}")

    transcripts = {}

    for file_path in files:
        # Extract quarter label from filename
        quarter = extract_quarter_from_filename(file_path)

        if not quarter:
            # Skip files that don't match expected naming convention
            print(f"Warning: Could not extract quarter from filename: {file_path}")
            continue

        try:
            # Read the entire transcript file
            # Using UTF-8 encoding to handle special characters (em dashes, etc.)
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Store in dictionary with quarter as key
            transcripts[quarter] = content

            # Debug output to confirm successful load
            print(f"Loaded transcript: {quarter} from {Path(file_path).name}")

        except Exception as e:
            # Log error but continue processing other files
            print(f"Error reading {file_path}: {str(e)}")
            continue

    return transcripts


def analyze_market_historical(market: Dict, transcripts: Dict[str, str]) -> Dict:
    """
    Analyze one market across all historical transcripts to compute statistics.

    This is the "brain" of Phase 2. It combines word detection (Step 1) and transcript
    loading (Step 2) to produce quarter-by-quarter analysis with statistical summaries.

    The output feeds directly into Phase 4 (Edge Calculator) to determine if market
    prices reflect historical patterns.

    Args:
        market: Market definition with word criteria
            Example: {
                "market_question": "Will Microsoft say \"Copilot\" during earnings call?",
                "words": ["copilot"],
                "threshold": 1,
                "market_id": "647109"
            }

        transcripts: Dictionary of quarter labels to transcript content
            Example: {
                "Q1_2025": "# Microsoft Q1 2025...",
                "Q2_2025": "# Microsoft Q2 2025...",
                ...
            }

    Returns:
        Analysis results with quarter-by-quarter data and statistics
        Example: {
            "market_question": "Will Microsoft say \"Copilot\" during earnings call?",
            "threshold": 1,
            "quarters": {
                "Q1_2025": {"count": 65, "met_threshold": true},
                "Q2_2025": {"count": 48, "met_threshold": true},
                ...
            },
            "mention_rate": 1.0,           # fraction of quarters that met threshold
            "avg_count": 44.75,            # mean count across all quarters
            "historical_probability": 1.0  # same as mention_rate (for Phase 4)
        }

    Implementation Logic:
        1. Extract word criteria from market definition
        2. For each quarter in transcripts:
           - Call detect_words_in_transcript() to count mentions
           - Check if count meets threshold requirement
           - Store results in quarters dict
        3. Calculate statistics:
           - mention_rate: what % of quarters met threshold
           - avg_count: average mentions per quarter
           - historical_probability: same as mention_rate

    Examples:
        >>> market = {
        ...     "market_question": "Will Microsoft say \"Copilot\" during earnings call?",
        ...     "words": ["copilot"],
        ...     "threshold": 1
        ... }
        >>> transcripts = {
        ...     "Q1_2025": "Microsoft Copilot mentioned 65 times...",
        ...     "Q2_2025": "Copilot features improved..."
        ... }
        >>> result = analyze_market_historical(market, transcripts)
        >>> result["mention_rate"]  # If both quarters met threshold
        1.0

    Why This Function Matters:
        - Bridges detection logic with statistical analysis
        - Produces structured output for edge calculation
        - Enables comparison of historical patterns vs market prices
        - Identifies mispriced markets based on historical data

    Pattern Reference:
        This follows the pure functional approach from Steps 1-2, with clear
        inputs/outputs and no side effects. Results are JSON-serializable for
        easy persistence and reporting.
    """
    # Extract word criteria from market definition
    # These fields are required in the market dict
    words = market.get("words", [])
    threshold = market.get("threshold", 1)
    word_description = market.get("market_question", "Unknown market")

    # Initialize results structure
    quarters_analysis = {}
    counts = []  # Track all counts for avg calculation

    # Process each quarter's transcript
    for quarter, transcript in transcripts.items():
        # Use Step 1's word detection logic to count mentions
        count = detect_words_in_transcript(transcript, words)

        # Check if this quarter met the threshold requirement
        met_threshold = count >= threshold

        # Store quarter-level results
        quarters_analysis[quarter] = {
            "count": count,
            "met_threshold": met_threshold
        }

        # Track count for average calculation
        counts.append(count)

    # Calculate statistics across all quarters
    total_quarters = len(transcripts)

    if total_quarters == 0:
        # Edge case: no transcripts provided
        mention_rate = 0.0
        avg_count = 0.0
    else:
        # Calculate mention rate: what fraction of quarters met threshold
        # Example: 4 quarters met threshold out of 4 total → 1.0 (100%)
        quarters_met = sum(1 for q in quarters_analysis.values() if q["met_threshold"])
        mention_rate = quarters_met / total_quarters

        # Calculate average count across all quarters
        # Example: [65, 48, 25, 41] → 44.75
        avg_count = sum(counts) / total_quarters

    # Return structured analysis result
    return {
        "market_question": word_description,  # Full question text (e.g., "Will Microsoft say 'Copilot'...")
        "threshold": threshold,
        "quarters": quarters_analysis,
        "mention_rate": mention_rate,
        "avg_count": avg_count,
        "historical_probability": mention_rate  # Same as mention_rate for Phase 4
    }
