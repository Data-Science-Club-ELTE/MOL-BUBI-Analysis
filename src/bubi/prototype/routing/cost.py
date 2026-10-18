"""Prototype edge weights with slope penalty for synthetic bike routing.

Conforms to Technical Design Document (Section 6.4):
- Edge cost = length plus an uphill penalty: cost = length * (1 + alpha * max(0, grade))
- Grade is signed: uphill is positive, downhill is negative
- Downhill and flat edges receive no penalty (max(0, grade) == 0)
"""

from __future__ import annotations

from typing import Any, Optional, Union


def _calculate_cost(length_m: float, grade: float, alpha: float) -> float:
    """Internal calculation of edge cost."""
    if length_m < 0.0:
        raise ValueError(f"Edge length must be non-negative, got {length_m}")
    if alpha < 0.0:
        raise ValueError(f"Slope penalty alpha must be non-negative, got {alpha}")

    # Uphill penalty only: downhill and flat edges receive no penalty
    uphill_grade = max(0.0, float(grade))
    multiplier = 1.0 + float(alpha) * uphill_grade
    return float(length_m) * multiplier


def compute_edge_weight(
    *args: Any,
    length_m: Optional[Union[float, int]] = None,
    grade: Optional[Union[float, int]] = None,
    alpha: Optional[Union[float, int]] = None,
    **kwargs: Any,
) -> float:
    """Compute the traversal cost of an edge including slope penalty.

    Supports multiple calling patterns:

    1. Keyword argument call:
       >>> compute_edge_weight(length_m=100.0, grade=0.05, alpha=10.0)
       150.0

    2. Positional numeric call:
       >>> compute_edge_weight(100.0, 0.05, 10.0)
       150.0

    3. NetworkX / graph callback convention:
       >>> compute_edge_weight(u, v, {'length_m': 100.0, 'grade': 0.05})
       150.0

    4. Dictionary call:
       >>> compute_edge_weight({'length_m': 100.0, 'grade': 0.05})
       150.0

    Parameters:
    - length_m: Edge length in meters (>= 0).
    - grade: Signed slope (rise / run). Positive for uphill, negative for downhill.
    - alpha: Non-negative multiplier for uphill grade penalty (default: 10.0).

    Returns:
    - Weighted edge cost as float.
    """
    default_alpha = 10.0 if alpha is None else float(alpha)

    # Case A: NetworkX convention compute_edge_weight(u, v, data)
    if len(args) == 3 and isinstance(args[2], dict):
        data = args[2]
        l_val = float(data.get("length_m", 1.0))
        g_val = float(data.get("grade", 0.0))
        a_val = float(data.get("alpha", default_alpha))
        return _calculate_cost(l_val, g_val, a_val)

    # Case B: Dictionary passed as first argument compute_edge_weight(data)
    if len(args) == 1 and isinstance(args[0], dict):
        data = args[0]
        l_val = float(data.get("length_m", 1.0))
        g_val = float(data.get("grade", 0.0))
        a_val = float(data.get("alpha", default_alpha))
        return _calculate_cost(l_val, g_val, a_val)

    # Case C: Positional arguments (length_m, [grade, [alpha]])
    if len(args) >= 1 and not isinstance(args[0], dict):
        l_val = float(args[0])
        g_val = float(args[1]) if len(args) >= 2 else (0.0 if grade is None else float(grade))
        a_val = float(args[2]) if len(args) >= 3 else default_alpha
        return _calculate_cost(l_val, g_val, a_val)

    # Case D: Keyword arguments
    if length_m is not None:
        l_val = float(length_m)
        g_val = 0.0 if grade is None else float(grade)
        a_val = default_alpha
        return _calculate_cost(l_val, g_val, a_val)

    raise TypeError(
        "compute_edge_weight requires length_m or edge data dictionary (either positional or keyword)."
    )
