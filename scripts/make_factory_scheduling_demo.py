#!/usr/bin/env python3
"""Create linked synthetic factory scheduling CSVs for the web demo."""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

from make_scheduling_mockup import DATA

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "samples/web-demo/factory-scheduling"
LOT_FIELDS = ["lot_id", "product", "operation", "quantity_wafers", "due_time", "priority", "recipe_id"]
EQUIPMENT_FIELDS = ["lot_id", "equipment_id", "fit_status", "equipment_state", "process_minutes", "setup_minutes"]
RESOURCE_FIELDS = ["lot_id", "equipment_id", "resource_id", "resource_value", "unit", "resource_state", "shared"]
SPEC_FIELDS = ["lot_id", "equipment_id", "resource_id", "spec_name", "required_min", "required_max", "required_value", "actual_numeric", "actual_value", "unit", "passed"]


def lot_rows(count: int) -> list[dict]:
    base = DATA["lot"]
    rows = []
    hours, minutes = (int(part) for part in base["due"].split(":"))
    for index in range(count):
        due_minutes = (hours * 60 + minutes + index * 17) % (24 * 60)
        rows.append({
            "lot_id": base["id"] if index == 0 else f"LOT-DEMO-{index + 1:04d}",
            "product": base["product"] if index == 0 else ("AX8" if index % 3 == 0 else base["product"]),
            "operation": base["operation"] if index == 0 else ("Etch-04" if index % 2 else base["operation"]),
            "quantity_wafers": base["quantity"] if index == 0 else 900 + (index * 37) % 701,
            "due_time": base["due"] if index == 0 else f"{due_minutes // 60:02d}:{due_minutes % 60:02d}",
            "priority": base["priority"] if index == 0 else ("HIGH", "NORMAL", "LOW")[index % 3],
            "recipe_id": base["recipe"] if index == 0 else f"R-ETCH-{index % 4 + 1:02d}",
        })
    return rows


def numeric_parts(value: str) -> list[float]:
    return [float(item) for item in re.findall(r"\d+(?:\.\d+)?", value)]


def resource_observation(resource_id: str, value: str, lot_index: int, machine_index: int,
                         vary_flow: bool = True) -> tuple[str, str, str]:
    if re.fullmatch(r"(?:AM|PM)\s*\d{1,2}:\d{2}", value, re.IGNORECASE):
        return "", "", value
    if resource_id == "GAS-CF4":
        base = float(numeric_parts(value)[0])
        observed = base if lot_index == 0 or not vary_flow else 28 + (lot_index * 7 + machine_index * 5) % 29
        return str(observed), "slm", "Ready" if observed >= 40 else "보충 필요"
    numbers = numeric_parts(value)
    if numbers:
        unit = "%" if "%" in value else "people" if "명" in value else ""
        return str(numbers[0]), unit, "Ready"
    return "", "", value


def spec_rows_for(lot: dict, machine: dict, lot_index: int, machine_index: int) -> list[dict]:
    rows = []
    for resource_id, name, required, actual, _ in machine["specs"]:
        bounds = numeric_parts(required)
        base_actual = numeric_parts(actual)
        actual_numeric = ""
        actual_value = actual
        required_min = str(bounds[0]) if bounds else ""
        required_max = str(bounds[1]) if len(bounds) > 1 else ""
        required_value = "" if bounds else required
        unit = "℃" if "℃" in required else "mTorr" if "mTorr" in required else "slm" if "slm" in required else ""
        if name == "유량":
            actual_numeric = resource_observation(resource_id, actual + " slm", lot_index, machine_index)[0]
            actual_value = actual_numeric
        elif bounds:
            delta = 0 if lot_index == 0 else ((lot_index + machine_index * 2) % 5) - 2
            actual_numeric = str(base_actual[0] + delta)
            actual_value = actual_numeric
        else:
            actual_value = actual
        if bounds:
            passed = float(actual_numeric) >= bounds[0] and (len(bounds) < 2 or float(actual_numeric) <= bounds[1])
        else:
            passed = actual_value == required_value
        rows.append({
            "lot_id": lot["lot_id"], "equipment_id": machine["id"], "resource_id": resource_id,
            "spec_name": name, "required_min": required_min, "required_max": required_max,
            "required_value": required_value, "actual_numeric": actual_numeric,
            "actual_value": actual_value, "unit": unit, "passed": str(passed).lower(),
        })
    return rows


