#!/usr/bin/env python3

from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path


RAW_DIR = Path("data/raw/tamil_nadu/agmarknet")
OUTPUT = Path("data/processed/tn_agmarknet_paddy_arrivals_2025.csv")

EXPECTED_HEADER = [
    "State/UT",
    "District",
    "Market",
    "Commodity Group",
    "Commodity",
    "Arrival Quantity",
    "Arrival Unit",
    "Arrival Date",
]

# Canonical district names based on the DES 2024-25 district naming.
# Only explicit spelling variants observed in AGMARKNET are mapped here.
DISTRICT_MAP = {
    "Thiruchirappalli": "Tiruchirapalli",
    "Thirunelveli": "Tirunelveli",
    "Thiruvannamalai": "Tiruvannamalai",
    "Thiruvellore": "Tiruvallur",
    "Thiruvarur": "Tiruvarur",
    "Tuticorin": "Thoothukudi",
    "Nagercoil (Kannyiakumari)": "Kanniyakumari",
}

MONTH_PATTERN = re.compile(
    r"(\d{2})-(\d{2})-(\d{4}).*?(\d{2})-(\d{2})-(\d{4})",
    re.IGNORECASE,
)


def normalize_number(value: str) -> float:
    """
    Convert AGMARKNET numeric strings such as:
      0.47
      1,113.11
      3,135.30
    into floats.
    """
    value = value.strip().replace(",", "")

    if not value:
        raise ValueError("empty numeric value")

    return float(value)


def normalize_date(value: str) -> str:
    """
    AGMARKNET date format:
        DD-MM-YYYY

    Output:
        YYYY-MM-DD
    """
    value = value.strip()

    day, month, year = value.split("-")
    return f"{year}-{month}-{day}"


def canonical_district(source_district: str) -> str:
    district = re.sub(r"\s+", " ", source_district.strip())
    return DISTRICT_MAP.get(district, district)


def read_agmarknet_file(path: Path) -> list[dict[str, str]]:
    """
    Read an AGMARKNET CSV export.

    The current export has:
      row 1 = report title
      row 2 = actual header
      rows 3+ = observations
    """
    records: list[dict[str, str]] = []

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)

        try:
            title_row = next(reader)
            header = next(reader)
        except StopIteration:
            raise RuntimeError(f"Empty AGMARKNET file: {path}")

        # Normalize header whitespace.
        header = [h.strip() for h in header]

        # Current portal has "Arrival Quantity".
        # Older/alternate exports may use "ArrivalQuantity".
        header = [
            "Arrival Quantity" if h.replace(" ", "").lower() == "arrivalquantity" else h
            for h in header
        ]

        if header != EXPECTED_HEADER:
            raise RuntimeError(
                f"\nUnexpected AGMARKNET header in {path.name}\n"
                f"Expected: {EXPECTED_HEADER}\n"
                f"Actual:   {header}"
            )

        for line_number, row in enumerate(reader, start=3):
            if not any(cell.strip() for cell in row):
                continue

            if len(row) != len(header):
                raise RuntimeError(
                    f"{path.name}: malformed row at CSV line {line_number}: "
                    f"expected {len(header)} fields, got {len(row)}"
                )

            records.append(
                dict(zip(header, [cell.strip() for cell in row]))
            )

    return records


