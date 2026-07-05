"""Excel parser/importer for GLAME seller shift schedules.

The operational ЕО workbook contains a sheet named `График`. Rows have seller
names in column B, positions in column C, and day numbers from column D onward.
Only pure numeric marks count as worked shifts/hours; absence markers (`в`, `о`,
`с`) and suffix marks (`11с`) are intentionally skipped, matching the KPI
business rule documented for GLAME.
"""
from __future__ import annotations

import base64
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, Iterable, List, Optional, Tuple

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
RELS_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"

RUSSIAN_MONTHS = {
    "январь": 1,
    "января": 1,
    "февраль": 2,
    "февраля": 2,
    "март": 3,
    "марта": 3,
    "апрель": 4,
    "апреля": 4,
    "май": 5,
    "мая": 5,
    "июнь": 6,
    "июня": 6,
    "июль": 7,
    "июля": 7,
    "август": 8,
    "августа": 8,
    "сентябрь": 9,
    "сентября": 9,
    "октябрь": 10,
    "октября": 10,
    "ноябрь": 11,
    "ноября": 11,
    "декабрь": 12,
    "декабря": 12,
}


def _column_number(cell_ref: str) -> int:
    letters = re.match(r"([A-Z]+)", cell_ref or "")
    if not letters:
        return 0
    number = 0
    for char in letters.group(1):
        number = number * 26 + ord(char) - 64
    return number


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


