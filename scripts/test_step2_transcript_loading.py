#!/usr/bin/env python3
"""
Test Step 2: Transcript Loading Functions

Tests the extract_quarter_from_filename() and load_transcripts() functions
to validate they correctly parse filenames and load transcript files.
"""

import sys
from pathlib import Path

# Add lib directory to path
sys.path.insert(0, str(Path(__file__).parent / 'lib'))

from transcript_analyzer import extract_quarter_from_filename, load_transcripts


def test_extract_quarter_from_filename():
    """Test quarter extraction from various filename formats."""
    print("=" * 60)
    print("TEST 1: extract_quarter_from_filename()")
    print("=" * 60)

    test_cases = [
        ("Microsoft_Q1_2025_Transcript.md", "Q1_2025"),
        ("transcripts/microsoft/Microsoft_Q2_2025_Transcript.md", "Q2_2025"),
        ("Tesla_Q3_2024_Transcript_PERFECT.md", "Q3_2024"),
        ("SBUX_Q4_2025.md", "Q4_2025"),
        ("/absolute/path/Apple_Q1_2024.md", "Q1_2024"),
        ("invalid_filename.md", ""),
        ("no_quarter_here.txt", ""),
        ("Q5_2025.md", "Q5_2025"),  # Invalid quarter number but pattern matches
    ]

    passed = 0
    failed = 0

    for filename, expected in test_cases:
        result = extract_quarter_from_filename(filename)
        status = "✓ PASS" if result == expected else "✗ FAIL"

        if result == expected:
            passed += 1
        else:
            failed += 1

        print(f"{status}: extract_quarter_from_filename('{filename}')")
        print(f"  Expected: '{expected}'")
        print(f"  Got:      '{result}'")
        print()

    print(f"Results: {passed} passed, {failed} failed")
    print()
    return failed == 0


def test_load_transcripts():
    """Test loading Microsoft transcripts."""
    print("=" * 60)
    print("TEST 2: load_transcripts()")
    print("=" * 60)

    # Construct path relative to script location
    script_dir = Path(__file__).parent.parent
    pattern = str(script_dir / "transcripts" / "microsoft" / "*.md")

    print(f"Loading transcripts with pattern: {pattern}")
    print()

    try:
        transcripts = load_transcripts(pattern)

        print(f"Successfully loaded {len(transcripts)} transcripts:")
        print()

        # Expected quarters for Microsoft 2025
        expected_quarters = ["Q1_2025", "Q2_2025", "Q3_2025", "Q4_2025"]

        for quarter in sorted(transcripts.keys()):
            content = transcripts[quarter]
            content_preview = content[:100].replace('\n', ' ')
            print(f"  {quarter}:")
            print(f"    Length: {len(content):,} characters")
            print(f"    Preview: {content_preview}...")
            print()

        # Validate all expected quarters present
        missing = [q for q in expected_quarters if q not in transcripts]
        if missing:
            print(f"✗ FAIL: Missing expected quarters: {missing}")
            return False

        # Validate content is not empty
        for quarter, content in transcripts.items():
            if not content or len(content) < 100:
                print(f"✗ FAIL: {quarter} has insufficient content ({len(content)} chars)")
                return False

        print("✓ PASS: All transcripts loaded successfully")
        return True

    except FileNotFoundError as e:
        print(f"✗ FAIL: {e}")
        return False
    except Exception as e:
        print(f"✗ FAIL: Unexpected error: {e}")
        return False


def test_invalid_pattern():
    """Test error handling for invalid glob pattern."""
    print("=" * 60)
    print("TEST 3: Error Handling - Invalid Pattern")
    print("=" * 60)

    try:
        load_transcripts("nonexistent/path/*.md")
        print("✗ FAIL: Should have raised FileNotFoundError")
        return False
    except FileNotFoundError as e:
        print(f"✓ PASS: Correctly raised FileNotFoundError: {e}")
        return True


if __name__ == "__main__":
    print("\n🧪 Testing Step 2: Transcript Loading Functions\n")

    results = []

    # Run all tests
    results.append(("Quarter Extraction", test_extract_quarter_from_filename()))
    print()
    results.append(("Load Transcripts", test_load_transcripts()))
    print()
    results.append(("Error Handling", test_invalid_pattern()))
    print()

    # Summary
    print("=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")

    print()
    print(f"Overall: {passed}/{total} test groups passed")

    if passed == total:
        print("\n✅ All tests passed! Step 2 is complete.")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed. Please review the output above.")
        sys.exit(1)
