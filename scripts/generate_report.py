#!/usr/bin/env python3
"""
Phase 5: Report Generator
Generates human-readable Markdown reports from edge calculation output.

This script transforms the structured JSON output from Phase 4 (edges.json) into
a professional investment report with:
- Executive summary with conviction breakdown
- Market context and risk profile
- Detailed recommendations by conviction tier
- Portfolio allocation summary table
- Methodology documentation
- Report metadata footer

Usage:
    python scripts/generate_report.py \
        --edges data/test_microsoft/edges.json \
        --output reports/microsoft_q1_2025.md \
        --company "Microsoft" \
        --quarter "Q1 2025"

Output:
    Creates a formatted Markdown report at the specified path with:
    - STRONG conviction recommendations (>20% edge)
    - MODERATE conviction recommendations (10-20% edge)
    - Markets to pass (<10% edge)
    - Portfolio summary table
    - Methodology and metadata sections
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

from jinja2 import Environment, FileSystemLoader, TemplateNotFound


def parse_arguments() -> argparse.Namespace:
    """
    Parse command line arguments.

    Returns:
        Parsed arguments namespace

    CLI Arguments:
        --edges: Path to edges.json (Phase 4 output)
        --output: Path for output Markdown report file (required, user controls naming)
        --company: Company name for report header (optional, defaults to "Unknown")
        --quarter: Quarter identifier for report header (optional, defaults to "Unknown")
    """
    parser = argparse.ArgumentParser(
        description='Generate Markdown report from edge calculation output',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Generate report with company/quarter context
    python scripts/generate_report.py \\
        --edges data/test_microsoft/edges.json \\
        --output reports/microsoft_q1_2025.md \\
        --company "Microsoft" \\
        --quarter "Q1 2025"

    # Generate report with automatic naming
    python scripts/generate_report.py \\
        --edges data/test_microsoft/edges.json \\
        --output reports/earnings_report_$(date +%Y%m%d).md

    # Minimal usage (company/quarter will show as "Unknown")
    python scripts/generate_report.py \\
        --edges data/test_microsoft/edges.json \\
        --output reports/report.md
        """
    )

    parser.add_argument(
        '--edges',
        required=True,
        help='Path to edges.json from Phase 4 (edge calculator output)'
    )

    parser.add_argument(
        '--output',
        required=True,
        help='Output path for Markdown report file (e.g., reports/microsoft_q1_2025.md)'
    )

    parser.add_argument(
        '--company',
        default='Unknown',
        help='Company name for report header (default: "Unknown")'
    )

    parser.add_argument(
        '--quarter',
        default='Unknown',
        help='Quarter identifier for report header (default: "Unknown")'
    )

    return parser.parse_args()


def validate_arguments(args: argparse.Namespace) -> None:
    """
    Validate parsed arguments.

    Args:
        args: Parsed arguments namespace

    Raises:
        FileNotFoundError: If edges file doesn't exist
        ValueError: If output path is invalid

    Validations:
        - edges file must exist
        - output must have .md extension
    """
    # Validate edges file exists
    edges_path = Path(args.edges)
    if not edges_path.exists():
        raise FileNotFoundError(f"edges file not found: {args.edges}")

    # Validate output path extension
    output_path = Path(args.output)
    if output_path.suffix.lower() != '.md':
        raise ValueError(
            f"output file must have .md extension, got: {args.output}"
        )


