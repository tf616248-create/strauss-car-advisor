"""Loads the challenge data files exactly as delivered (read-only).

- data/strauss-rules.json      challenge rules (budgets, tracks, tax tables)
- data/strauss-data.xlsx       catalog, occupations, sample employees, reference results
- data/vehicle-values-2026.csv Tax Authority value-of-use file
- config/calc-assumptions.json details used by the reference sheet but not in the rules file
- config/column-map.json       Hebrew headers -> code field names

Everything is loaded once at startup and kept in memory.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple, Optional

import openpyxl


class VehicleKey(NamedTuple):
    """Full Tax Authority key. A None part acts as a wildcard in VehicleIndex.find."""

    tax_year: Optional[int]
    registration_year: Optional[int]
    vehicle_type_code: Optional[int]
    manufacturer_code: Optional[str]
    model_code: Optional[str]


class AmbiguousVehicleKey(Exception):
    pass


class VehicleIndex:
    """Two in-memory indexes over the CSV: by full key and by commercial name."""

    def __init__(self, records: list[dict]):
        self.records = records
        self._by_key: dict[VehicleKey, list[dict]] = {}
        for rec in records:
            self._by_key.setdefault(self._key_of(rec), []).append(rec)
        years = {r["taxYear"] for r in records}
        self.tax_year = years.pop() if len(years) == 1 else None

    @staticmethod
    def _key_of(rec: dict) -> VehicleKey:
        return VehicleKey(
            rec["taxYear"],
            rec["registrationYear"],
            rec["vehicleTypeCode"],
            rec["manufacturerCode"],
            rec["modelCode"],
        )

    def get(self, key: VehicleKey) -> Optional[dict]:
        """Exact lookup by the full key. None if absent; error if not unique."""
        hits = self._by_key.get(key, [])
        if not hits:
            return None
        if len({h["valueOfUse"] for h in hits}) > 1:
            raise AmbiguousVehicleKey(key)
        return hits[0]

    def find(self, key: VehicleKey) -> list[dict]:
        """Lookup where None parts of the key match anything."""
        if all(part is not None for part in key):
            return list(self._by_key.get(key, []))
        return [
            rec
            for k, recs in self._by_key.items()
            if all(want is None or want == got for want, got in zip(key, k))
            for rec in recs
        ]

    def search_name(self, query: str, registration_year: Optional[int] = None) -> list[dict]:
        """Candidates whose commercial name contains the query (case-insensitive)."""
        q = query.strip().upper()
        return [
            r
            for r in self.records
            if q in r["name"].upper()
            and (registration_year is None or r["registrationYear"] == registration_year)
        ]


@dataclass
class Data:
    rules: dict
    assumptions: dict
    column_map: dict
    catalog: dict[str, dict]
    occupations: dict[str, dict]
    employees: dict[str, dict]
    reference: dict[str, dict]
    vehicles: VehicleIndex
    _catalog_by_name: dict[str, dict] = field(default_factory=dict)

    def __post_init__(self):
        self._catalog_by_name = {c["name"].strip().upper(): c for c in self.catalog.values()}

    def find_car(self, name_or_id: str) -> Optional[dict]:
        key = name_or_id.strip().upper()
        return self.catalog.get(key) or self._catalog_by_name.get(key)

    @property
    def excel_values(self) -> dict:
        return self.column_map["excel"]


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_sheet(wb, spec: dict, yes_value: str) -> list[dict]:
    ws = wb[spec["sheet"]]
    rows = ws.iter_rows(values_only=True)
    headers = [h.strip() if isinstance(h, str) else h for h in next(rows)]
    mapping = spec["columns"]
    missing = [h for h in mapping if h not in headers]
    if missing:
        raise ValueError(f"Sheet '{spec['sheet']}' is missing columns: {missing}")
    out = []
    for row in rows:
        if all(c is None for c in row):
            continue
        rec = {}
        for header, value in zip(headers, row):
            if header in mapping:
                rec[mapping[header]] = value.strip() if isinstance(value, str) else value
        out.append(rec)
    return out


def _yes(value, yes_value: str) -> bool:
    return value == yes_value


def _load_excel(path: Path, cmap: dict):
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    excel = cmap["excel"]
    yes = excel["yesValue"]
    catalog = {r["id"]: r for r in _read_sheet(wb, excel["catalog"], yes)}
    occupations = {}
    for r in _read_sheet(wb, excel["occupations"], yes):
        r["carMandatory"] = _yes(r["carMandatory"], yes)
        r["waiverAllowed"] = _yes(r["waiverAllowed"], yes)
        occupations[r["name"]] = r
    employees = {r["id"]: r for r in _read_sheet(wb, excel["employees"], yes)}
    reference = {r["id"]: r for r in _read_sheet(wb, excel["reference"], yes)}
    return catalog, occupations, employees, reference


def _to_int(value: str) -> Optional[int]:
    value = value.strip()
    return int(float(value)) if value else None


def _load_csv(path: Path, cmap: dict, drive_field: dict) -> VehicleIndex:
    """drive_field comes from strauss-rules.json valueOfUse.driveField.

    The CSV header for the drive column reads "1-חשמלי.2-היברידי.3-פלג-אין", but the
    actual values are 0 petrol, 1 hybrid, 2 plug-in, 3 electric. We never parse the
    header; the code->name meaning comes only from the rules file.
    """
    spec = cmap["csv"]
    idx = spec["columnIndex"]
    records = []
    with path.open(encoding=spec["encoding"], newline="") as f:
        reader = csv.reader(f)
        next(reader)  # header (its drive description is misleading - see column-map)
        for row in reader:
            records.append(
                {
                    "taxYear": _to_int(row[idx["taxYear"]]),
                    "registrationYear": _to_int(row[idx["registrationYear"]]),
                    "vehicleTypeCode": _to_int(row[idx["vehicleTypeCode"]]),
                    "manufacturerCode": row[idx["manufacturerCode"]].strip(),
                    "manufacturer": row[idx["manufacturer"]].strip(),
                    "modelCode": row[idx["modelCode"]].strip(),
                    "modelDescription": row[idx["modelDescription"]].strip(),
                    "fuelType": _to_int(row[idx["fuelType"]]),
                    "name": row[idx["name"]].strip(),
                    "drive": _to_int(row[idx["drive"]]),
                    "driveName": drive_field.get(row[idx["drive"]].strip()),
                    "listPrice": _to_int(row[idx["listPrice"]]),
                    "valueOfUse": _to_int(row[idx["valueOfUse"]]),
                }
            )
    return VehicleIndex(records)


def load_all(base_dir: Path) -> Data:
    base_dir = Path(base_dir)
    cmap = _read_json(base_dir / "config" / "column-map.json")
    rules = _read_json(base_dir / "data" / "strauss-rules.json")
    catalog, occupations, employees, reference = _load_excel(
        base_dir / "data" / "strauss-data.xlsx", cmap
    )
    return Data(
        rules=rules,
        assumptions=_read_json(base_dir / "config" / "calc-assumptions.json"),
        column_map=cmap,
        catalog=catalog,
        occupations=occupations,
        employees=employees,
        reference=reference,
        vehicles=_load_csv(
            base_dir / "data" / "vehicle-values-2026.csv", cmap, rules["valueOfUse"]["driveField"]
        ),
    )