def build_tables(count: int) -> dict[str, list[dict]]:
    lots = lot_rows(count)
    equipment, resources, specs = [], [], []
    for lot_index, lot in enumerate(lots):
        for machine_index, machine in enumerate(DATA["equipment"]):
            machine_specs = spec_rows_for(lot, machine, lot_index, machine_index)
            failed = any(row["passed"] == "false" for row in machine_specs)
            state = ("CF4 보충 필요" if failed else "Setup 필요" if machine["setup"] > 0 else "Ready")
            equipment.append({
                "lot_id": lot["lot_id"], "equipment_id": machine["id"],
                "fit_status": "조건부" if failed else "가능", "equipment_state": state,
                "process_minutes": max(1, machine["process"] + (0 if lot_index == 0 else (lot_index + machine_index) % 7 - 3)),
                "setup_minutes": max(0, machine["setup"] + (0 if lot_index == 0 else (lot_index * 3 + machine_index) % 5 - 2)),
            })
            specs.extend(machine_specs)
            for resource_id, value, shared in machine["resources"]:
                gas_spec = None
                if resource_id == "GAS-CF4":
                    gas_spec = next((row for row in machine_specs if row["spec_name"] == "유량"), None)
                    if gas_spec:
                        value = gas_spec["actual_numeric"]
                observed, unit, state = resource_observation(
                    resource_id, value, lot_index, machine_index, vary_flow=gas_spec is not None,
                )
                resources.append({
                    "lot_id": lot["lot_id"], "equipment_id": machine["id"], "resource_id": resource_id,
                    "resource_value": observed, "unit": unit, "resource_state": state, "shared": str(shared).lower(),
                })
    return {"lots.csv": lots, "equipment_options.csv": equipment,
            "equipment_resources.csv": resources, "resource_specs.csv": specs}


def validate(tables: dict[str, list[dict]], count: int) -> None:
    lots = tables["lots.csv"]
    equipment = tables["equipment_options.csv"]
    resources = tables["equipment_resources.csv"]
    specs = tables["resource_specs.csv"]
    lot_ids = {row["lot_id"] for row in lots}
    equipment_keys = {(row["lot_id"], row["equipment_id"]) for row in equipment}
    resource_keys = {(row["lot_id"], row["equipment_id"], row["resource_id"]) for row in resources}
    spec_keys = {(row["lot_id"], row["equipment_id"], row["resource_id"], row["spec_name"])
                 for row in specs}
    expected_equipment = {machine["id"] for machine in DATA["equipment"]}
    expected_resources = {item[0] for machine in DATA["equipment"] for item in machine["resources"]}
    expected_resource_pairs = {(machine["id"], item[0])
                               for machine in DATA["equipment"] for item in machine["resources"]}
    if len(lot_ids) != count or len(lots) != count or len(equipment_keys) != len(equipment):
        raise ValueError("중복 Lot 또는 설비 후보 키가 있습니다")
    if {row["equipment_id"] for row in equipment} != expected_equipment:
        raise ValueError("기준 데이터에 없는 설비 ID가 있습니다")
    if {row["resource_id"] for row in resources} != expected_resources:
        raise ValueError("기준 데이터에 없는 Resource ID가 있습니다")
    if any((row["equipment_id"], row["resource_id"]) not in expected_resource_pairs
           for row in resources):
        raise ValueError("Resource와 설비 조합이 기준 데이터와 다릅니다")
    if len(equipment) != count * len(expected_equipment):
        raise ValueError("Lot별 설비 후보 수가 기준 데이터와 다릅니다")
    if len(resources) != count * sum(len(m["resources"]) for m in DATA["equipment"]):
        raise ValueError("Lot별 Resource 관계 수가 기준 데이터와 다릅니다")
    if len(specs) != count * sum(len(m["specs"]) for m in DATA["equipment"]):
        raise ValueError("Lot별 Spec 수가 기준 데이터와 다릅니다")
    if len(resource_keys) != len(resources):
        raise ValueError("중복 Resource 관계 키가 있습니다")
    if len(spec_keys) != len(specs):
        raise ValueError("중복 Spec 키가 있습니다")
    expected_specs = {(machine["id"], spec[0], spec[1])
                      for machine in DATA["equipment"] for spec in machine["specs"]}
    if any((row["equipment_id"], row["resource_id"], row["spec_name"]) not in expected_specs
           for row in specs):
        raise ValueError("Spec과 Resource 조합이 기준 데이터와 다릅니다")
    if any(row["lot_id"] not in lot_ids for row in equipment + resources + specs):
        raise ValueError("존재하지 않는 Lot을 참조합니다")
    if any((row["lot_id"], row["equipment_id"]) not in equipment_keys for row in resources + specs):
        raise ValueError("존재하지 않는 설비 후보를 참조합니다")
    if any((row["lot_id"], row["equipment_id"], row["resource_id"]) not in resource_keys for row in specs):
        raise ValueError("Spec이 존재하지 않는 Resource 관계를 참조합니다")
    validate_spec_values(specs)
    validate_shared_resources(resources, lot_ids)
    if len(expected_equipment) < 2:
        raise ValueError("여러 설비 후보가 필요합니다")
    if any(len(rows) < 4 for rows in tables.values()):
        raise ValueError("웹 시각화에 필요한 최소 행 수를 충족하지 못했습니다")