def load_edges_file(file_path: str) -> Dict[str, Any]:
    """
    Load and parse edges.json file with error handling.

    Args:
        file_path: Path to edges.json file

    Returns:
        Parsed edges data as dictionary

    Raises:
        ValueError: If JSON is invalid or missing required fields
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in edges file: {e}")

    return data


def validate_edges_data(data: Dict[str, Any]) -> None:
    """
    Validate edges.json data structure.

    Args:
        data: Edges JSON data from Phase 4

    Raises:
        KeyError: If required fields are missing
        ValueError: If data structure is invalid
    """
    # Check top-level structure
    required_top_level = ['metadata', 'recommendations']
    for field in required_top_level:
        if field not in data:
            raise KeyError(f"edges data missing required field: '{field}'")

    # Check metadata structure
    metadata = data['metadata']
    required_metadata = ['generated_at', 'historical_data', 'markets_data',
                         'news_data', 'configuration', 'allocation', 'summary']
    for field in required_metadata:
        if field not in metadata:
            raise KeyError(f"metadata missing required field: '{field}'")

    # Check recommendations structure
    recommendations = data['recommendations']
    if 'all' not in recommendations:
        raise KeyError("recommendations missing 'all' field")

    if not isinstance(recommendations['all'], list):
        raise ValueError("recommendations['all'] must be a list")


def calculate_template_variables(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate derived variables needed for template rendering.

    This function computes summary statistics and aggregations from the raw
    edges.json data to populate the template.

    Args:
        data: Validated edges.json data

    Returns:
        Dictionary of template variables including:
        - Conviction tier breakdowns (strong/moderate/pass)
        - Allocation totals and averages
        - Edge statistics (highest, average, etc.)
        - Spread analysis
        - Historical context
    """
    metadata = data['metadata']
    recommendations = data['recommendations']

    # Extract conviction tiers
    all_recs = recommendations['all']
    strong_conviction = [r for r in all_recs if r['conviction'] == 'STRONG']
    moderate_conviction = [r for r in all_recs if r['conviction'] == 'MODERATE']
    pass_recommendations = [r for r in all_recs if r['conviction'] == 'PASS']

    # Calculate allocation totals
    strong_total_allocation = sum(r['position_size'] for r in strong_conviction)
    moderate_total_allocation = sum(r['position_size'] for r in moderate_conviction)

    # Calculate average positions
    strong_avg_position = (
        strong_total_allocation / len(strong_conviction)
        if strong_conviction else 0.0
    )
    moderate_avg_position = (
        moderate_total_allocation / len(moderate_conviction)
        if moderate_conviction else 0.0
    )

    # Calculate average edges by tier
    strong_avg_edge = (
        sum(r['abs_edge_pct'] for r in strong_conviction) / len(strong_conviction)
        if strong_conviction else 0.0
    )
    moderate_avg_edge = (
        sum(r['abs_edge_pct'] for r in moderate_conviction) / len(moderate_conviction)
        if moderate_conviction else 0.0
    )
    pass_avg_edge = (
        sum(r['abs_edge_pct'] for r in pass_recommendations) / len(pass_recommendations)
        if pass_recommendations else 0.0
    )

    # Calculate overall average edge (active positions only)
    active_recs = strong_conviction + moderate_conviction
    avg_active_edge = (
        sum(r['edge_pct'] for r in active_recs) / len(active_recs)
        if active_recs else 0.0
    )

    # Calculate overall average edge (all markets)
    overall_avg_edge = (
        sum(r['edge_pct'] for r in all_recs) / len(all_recs)
        if all_recs else 0.0
    )

    # Find highest edge
    highest_edge = max((r['abs_edge_pct'] for r in all_recs), default=0.0)
    highest_edge_market = next(
        (r['market_question'] for r in all_recs if r['abs_edge_pct'] == highest_edge),
        "None"
    )

    # Calculate average spread
    avg_spread = (
        sum(r.get('spread', 0.0) for r in all_recs) / len(all_recs)
        if all_recs else 0.0
    )

    # Extract historical context (number of quarters analyzed)
    # This information comes from historical.json metadata
    # For now, use a placeholder - can be enhanced to read from historical.json
    historical_quarters = "N/A"

    # Try to extract from first recommendation's rationale
    if all_recs:
        first_rationale = all_recs[0].get('rationale', {}).get('historical', '')
        # Parse "across N quarters" from rationale string
        import re
        match = re.search(r'across (\d+) quarters?', first_rationale)
        if match:
            historical_quarters = match.group(1)

    return {
        # Conviction tier data
        'strong_conviction': strong_conviction,
        'moderate_conviction': moderate_conviction,
        'pass_recommendations': pass_recommendations,

        # Allocation totals
        'strong_total_allocation': strong_total_allocation,
        'moderate_total_allocation': moderate_total_allocation,

        # Average positions
        'strong_avg_position': strong_avg_position,
        'moderate_avg_position': moderate_avg_position,

        # Average edges
        'strong_avg_edge': strong_avg_edge,
        'moderate_avg_edge': moderate_avg_edge,
        'pass_avg_edge': pass_avg_edge,
        'avg_active_edge': avg_active_edge,
        'overall_avg_edge': overall_avg_edge,

        # Risk metrics
        'highest_edge': highest_edge,
        'highest_edge_market': highest_edge_market,
        'avg_spread': avg_spread,

        # Context
        'historical_quarters': historical_quarters,
    }


