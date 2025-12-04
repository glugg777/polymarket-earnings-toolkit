#!/usr/bin/env python3
"""
Liquidity Scenario Simulator

Simulates how limit orders perform under different liquidity arrival patterns.
Tests whether our orders get filled or skipped when market conditions change.

Usage:
    python scripts/simulate_liquidity_scenarios.py \
        --market "Server" \
        --fair-value 1.00 \
        --initial-bid 0.12 \
        --initial-ask 0.99 \
        --scenarios all

    python scripts/simulate_liquidity_scenarios.py \
        --market "Server" \
        --fair-value 1.00 \
        --initial-bid 0.12 \
        --initial-ask 0.99 \
        --scenario market_makers
"""

import argparse
from dataclasses import dataclass
from typing import List, Tuple, Optional
from enum import Enum


class OrderStatus(Enum):
    """Status of our limit order."""
    PENDING = "Pending"
    FILLED = "Filled"
    SKIPPED = "Skipped"
    PARTIAL = "Partial"


@dataclass
class OrderBook:
    """Represents the state of the order book at a point in time."""
    best_bid: float
    best_ask: float
    mid_price: float
    spread: float
    spread_pct: float

    def __str__(self):
        return (
            f"Bid: ${self.best_bid:.2f} | "
            f"Ask: ${self.best_ask:.2f} | "
            f"Mid: ${self.mid_price:.2f} | "
            f"Spread: {self.spread_pct:.1%}"
        )


@dataclass
class LimitOrder:
    """Our limit order."""
    price: float
    size: float
    side: str  # "BUY" or "SELL"

    def __str__(self):
        return f"{self.side} {self.size} shares @ ${self.price:.2f}"


@dataclass
class SimulationResult:
    """Result of a liquidity scenario simulation."""
    scenario_name: str
    initial_book: OrderBook
    final_book: OrderBook
    our_limit: LimitOrder
    status: OrderStatus
    fills: List[Tuple[float, float]]  # (price, quantity) pairs
    total_filled: float
    avg_fill_price: float
    profit_per_share: float
    total_profit: float
    notes: str

    def __str__(self):
        status_symbol = {
            OrderStatus.FILLED: "✅",
            OrderStatus.SKIPPED: "❌",
            OrderStatus.PARTIAL: "🟡",
            OrderStatus.PENDING: "⏳"
        }[self.status]

        return f"""
{'='*80}
{status_symbol} SCENARIO: {self.scenario_name}
{'='*80}

INITIAL STATE (Low Liquidity):
    {self.initial_book}

OUR LIMIT ORDER:
    {self.our_limit}

FINAL STATE (After Liquidity Arrives):
    {self.final_book}

EXECUTION RESULT:
    Status: {self.status.value}
    Filled: {self.total_filled}/{self.our_limit.size} shares ({self.total_filled/self.our_limit.size*100:.0f}%)
    Avg Fill Price: ${self.avg_fill_price:.2f}
    Profit per Share: ${self.profit_per_share:.2f}
    Total Profit: ${self.total_profit:.2f}

NOTES:
    {self.notes}
{'='*80}
"""


