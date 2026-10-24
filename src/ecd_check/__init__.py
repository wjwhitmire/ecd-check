"""ECD Check: annular hydraulics screening with the API RP 13D (1995) power-law annulus model.

A screening tool. Not a replacement for a full hydraulics program.
"""

from .core import (
    EXAMPLE_CASE,
    InputError,
    default_sweep_rates,
    dial_from_pv_yp,
    ecd_sweep,
    evaluate,
    friction_factor,
    normalize_case,
    rheology_params,
    section_hydraulics,
    sweep_dips,
)
from .parse import parse_sections_text

__version__ = "0.1.0"

__all__ = [
    "EXAMPLE_CASE",
    "InputError",
    "default_sweep_rates",
    "dial_from_pv_yp",
    "ecd_sweep",
    "evaluate",
    "friction_factor",
    "normalize_case",
    "parse_sections_text",
    "rheology_params",
    "section_hydraulics",
    "sweep_dips",
    "__version__",
]