def render_template(
    template_path: Path,
    data: Dict[str, Any],
    template_vars: Dict[str, Any],
    company: str,
    quarter: str
) -> str:
    """
    Render Jinja2 template with data and calculated variables.

    Args:
        template_path: Path to templates directory
        data: Raw edges.json data
        template_vars: Calculated template variables
        company: Company name for header
        quarter: Quarter identifier for header

    Returns:
        Rendered Markdown content as string

    Raises:
        TemplateNotFound: If template file doesn't exist
    """
    # Set up Jinja2 environment
    env = Environment(
        loader=FileSystemLoader(template_path),
        trim_blocks=True,
        lstrip_blocks=True
    )

    # Load template
    try:
        template = env.get_template('report.md.j2')
    except TemplateNotFound:
        raise TemplateNotFound(
            f"Template not found: {template_path / 'report.md.j2'}"
        )

    # Combine all template context
    context = {
        # Raw data from edges.json
        'metadata': data['metadata'],

        # Calculated variables
        **template_vars,

        # User-provided context
        'company_name': company,
        'quarter': quarter,
    }

    # Render template
    return template.render(**context)


def write_report(output_path: Path, content: str) -> None:
    """
    Write rendered report content to file.

    Args:
        output_path: Path to output Markdown file
        content: Rendered Markdown content

    Creates parent directories if they don't exist.
    """
    # Create parent directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write report
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)


def main():
    """Main execution function."""
    try:
        # Parse and validate arguments
        args = parse_arguments()

        print("=" * 60)
        print("PHASE 5: REPORT GENERATOR")
        print("=" * 60)
        print(f"Edges Data: {args.edges}")
        print(f"Output: {args.output}")
        print(f"Company: {args.company}")
        print(f"Quarter: {args.quarter}")
        print()

        # Validate arguments
        validate_arguments(args)
        print("✓ Arguments validated\n")

        # Step 2: Load and validate edges.json
        print("Loading edges data...")
        edges_data = load_edges_file(args.edges)
        validate_edges_data(edges_data)

        total_markets = len(edges_data['recommendations']['all'])
        print(f"✓ Loaded {total_markets} market recommendations")
        print(f"  STRONG: {edges_data['metadata']['summary']['strong_conviction']}")
        print(f"  MODERATE: {edges_data['metadata']['summary']['moderate_conviction']}")
        print(f"  PASS: {edges_data['metadata']['summary']['pass']}")
        print()

        # Step 3: Calculate template variables
        print("Calculating template variables...")
        template_vars = calculate_template_variables(edges_data)

        print(f"✓ Calculated summary statistics")
        print(f"  Highest edge: {template_vars['highest_edge']:+.1f}%")
        print(f"  Avg active edge: {template_vars['avg_active_edge']:+.1f}%")
        print(f"  Avg spread: {template_vars['avg_spread']:.1%}")
        print()

        # Step 4: Render template
        print("Rendering report template...")

        # Find template directory (relative to this script)
        script_dir = Path(__file__).parent
        template_dir = script_dir.parent / 'templates'

        if not template_dir.exists():
            raise FileNotFoundError(
                f"Templates directory not found: {template_dir}"
            )

        rendered_content = render_template(
            template_dir,
            edges_data,
            template_vars,
            args.company,
            args.quarter
        )

        print(f"✓ Template rendered successfully")
        print(f"  Content length: {len(rendered_content):,} characters")
        print()

        # Step 5: Write report
        print("Writing report to disk...")
        output_path = Path(args.output)
        write_report(output_path, rendered_content)

        print(f"✓ Report written to {args.output}")
        print(f"  File size: {output_path.stat().st_size:,} bytes")
        print()

        print("✓ Phase 5 complete!")
        print(f"\nReport available at: {args.output}")

    except FileNotFoundError as e:
        print(f"❌ ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    except ValueError as e:
        print(f"❌ ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    except TemplateNotFound as e:
        print(f"❌ ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    except Exception as e:
        print(f"❌ UNEXPECTED ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
