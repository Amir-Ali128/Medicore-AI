# MediCore Native Lab Extensions v1

This module completes the deterministic lab layer without moving clinical interpretation into C++.

## Native responsibilities

- raw reference text parsing (`<`, `<=`, `>`, `>=`, ranges, qualitative references, titers)
- analyte-aware deterministic unit conversion for explicitly registered unit pairs
- conservative plausibility/data-quality flags (never silent value correction)
- fractional-year demographic reference selection for pediatric/neonatal ranges
- Python bindings through `medicore_lab_ext`

## Safety invariants

- Unknown unit conversions fail closed and preserve the original value.
- Plausibility rules only flag or reject structurally impossible values; they never guess a corrected result.
- Fractional ages are not rounded to whole years.
- Database access and AI/clinical interpretation remain in Python.