def validate_spec_values(specs: list[dict]) -> None:
    for row in specs:
        if row["required_min"] or row["required_max"]:
            actual = float(row["actual_numeric"])
            passed = actual >= float(row["required_min"] or "-inf") and actual <= float(row["required_max"] or "inf")
        else:
            passed = row["actual_value"] == row["required_value"]
        if str(passed).lower() != row["passed"]:
            raise ValueError("Spec의 충족 판정이 요구/실측값과 일치하지 않습니다")


def validate_shared_resources(resources: list[dict], lot_ids: set[str]) -> None:
    by_lot: dict[str, dict[str, set[str]]] = {}
    for row in resources:
        by_lot.setdefault(row["lot_id"], {}).setdefault(row["resource_id"], set()).add(row["equipment_id"])
    if any(len(by_lot[lot_id].get("GAS-CF4", set())) < 3
           or len(by_lot[lot_id].get("TOOL-KIT-7", set())) < 2 for lot_id in lot_ids):
        raise ValueError("공유 GAS-CF4/TOOL-KIT-7이 기준 설비 간 재사용되지 않습니다")


def write_tables(output: Path, tables: dict[str, list[dict]]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    fields = {"lots.csv": LOT_FIELDS, "equipment_options.csv": EQUIPMENT_FIELDS,
              "equipment_resources.csv": RESOURCE_FIELDS, "resource_specs.csv": SPEC_FIELDS}
    for filename, rows in tables.items():
        with (output / filename).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields[filename], extrasaction="raise")
            writer.writeheader()
            writer.writerows(rows)
        print(f"{filename}: {len(rows):,}행 × {len(fields[filename])}열")


def main() -> None:
    parser = argparse.ArgumentParser(description="합성 Scheduling 관계 CSV 생성")
    parser.add_argument("--lots", type=int, default=120, help="생성할 합성 Lot 수 (최소 4)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="CSV 출력 폴더")
    args = parser.parse_args()
    if args.lots < 4:
        parser.error("--lots는 최소 4여야 합니다")
    tables = build_tables(args.lots)
    validate(tables, args.lots)
    write_tables(args.out, tables)
    print(f"완료: {args.out.resolve()}")


if __name__ == "__main__":
    main()