class LiquiditySimulator:
    """Simulates different liquidity arrival scenarios."""

    def __init__(
        self,
        market_name: str,
        fair_value: float,
        initial_bid: float,
        initial_ask: float,
        position_size: float = 100.0
    ):
        self.market_name = market_name
        self.fair_value = fair_value
        self.initial_bid = initial_bid
        self.initial_ask = initial_ask
        self.position_size = position_size

        # Calculate our limit order price using the same logic as calculate_edges.py
        self.our_limit_price = self._calculate_limit_price()

    def _calculate_limit_price(self) -> float:
        """
        Calculate our limit price using the enhanced hybrid strategy.
        Same logic as calculate_edges.py
        """
        max_spread_cross = 0.03
        spread = self.initial_ask - self.initial_bid

        # Safety target (5¢ below fair value)
        fair_value_target = self.fair_value - 0.05

        # Maker target (2¢ above best bid)
        maker_target = self.initial_bid + 0.02

        # Check if we should cross the spread
        if spread <= max_spread_cross:
            # Hybrid: consider taker side too
            taker_target = self.initial_ask - 0.02
            target = min(fair_value_target, maker_target, taker_target)
        else:
            # Maker-only: spread too wide
            target = min(fair_value_target, maker_target)

        return target

    def _create_order_book(self, bid: float, ask: float) -> OrderBook:
        """Create an OrderBook object from bid/ask prices."""
        mid = (bid + ask) / 2
        spread = ask - bid
        spread_pct = spread / mid if mid > 0 else 0
        return OrderBook(bid, ask, mid, spread, spread_pct)

    def simulate_scenario(
        self,
        scenario_name: str,
        new_bid: float,
        new_ask: float,
        fill_logic: str
    ) -> SimulationResult:
        """
        Simulate a liquidity scenario.

        Args:
            scenario_name: Name of the scenario
            new_bid: New best bid after liquidity arrives
            new_ask: New best ask after liquidity arrives
            fill_logic: How to determine if our order fills:
                - "below_new_bid": Filled if our_limit < new_bid (we're below market)
                - "above_new_ask": Skipped if our_limit < new_ask (market moved away)
                - "seller_walks_down": Filled if seller dumps through our level
                - "partial": Partially filled if between new_bid and old_bid
        """
        initial_book = self._create_order_book(self.initial_bid, self.initial_ask)
        final_book = self._create_order_book(new_bid, new_ask)

        our_limit = LimitOrder(
            price=self.our_limit_price,
            size=self.position_size,
            side="BUY"
        )

        # Determine fill status based on logic
        fills = []
        status = OrderStatus.PENDING
        notes = ""

        if fill_logic == "below_new_bid":
            # Market moved up, our order is below new bid → skipped
            if our_limit.price < new_bid:
                status = OrderStatus.SKIPPED
                notes = (
                    f"Market makers tightened spread. New bid (${new_bid:.2f}) is above "
                    f"our limit (${our_limit.price:.2f}). Our order never fills."
                )
            else:
                status = OrderStatus.FILLED
                fills = [(our_limit.price, our_limit.size)]
                notes = f"Our limit (${our_limit.price:.2f}) is at or above new bid (${new_bid:.2f}). Filled."

        elif fill_logic == "above_new_ask":
            # Market collapsed, our order is above new ask → filled (bad sign)
            if our_limit.price > new_ask:
                status = OrderStatus.FILLED
                fills = [(our_limit.price, our_limit.size)]
                notes = (
                    f"⚠️ ADVERSE SELECTION: Market collapsed to ${new_ask:.2f} ask, but we bought at "
                    f"${our_limit.price:.2f}. Only filled because we're on the wrong side."
                )
            else:
                status = OrderStatus.SKIPPED
                notes = f"Market fell but not to our level. Our limit (${our_limit.price:.2f}) < ask (${new_ask:.2f})."

        elif fill_logic == "seller_walks_down":
            # Seller dumps shares, walking down the book to our level
            status = OrderStatus.FILLED
            fills = [(our_limit.price, our_limit.size)]
            notes = (
                f"Smart money seller dumped shares through the book. "
                f"We're filled at ${our_limit.price:.2f}. Hope our analysis is right!"
            )

        elif fill_logic == "partial":
            # Gradual liquidity arrival, we get partial fill
            # Assume 30% chance of fill based on where we are in queue
            fill_pct = 0.3
            fill_qty = our_limit.size * fill_pct
            fills = [(our_limit.price, fill_qty)]
            status = OrderStatus.PARTIAL
            notes = (
                f"Gradual liquidity arrival. Multiple bids appear between ${self.initial_bid:.2f} and "
                f"${new_bid:.2f}. We get partial fill ({fill_pct*100:.0f}%) at ${our_limit.price:.2f}."
            )

        # Calculate profit
        total_filled = sum(qty for _, qty in fills)
        avg_fill_price = (
            sum(price * qty for price, qty in fills) / total_filled
            if total_filled > 0 else 0
        )
        profit_per_share = self.fair_value - avg_fill_price if total_filled > 0 else 0
        total_profit = profit_per_share * total_filled

        return SimulationResult(
            scenario_name=scenario_name,
            initial_book=initial_book,
            final_book=final_book,
            our_limit=our_limit,
            status=status,
            fills=fills,
            total_filled=total_filled,
            avg_fill_price=avg_fill_price,
            profit_per_share=profit_per_share,
            total_profit=total_profit,
            notes=notes
        )

    def run_all_scenarios(self) -> List[SimulationResult]:
        """Run all predefined scenarios."""
        scenarios = [
            {
                "name": "Scenario 1: Market Makers Arrive",
                "new_bid": 0.72,
                "new_ask": 0.82,
                "fill_logic": "below_new_bid",
            },
            {
                "name": "Scenario 2: Smart Money Sells",
                "new_bid": 0.10,
                "new_ask": 0.15,
                "fill_logic": "seller_walks_down",
            },
            {
                "name": "Scenario 3: Retail Hype",
                "new_bid": 0.85,
                "new_ask": 0.92,
                "fill_logic": "below_new_bid",
            },
            {
                "name": "Scenario 4: Gradual Fill-In",
                "new_bid": 0.20,
                "new_ask": 0.40,
                "fill_logic": "partial",
            },
            {
                "name": "Scenario 5: Insider Dump",
                "new_bid": 0.01,
                "new_ask": 0.05,
                "fill_logic": "above_new_ask",
            },
        ]

        results = []
        for scenario in scenarios:
            result = self.simulate_scenario(
                scenario_name=scenario["name"],
                new_bid=scenario["new_bid"],
                new_ask=scenario["new_ask"],
                fill_logic=scenario["fill_logic"]
            )
            results.append(result)

        return results


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Simulate liquidity scenarios for limit orders',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run all scenarios for Server market
    python scripts/simulate_liquidity_scenarios.py \\
        --market "Server" \\
        --fair-value 1.00 \\
        --initial-bid 0.12 \\
        --initial-ask 0.99

    # Run specific scenario
    python scripts/simulate_liquidity_scenarios.py \\
        --market "Server" \\
        --fair-value 1.00 \\
        --initial-bid 0.12 \\
        --initial-ask 0.99 \\
        --scenario market_makers \\
        --new-bid 0.72 \\
        --new-ask 0.82

    # Test with different position size
    python scripts/simulate_liquidity_scenarios.py \\
        --market "Cybersecurity" \\
        --fair-value 0.0 \\
        --initial-bid 0.10 \\
        --initial-ask 0.96 \\
        --position-size 500
        """
    )

    parser.add_argument(
        '--market',
        required=True,
        help='Market name (e.g., "Server", "Cybersecurity")'
    )

    parser.add_argument(
        '--fair-value',
        type=float,
        required=True,
        help='Our estimated fair value (0.0 to 1.0)'
    )

    parser.add_argument(
        '--initial-bid',
        type=float,
        required=True,
        help='Current best bid (before liquidity arrives)'
    )

    parser.add_argument(
        '--initial-ask',
        type=float,
        required=True,
        help='Current best ask (before liquidity arrives)'
    )

    parser.add_argument(
        '--position-size',
        type=float,
        default=100.0,
        help='Number of shares to buy (default: 100)'
    )

    parser.add_argument(
        '--scenarios',
        choices=['all', 'market_makers', 'smart_sell', 'hype', 'gradual', 'insider'],
        default='all',
        help='Which scenario(s) to run (default: all)'
    )

    # For custom scenarios
    parser.add_argument(
        '--new-bid',
        type=float,
        help='New best bid after liquidity arrives (for custom scenario)'
    )

    parser.add_argument(
        '--new-ask',
        type=float,
        help='New best ask after liquidity arrives (for custom scenario)'
    )

    return parser.parse_args()


def main():
    """Main execution function."""
    args = parse_arguments()

    print("="*80)
    print("LIQUIDITY SCENARIO SIMULATOR")
    print("="*80)
    print(f"Market: {args.market}")
    print(f"Fair Value: ${args.fair_value:.2f}")
    print(f"Initial Bid: ${args.initial_bid:.2f}")
    print(f"Initial Ask: ${args.initial_ask:.2f}")
    print(f"Position Size: {args.position_size:.0f} shares")
    print()

    # Create simulator
    simulator = LiquiditySimulator(
        market_name=args.market,
        fair_value=args.fair_value,
        initial_bid=args.initial_bid,
        initial_ask=args.initial_ask,
        position_size=args.position_size
    )

    print(f"Calculated Limit Price: ${simulator.our_limit_price:.2f}")
    print(f"  (using enhanced hybrid strategy with 3% max spread cross)")
    print()

    # Run scenarios
    if args.scenarios == 'all':
        results = simulator.run_all_scenarios()
        for result in results:
            print(result)
    else:
        # Run specific scenario or custom
        if args.new_bid is not None and args.new_ask is not None:
            # Custom scenario
            result = simulator.simulate_scenario(
                scenario_name=f"Custom: {args.scenarios}",
                new_bid=args.new_bid,
                new_ask=args.new_ask,
                fill_logic="below_new_bid"  # Default logic
            )
            print(result)
        else:
            print("ERROR: For specific scenarios, provide --new-bid and --new-ask")
            return 1

    # Summary statistics
    if args.scenarios == 'all':
        print("\n" + "="*80)
        print("SUMMARY STATISTICS")
        print("="*80)

        filled_count = sum(1 for r in results if r.status == OrderStatus.FILLED)
        skipped_count = sum(1 for r in results if r.status == OrderStatus.SKIPPED)
        partial_count = sum(1 for r in results if r.status == OrderStatus.PARTIAL)

        avg_profit = sum(r.total_profit for r in results if r.total_filled > 0) / max(1, len([r for r in results if r.total_filled > 0]))

        print(f"Total Scenarios: {len(results)}")
        print(f"  Filled: {filled_count} ({filled_count/len(results)*100:.0f}%)")
        print(f"  Skipped: {skipped_count} ({skipped_count/len(results)*100:.0f}%)")
        print(f"  Partial: {partial_count} ({partial_count/len(results)*100:.0f}%)")
        print()
        print(f"Average Profit (when filled): ${avg_profit:.2f}")
        print()
        print("KEY INSIGHT:")
        print(f"  Your order has a {(filled_count + partial_count)/len(results)*100:.0f}% chance of at least partial fill")
        print(f"  But a {skipped_count/len(results)*100:.0f}% chance of being completely skipped")
        print()


if __name__ == '__main__':
    main()