class SellerShiftExcelParser:
    """Parse GLAME ЕО schedule sheet without external xlsx dependencies."""

    def parse_file(self, path: str | Path, store_name: Optional[str] = None, source_filename: Optional[str] = None) -> Dict[str, Any]:
        workbook = self._read_workbook(Path(path))
        return self.parse_workbook_rows(workbook, store_name=store_name, source_filename=source_filename or Path(path).name)

    def parse_bytes(self, content: bytes, store_name: Optional[str] = None, source_filename: str = "schedule.xlsx") -> Dict[str, Any]:
        with NamedTemporaryFile(suffix=".xlsx") as tmp:
            tmp.write(content)
            tmp.flush()
            return self.parse_file(tmp.name, store_name=store_name, source_filename=source_filename)

    def parse_base64(self, content_base64: str, store_name: Optional[str] = None, source_filename: str = "schedule.xlsx") -> Dict[str, Any]:
        return self.parse_bytes(base64.b64decode(content_base64), store_name=store_name, source_filename=source_filename)

    def parse_workbook_rows(self, workbook: Dict[str, List[Tuple[int, Dict[int, Any]]]], store_name: Optional[str], source_filename: str) -> Dict[str, Any]:
        sheet_name = self._find_schedule_sheet(workbook)
        rows = workbook[sheet_name]
        row_map = {row_number: cells for row_number, cells in rows}
        period = self._parse_period(row_map)
        starts_at, ends_at = self._parse_working_hours(row_map)
        header_row_number, day_columns = self._find_day_columns(rows)
        shifts: List[Dict[str, Any]] = []
        skipped_rows: List[Dict[str, Any]] = []
        for row_number, cells in rows:
            if row_number <= header_row_number:
                continue
            seller_name = _cell_text(cells.get(2))
            position = _cell_text(cells.get(3))
            if not seller_name or seller_name.lower().startswith("итого"):
                continue
            for column, day_number in day_columns.items():
                mark = _cell_text(cells.get(column))
                if not mark:
                    continue
                if not self._is_worked_shift_mark(mark):
                    skipped_rows.append({"row_number": row_number, "seller_name": seller_name, "day": day_number, "mark": mark, "reason": "not_pure_numeric"})
                    continue
                shift_date = date(period.year, period.month, day_number).isoformat()
                shifts.append({
                    "shift_date": shift_date,
                    "seller_external_id": None,
                    "seller_name": seller_name,
                    "store_id": None,
                    "store_name": store_name,
                    "starts_at": starts_at,
                    "ends_at": ends_at,
                    "note": f"Импорт из Excel {self._period_note(period)}: {mark}; должность {position or '—'}",
                    "source_row": row_number,
                    "source_day": day_number,
                    "source_mark": mark,
                    "position": position or None,
                })
        return {
            "success": True,
            "source_file": source_filename,
            "source_sheet": sheet_name,
            "store_name": store_name,
            "period_month": period.isoformat()[:7],
            "starts_at": starts_at,
            "ends_at": ends_at,
            "shifts": shifts,
            "stats": {
                "parsed_shifts": len(shifts),
                "skipped_marks": len(skipped_rows),
                "sellers_count": len({row["seller_name"] for row in shifts}),
            },
            "skipped_rows": skipped_rows[:100],
        }

    def _read_workbook(self, path: Path) -> Dict[str, List[Tuple[int, Dict[int, Any]]]]:
        with zipfile.ZipFile(path) as archive:
            shared_strings = self._read_shared_strings(archive)
            relationship_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            relationships = {item.attrib["Id"]: item.attrib["Target"] for item in relationship_root.findall(f"{RELS_NS}Relationship")}
            workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
            sheets: Dict[str, List[Tuple[int, Dict[int, Any]]]] = {}
            for sheet in workbook_root.find(f"{NS}sheets") or []:
                name = sheet.attrib.get("name") or "Sheet"
                target = relationships.get(sheet.attrib.get(f"{REL_NS}id", ""))
                if not target:
                    continue
                sheet_path = f"xl/{target}" if not target.startswith("/") else target[1:]
                sheets[name] = self._read_sheet(archive, sheet_path, shared_strings)
            return sheets

    def _read_shared_strings(self, archive: zipfile.ZipFile) -> List[str]:
        if "xl/sharedStrings.xml" not in archive.namelist():
            return []
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        strings: List[str] = []
        for item in root.findall(f"{NS}si"):
            strings.append("".join(text.text or "" for text in item.iter(f"{NS}t")))
        return strings

    def _read_sheet(self, archive: zipfile.ZipFile, sheet_path: str, shared_strings: List[str]) -> List[Tuple[int, Dict[int, Any]]]:
        root = ET.fromstring(archive.read(sheet_path))
        rows: List[Tuple[int, Dict[int, Any]]] = []
        sheet_data = root.find(f"{NS}sheetData")
        if sheet_data is None:
            return rows
        for row in sheet_data.findall(f"{NS}row"):
            row_number = int(row.attrib.get("r", "0") or 0)
            cells: Dict[int, Any] = {}
            for cell in row.findall(f"{NS}c"):
                column = _column_number(cell.attrib.get("r", ""))
                value_node = cell.find(f"{NS}v")
                inline_node = cell.find(f"{NS}is")
                value: Any = None
                if value_node is not None:
                    raw = value_node.text or ""
                    if cell.attrib.get("t") == "s":
                        value = shared_strings[int(raw)] if raw.isdigit() and int(raw) < len(shared_strings) else raw
                    else:
                        value = raw
                elif inline_node is not None:
                    value = "".join(text.text or "" for text in inline_node.iter(f"{NS}t"))
                if column:
                    cells[column] = value
            rows.append((row_number, cells))
        return rows

    def _find_schedule_sheet(self, workbook: Dict[str, List[Tuple[int, Dict[int, Any]]]]) -> str:
        for name in workbook:
            if name.strip().lower() == "график":
                return name
        for name, rows in workbook.items():
            for _, cells in rows[:20]:
                values = {_cell_text(value).lower() for value in cells.values()}
                if {"фио", "должность"}.issubset(values):
                    return name
        raise ValueError("В Excel не найден лист графика смен")

    def _parse_period(self, row_map: Dict[int, Dict[int, Any]]) -> date:
        for cells in row_map.values():
            for value in cells.values():
                text = _cell_text(value).lower().replace("ё", "е")
                match = re.search(r"([а-я]+)\s*,?\s*(20\d{2})", text)
                if match and match.group(1) in RUSSIAN_MONTHS:
                    return date(int(match.group(2)), RUSSIAN_MONTHS[match.group(1)], 1)
        raise ValueError("Не удалось определить месяц графика из Excel")

    def _parse_working_hours(self, row_map: Dict[int, Dict[int, Any]]) -> Tuple[str, str]:
        for cells in row_map.values():
            for value in cells.values():
                text_value = _cell_text(value)
                match = re.search(r"(\d{1,2})[.:](\d{2})\s*[-–—]\s*(\d{1,2})[.:](\d{2})", text_value)
                if match:
                    return f"{int(match.group(1)):02d}:{match.group(2)}", f"{int(match.group(3)):02d}:{match.group(4)}"
        return "10:00", "22:00"

    def _find_day_columns(self, rows: Iterable[Tuple[int, Dict[int, Any]]]) -> Tuple[int, Dict[int, int]]:
        for row_number, cells in rows:
            values = {_cell_text(value).lower() for value in cells.values()}
            if "фио" not in values or "должность" not in values:
                continue
            day_columns: Dict[int, int] = {}
            for column, value in cells.items():
                text_value = _cell_text(value)
                if text_value.isdigit():
                    day = int(text_value)
                    if 1 <= day <= 31:
                        day_columns[column] = day
            if day_columns:
                return row_number, day_columns
        raise ValueError("Не найдена строка с днями месяца в листе графика")

    def _is_worked_shift_mark(self, value: str) -> bool:
        return bool(re.fullmatch(r"\d+(?:[.,]\d+)?", value.strip()))

    def _period_note(self, period: date) -> str:
        names = {1: "январь", 2: "февраль", 3: "март", 4: "апрель", 5: "май", 6: "июнь", 7: "июль", 8: "август", 9: "сентябрь", 10: "октябрь", 11: "ноябрь", 12: "декабрь"}
        return f"{names[period.month]} {period.year}"
