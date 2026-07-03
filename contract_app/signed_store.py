"""
Файл дээр суурилсан **"нэг сурагч — нэг удаа"** түгжээ.

PostgreSQL унтарсан үед ч гэрээг дахин дахин баталгаажуулахаас сэргийлнэ.
Сурагч амжилттай гарын үсэг зурж PDF үүсгэмэгц `storage/signed/<student_id>.json`
маркер бичигдэнэ; дараа нь тухайн id-гаар дахин хийхийг блоклоно.

Reset (дахин зөвшөөрөх): холбогдох `storage/signed/<student_id>.json` файлыг устгана
(мөн DB ашиглаж байгаа бол `contracts` мөрийг устгах).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIGNED_DIR = ROOT / "storage" / "signed"


def _safe(student_id: str) -> str:
    """Файлын нэрэнд аюулгүй болгох (path traversal-аас сэргийлж)."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(student_id)).strip("._")[:100] or "unknown"


def is_signed(student_id: str) -> bool:
    if not student_id:
        return False
    return (SIGNED_DIR / f"{_safe(student_id)}.json").exists()


def mark_signed(student_id: str, **meta) -> None:
    """Тухайн сурагчийг 'баталгаажсан' гэж тэмдэглэнэ (маркер файл бичнэ)."""
    if not student_id:
        return
    SIGNED_DIR.mkdir(parents=True, exist_ok=True)
    path = SIGNED_DIR / f"{_safe(student_id)}.json"
    data = {
        "student_id": str(student_id),
        "signed_at": datetime.now(timezone.utc).isoformat(),
        **{k: v for k, v in meta.items() if v not in (None, "")},
    }
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
