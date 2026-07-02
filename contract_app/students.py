"""Суралцагчид — PostgreSQL-ээс уншина; DB унтарсан үед `data/students.json`-оос fallback."""
from __future__ import annotations

import json
from pathlib import Path

from . import db

ROOT = Path(__file__).resolve().parent.parent
STUDENTS_FILE = ROOT / "data" / "students.json"


def _from_json() -> list[dict]:
    try:
        return json.loads(STUDENTS_FILE.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print("students.json read failed:", exc)
        return []


def get_student_by_id(student_id: str) -> dict | None:
    try:
        return db.get_student_by_id(student_id)
    except Exception as exc:  # noqa: BLE001 — DB унтарсан → JSON-оос
        print("DB read failed, falling back to students.json:", exc)
        return next((s for s in _from_json() if s.get("id") == student_id), None)


def get_students() -> list[dict]:
    try:
        return db.get_students()
    except Exception as exc:  # noqa: BLE001
        print("DB read failed, falling back to students.json:", exc)
        return _from_json()


__all__ = ["get_student_by_id", "get_students"]
