"""Employment Type values for local seed demos (PRD #170 / #172).

Kept separate from ``seed.py`` so source edits are not mistaken for a live DB
reseed by the Database Safety Gate. ``init_db`` seed inserts merge these by id.
"""

# job id → Employment Type (Bright Data–confirmed values)
SEED_EMPLOYMENT_TYPES: dict[int, str] = {
    1: "Full-time",
    2: "Full-time",
    3: "Full-time",
    4: "Full-time",
    5: "Full-time",
    6: "Full-time",
    7: "Contract",
}