def main() -> None:
    files = sorted(RAW_DIR.glob("*.csv"))

    if not files:
        raise SystemExit(f"No AGMARKNET CSV files found in {RAW_DIR}")

    print(f"Found {len(files)} raw AGMARKNET file(s).")

    all_records: list[dict[str, str]] = []
    source_counts: Counter[str] = Counter()

    for path in files:
        print(f"Reading: {path.name}")
        rows = read_agmarknet_file(path)

        for row in rows:
            source_counts[path.name] += 1

            commodity = row["Commodity"].strip()

            # Keep only the paddy commodity selected in our exports.
            if commodity.lower() != "paddy(common)":
                continue

            arrival_unit = row["Arrival Unit"].strip()

            if arrival_unit != "Metric Tonnes":
                raise RuntimeError(
                    f"{path.name}: unexpected arrival unit "
                    f"{arrival_unit!r}"
                )

            quantity = normalize_number(row["Arrival Quantity"])

            if quantity < 0:
                raise RuntimeError(
                    f"{path.name}: negative arrival quantity: {quantity}"
                )

            source_district = row["District"].strip()
            canonical = canonical_district(source_district)

            date_iso = normalize_date(row["Arrival Date"])

            # Ensure requested year is 2025.
            if not date_iso.startswith("2025-"):
                raise RuntimeError(
                    f"{path.name}: non-2025 observation found: {date_iso}"
                )

            all_records.append(
                {
                    "observation_date": date_iso,
                    "state": row["State/UT"].strip(),
                    "district_source": source_district,
                    "district_canonical": canonical,
                    "market": row["Market"].strip(),
                    "commodity": commodity,
                    "arrival_quantity_mt": f"{quantity:.2f}",
                    "source_authority": (
                        "Directorate of Marketing and Inspection, "
                        "Government of India"
                    ),
                    "source_system": "AGMARKNET",
                    "provenance": "REAL_OBSERVED",
                    "source_file": path.name,
                }
            )

    # ------------------------------------------------------------
    # Deduplicate exact repeated observations.
    # ------------------------------------------------------------
    key_fields = [
        "observation_date",
        "state",
        "district_source",
        "district_canonical",
        "market",
        "commodity",
        "arrival_quantity_mt",
    ]

    unique: dict[tuple[str, ...], dict[str, str]] = {}

    for row in all_records:
        key = tuple(row[k] for k in key_fields)
        unique[key] = row

    deduplicated = list(unique.values())

    # ------------------------------------------------------------
    # Sort deterministically.
    # ------------------------------------------------------------
    deduplicated.sort(
        key=lambda r: (
            r["observation_date"],
            r["district_canonical"],
            r["market"],
        )
    )

    # ------------------------------------------------------------
    # Check canonical geography coverage.
    # ------------------------------------------------------------
    unknown_variants = sorted(
        {
            r["district_source"]
            for r in deduplicated
            if r["district_source"] != r["district_canonical"]
            or r["district_source"] not in DISTRICT_MAP
        }
    )

    # ------------------------------------------------------------
    # Write normalized dataset.
    # ------------------------------------------------------------
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "observation_date",
        "state",
        "district_source",
        "district_canonical",
        "market",
        "commodity",
        "arrival_quantity_mt",
        "source_authority",
        "source_system",
        "provenance",
        "source_file",
    ]

    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(deduplicated)

    # ------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------
    quantities = [
        float(r["arrival_quantity_mt"])
        for r in deduplicated
    ]

    dates = [
        r["observation_date"]
        for r in deduplicated
    ]

    districts = {
        r["district_canonical"]
        for r in deduplicated
    }

    markets = {
        r["market"]
        for r in deduplicated
    }

    print()
    print("=" * 72)
    print("AGMARKNET NORMALIZATION SUCCESS")
    print("=" * 72)
    print(f"Raw files:              {len(files)}")
    print(f"Raw paddy observations: {len(all_records)}")
    print(f"Unique observations:    {len(deduplicated)}")
    print(f"Duplicate removals:     {len(all_records) - len(deduplicated)}")
    print(f"Districts:              {len(districts)}")
    print(f"Markets:                {len(markets)}")
    print(f"Date range:             {min(dates)} -> {max(dates)}")
    print(f"Total arrivals:         {sum(quantities):,.2f} MT")
    print(f"Min arrival:            {min(quantities):,.2f} MT")
    print(f"Max arrival:            {max(quantities):,.2f} MT")
    print(f"Output:                 {OUTPUT}")

    print()
    print("SOURCE FILE COUNTS:")
    for name, count in source_counts.items():
        print(f"  {name}: {count}")

    print()
    print("DISTRICT NAMES OBSERVED:")
    for district in sorted(districts):
        print(f"  {district}")

    print()
    print("SOURCE -> CANONICAL MAPPINGS USED:")
    for source, canonical in sorted(DISTRICT_MAP.items()):
        print(f"  {source} -> {canonical}")

    print()
    print("FIRST 10 NORMALIZED RECORDS:")
    for row in deduplicated[:10]:
        print(
            f"{row['observation_date']} | "
            f"{row['district_canonical']} | "
            f"{row['market']} | "
            f"{row['arrival_quantity_mt']} MT"
        )


if __name__ == "__main__":
    main()
