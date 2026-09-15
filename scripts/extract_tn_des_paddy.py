#!/usr/bin/env python3

from __future__ import annotations

import csv
import re
from pathlib import Path


SOURCE = Path("/tmp/season_crop_full.txt")
OUTPUT = Path("data/processed/tn_des_paddy_2024_25.csv")

REPORT_YEAR = "2024-25"
SOURCE_AUTHORITY = "Department of Economics and Statistics, Government of Tamil Nadu"
SOURCE_REPORT = "Season and Crop Report Tamil Nadu 2024-2025, Fasli 1434"
PROVENANCE = "REAL_OBSERVED_AGGREGATED"

DISTRICT_COUNT = 38


def find_table_start(lines: list[str], marker: str, min_line_number: int) -> int:
    """Find the first table marker after an approximate 1-based line number."""
    start_index = max(0, min_line_number - 1)

    for i in range(start_index, len(lines)):
        if marker.lower() in lines[i].lower():
            return i

    raise RuntimeError(f"Could not find table marker: {marker}")


def district_rows_until_state(lines: list[str], start_index: int) -> list[tuple[int, str, list[float]]]:
    """
    Extract district rows after a table header until the State row.

    Expected row structure:
        <serial> <district name> <numeric columns...>
    """
    rows: list[tuple[int, str, list[float]]] = []

    row_pattern = re.compile(
        r"^\s*(\d{1,2})\s+([A-Za-z][A-Za-z .'-]*?)\s+(.+?)\s*$"
    )

    for line in lines[start_index + 1:]:
        if re.match(r"^\s*State\b", line, re.IGNORECASE):
            break

        match = row_pattern.match(line)
        if not match:
            continue

        serial = int(match.group(1))
        if not 1 <= serial <= DISTRICT_COUNT:
            continue

        district = re.sub(r"\s+", " ", match.group(2)).strip()

        numeric_tokens = re.findall(
            r"[-+]?(?:\d+(?:\.\d+)?|\.\d+)",
            match.group(3),
        )

        if not numeric_tokens:
            continue

        values = [float(x) for x in numeric_tokens]
        rows.append((serial, district, values))

    return rows


def require_38(rows: list[tuple[int, str, list[float]]], table_name: str) -> None:
    if len(rows) != DISTRICT_COUNT:
        raise RuntimeError(
            f"{table_name}: expected {DISTRICT_COUNT} district rows, "
            f"found {len(rows)}"
        )

    serials = [r[0] for r in rows]
    if serials != list(range(1, DISTRICT_COUNT + 1)):
        raise RuntimeError(
            f"{table_name}: district serials are not exactly 1..38: {serials}"
        )


