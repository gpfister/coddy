"""Cost formatting utilities for UI presentation."""

from __future__ import annotations

import math


def round_high_thousandth(amount: float) -> float:
    """Rounds a currency amount up to the nearest 1/1000th (high mil/thousandth).

    Args:
        amount: Non-negative monetary amount.

    Returns:
        Rounded amount to 3 decimal places, rounded towards positive infinity.
    """
    if amount <= 0.0:
        return 0.0
    # Use 9 decimal precision guard against floating point artifacts
    return math.ceil(round(amount, 9) * 1000.0) / 1000.0


# Backward compatibility alias
round_high_cent = round_high_thousandth


def format_cost_eur(amount: float) -> str:
    """Formats an amount in EUR rounded to the high 1/1000th of the currency.

    Args:
        amount: Non-negative monetary amount in EUR.

    Returns:
        String formatted as '€X.XXX'.
    """
    rounded = round_high_thousandth(amount)
    return f"€{rounded:.3f}"
