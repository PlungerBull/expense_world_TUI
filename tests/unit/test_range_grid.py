"""`formatting.build_range_grid` — the month grid the TUI Home screen draws."""

from expense import formatting
from expense.formatting import build_range_grid

# Two months with overlapping-but-different categories: Rent only in Nov,
# Salary only in Dec, Food in both (its #bbbb combo appears only in Dec).
MONTHS = [
    {
        "month": {"year": 2025, "month": 11},
        "categories": [
            {
                "id": "cat-food",
                "name": "Food",
                "spent_home_cents": -10000,
                "unconverted_count": 0,
                "hashtag_breakdown": [
                    {"hashtag_ids": ["aaaa"], "spent_home_cents": -6000, "unconverted_count": 0},
                    {"hashtag_ids": [], "spent_home_cents": -4000, "unconverted_count": 0},
                ],
            },
            {
                "id": "cat-rent",
                "name": "Rent",
                "spent_home_cents": -200000,
                "unconverted_count": 0,
                "hashtag_breakdown": [],
            },
        ],
        "totals": {
            "inflow_home_cents": 0,
            "outflow_home_cents": 210000,
            "net_home_cents": -210000,
            "unconverted_count": 0,
        },
    },
    {
        "month": {"year": 2025, "month": 12},
        "categories": [
            {
                "id": "cat-food",
                "name": "Food",
                "spent_home_cents": -12000,
                "unconverted_count": 0,
                "hashtag_breakdown": [
                    {"hashtag_ids": ["aaaa"], "spent_home_cents": -7000, "unconverted_count": 0},
                    {"hashtag_ids": ["bbbb"], "spent_home_cents": -5000, "unconverted_count": 0},
                ],
            },
            {
                "id": "cat-salary",
                "name": "Salary",
                "spent_home_cents": 900000,
                "unconverted_count": 0,
                "hashtag_breakdown": [],
            },
        ],
        "totals": {
            "inflow_home_cents": 900000,
            "outflow_home_cents": 12000,
            "net_home_cents": 888000,
            "unconverted_count": 0,
        },
    },
]


def _cents(cells: dict) -> dict:
    """Just the amounts out of a grid row's cell dicts, for readable asserts."""
    return {label: cell["cents"] for label, cell in cells.items()}


def test_build_range_grid_merges_first_appearance_order():
    grid = build_range_grid(MONTHS)
    assert grid["labels"] == ["2025-11", "2025-12"]
    assert [row["name"] for row in grid["rows"]] == ["Food", "Rent", "Salary"]

    food, rent, salary = grid["rows"]
    # A cell carries its unconverted_count alongside the figure — `None` alone
    # cannot say whether a blank is "no activity" or "the engine refused to
    # price this".
    assert _cents(food["cells"]) == {"2025-11": -10000, "2025-12": -12000}
    assert _cents(rent["cells"]) == {"2025-11": -200000}  # no Dec activity → no cell
    assert rent["cells"].get("2025-12") is None
    assert _cents(salary["cells"]) == {"2025-12": 900000}

    # combos keep first-appearance order; #aaaa merges across both months
    assert [tuple(sub["hashtag_ids"]) for sub in food["breakdown"]] == [
        ("aaaa",),
        (),
        ("bbbb",),
    ]
    assert _cents(food["breakdown"][0]["cells"]) == {"2025-11": -6000, "2025-12": -7000}
    assert _cents(food["breakdown"][2]["cells"]) == {"2025-12": -5000}

    assert _cents(grid["totals"]["net"]) == {"2025-11": -210000, "2025-12": 888000}
    assert all(cell["unconverted"] == 0 for cell in grid["totals"]["net"].values())
    # inflow/outflow ride alongside net off the same month payload
    assert set(grid["totals"]) == set(formatting.TOTALS_KEYS)


def test_build_range_grid_carries_the_unconverted_count_and_drops_empty_rows():
    """Three states: a figure, a real zero (no activity), and an unpriceable month."""
    months = [
        {
            "month": {"year": 2026, "month": 1},
            "categories": [
                {
                    "id": "cat-food",
                    "name": "Food",
                    "spent_home_cents": -10000,
                    "unconverted_count": 0,
                    "hashtag_breakdown": [],
                },
                {
                    "id": "cat-gifts",
                    "name": "Gifts",
                    "spent_home_cents": 0,
                    "unconverted_count": 0,
                    "hashtag_breakdown": [],
                },
            ],
            "totals": {"net_home_cents": -10000, "unconverted_count": 0},
        },
        {
            "month": {"year": 2026, "month": 2},
            "categories": [
                {
                    "id": "cat-food",
                    "name": "Food",
                    "spent_home_cents": None,
                    "unconverted_count": 3,
                    "hashtag_breakdown": [],
                },
                {
                    "id": "cat-gifts",
                    "name": "Gifts",
                    "spent_home_cents": 0,
                    "unconverted_count": 0,
                    "hashtag_breakdown": [],
                },
            ],
            "totals": {"net_home_cents": None, "unconverted_count": 3},
        },
    ]
    grid = build_range_grid(months)

    # Gifts spent nothing in either month, so it is not drawn at all.
    assert [row["name"] for row in grid["rows"]] == ["Food"]

    feb = grid["rows"][0]["cells"]["2026-02"]
    assert feb == {"cents": None, "unconverted": 3}
    assert not formatting.cell_is_empty(feb)  # unpriceable is NOT empty
    assert formatting.format_aggregate(feb["cents"], feb["unconverted"]) == "3 unrated"

    # ...and a genuinely empty cell is empty (Home draws the no-activity mark), not 0.00.
    assert formatting.cell_is_empty(None)
    assert formatting.cell_is_empty({"cents": 0, "unconverted": 0})
    assert grid["totals"]["net"]["2026-02"] == {"cents": None, "unconverted": 3}
    # all three totals share the month's one count, so they fail together
    assert grid["totals"]["inflow"]["2026-02"]["unconverted"] == 3
    assert grid["totals"]["outflow"]["2026-02"]["unconverted"] == 3