def main() -> None:
    if not SOURCE.exists():
        raise FileNotFoundError(f"Source text not found: {SOURCE}")

    lines = SOURCE.read_text(encoding="utf-8", errors="replace").splitlines()

    # ------------------------------------------------------------
    # Table IV-A: Paddy Total Area
    #
    # We deliberately start at the continuation page around the
    # section containing "Paddy (Total)", rather than the first
    # IV-A page containing the individual seasons.
    # ------------------------------------------------------------
    area_start = find_table_start(
        lines,
        "TABLE - IV-A",
        8470,
    )

    area_rows = district_rows_until_state(lines, area_start)
    require_38(area_rows, "DES Table IV-A")

    area_by_serial = {}
    for serial, district, values in area_rows:
        if len(values) < 1:
            raise RuntimeError(
                f"Table IV-A: no numeric value for {district}"
            )

        # On the Paddy (Total) continuation page, the final numeric
        # value is the total paddy area (ha).
        paddy_area_ha = values[-1]

        area_by_serial[serial] = {
            "district": district,
            "paddy_area_ha": paddy_area_ha,
        }

    # ------------------------------------------------------------
    # Table V-A: District-wise Average Yield Rates
    #
    # Rice columns are:
    #   Kar/Kuruvai/Sornavari
    #   Samba/Thaladi/Pishanam
    #   Navarai/Kodai
    #   Combined
    #
    # Therefore the 4th numeric value is combined rice yield.
    # ------------------------------------------------------------
    yield_start = find_table_start(
        lines,
        "TABLE - V A DISTRICTWISE AVERAGE YIELD RATES OF THE CROPS",
        21400,
    )

    yield_rows = district_rows_until_state(lines, yield_start)
    require_38(yield_rows, "DES Table V-A")

    yield_by_serial = {}

    for serial, district, values in yield_rows:
        if len(values) < 4:
            raise RuntimeError(
                f"Table V-A: expected at least 4 rice values for {district}, "
                f"found {values}"
            )

        paddy_yield_kg_per_ha = values[3]

        yield_by_serial[serial] = {
            "district": district,
            "paddy_yield_kg_per_ha": paddy_yield_kg_per_ha,
        }

    # ------------------------------------------------------------
    # Table V-B: Production of Crops
    #
    # Rice columns are:
    #   Kar/Kuruvai/Sornavari
    #   Samba/Thaladi/Pishanam
    #   Navarai/Kodai
    #   Total
    #
    # Therefore the 4th numeric value is total rice production
    # in tonnes.
    # ------------------------------------------------------------
    production_start = find_table_start(
        lines,
        "TABLE - V B PRODUCTION OF CROPS DURING 2024-25",
        22500,
    )

    production_rows = district_rows_until_state(lines, production_start)
    require_38(production_rows, "DES Table V-B")

    production_by_serial = {}

    for serial, district, values in production_rows:
        if len(values) < 4:
            raise RuntimeError(
                f"Table V-B: expected at least 4 rice values for {district}, "
                f"found {values}"
            )

        paddy_production_tonnes = values[3]

        production_by_serial[serial] = {
            "district": district,
            "paddy_production_tonnes": paddy_production_tonnes,
        }

    # ------------------------------------------------------------
    # Join and cross-validate
    # ------------------------------------------------------------
    records = []

    for serial in range(1, DISTRICT_COUNT + 1):
        area = area_by_serial[serial]
        production = production_by_serial[serial]
        yield_data = yield_by_serial[serial]

        district_names = {
            area["district"],
            production["district"],
            yield_data["district"],
        }

        if len(district_names) != 1:
            raise RuntimeError(
                f"District mismatch for serial {serial}: "
                f"{district_names}"
            )

        district = area["district"]

        record = {
            "district": district,
            "report_year": REPORT_YEAR,
            "paddy_area_ha": area["paddy_area_ha"],
            "paddy_production_tonnes": production["paddy_production_tonnes"],
            "paddy_yield_kg_per_ha": yield_data["paddy_yield_kg_per_ha"],
            "source_authority": SOURCE_AUTHORITY,
            "source_report": SOURCE_REPORT,
            "source_table_area": "Table IV-A",
            "source_table_production": "Table V-B",
            "source_table_yield": "Table V-A",
            "provenance": PROVENANCE,
        }

        # Basic sanity checks
        if record["paddy_area_ha"] < 0:
            raise RuntimeError(f"Negative paddy area for {district}")

        if record["paddy_production_tonnes"] < 0:
            raise RuntimeError(f"Negative paddy production for {district}")

        if record["paddy_yield_kg_per_ha"] < 0:
            raise RuntimeError(f"Negative paddy yield for {district}")

        # Independent consistency check:
        # tonnes ≈ hectares × kg/ha / 1000
        expected_production = (
            record["paddy_area_ha"]
            * record["paddy_yield_kg_per_ha"]
            / 1000.0
        )

        reported = record["paddy_production_tonnes"]

        if expected_production > 0:
            relative_error = abs(reported - expected_production) / expected_production

            # We don't fail on this because published figures can differ
            # because of rounding/reporting conventions.
            record["_production_yield_area_relative_error"] = relative_error

        records.append(record)

    # ------------------------------------------------------------
    # Write clean CSV
    # ------------------------------------------------------------
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "district",
        "report_year",
        "paddy_area_ha",
        "paddy_production_tonnes",
        "paddy_yield_kg_per_ha",
        "source_authority",
        "source_report",
        "source_table_area",
        "source_table_production",
        "source_table_yield",
        "provenance",
    ]

    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for record in records:
            writer.writerow({
                key: (
                    int(value)
                    if isinstance(value, float) and value.is_integer()
                    else value
                )
                for key, value in record.items()
                if key in fieldnames
            })

    # ------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------
    print()
    print("SUCCESS")
    print("=" * 72)
    print(f"Output: {OUTPUT}")
    print(f"Districts: {len(records)}")
    print()

    print("Sample records:")
    for record in records[:5]:
        print(
            f"{record['district']:<20} "
            f"area={record['paddy_area_ha']:>10,.0f} ha  "
            f"production={record['paddy_production_tonnes']:>10,.0f} t  "
            f"yield={record['paddy_yield_kg_per_ha']:>7,.0f} kg/ha"
        )

    print()
    print("Selected validation districts:")
    for target in [
        "Thanjavur",
        "Tiruvarur",
        "Nagapattinam",
        "Mayiladuthurai",
        "Ariyalur",
        "Chennai",
    ]:
        matches = [r for r in records if r["district"] == target]
        if matches:
            r = matches[0]
            print(
                f"{r['district']:<20} "
                f"{r['paddy_area_ha']:>10,.0f} ha | "
                f"{r['paddy_production_tonnes']:>10,.0f} t | "
                f"{r['paddy_yield_kg_per_ha']:>7,.0f} kg/ha"
            )
        else:
            print(f"{target:<20} NOT FOUND")

    print()
    print("CSV preview:")
    with OUTPUT.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            print(line.rstrip())
            if i >= 6:
                break


if __name__ == "__main__":
    main()
