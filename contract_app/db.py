"""
PostgreSQL хадгалалт.

- `students`  — суралцагчид. Анх удаа `data/students.json`-оос DB-д seed хийгдэнэ;
  цаашид апп DB-ээс уншина.
- `contracts` — хэрэглэгчээс авсан мэдээлэл + гэрээний линк + PDF файл + гарын үсэг.

Тохиргоо: `DATABASE_URL` (default — локал Docker дахь contract_db).
PDF/гарын үсэг `storage/`-д файлаар хадгалагдаж, замыг нь DB-д бичнэ.
"""
from __future__ import annotations

import os
import json
import base64
import uuid
from datetime import datetime
from pathlib import Path

import psycopg

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://admin:admin123@localhost:5432/contract_db"
)

ROOT = Path(__file__).resolve().parent.parent
STUDENTS_FILE = ROOT / "data" / "students.json"
PDF_DIR = ROOT / "storage" / "pdfs"
SIG_DIR = ROOT / "storage" / "signatures"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    id          TEXT PRIMARY KEY,
    num         TEXT,
    class_code  TEXT,
    data        JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS contracts (
    id                  SERIAL PRIMARY KEY,
    student_id          TEXT,
    num                 TEXT,
    class_code          TEXT,
    program             TEXT,
    last_name           TEXT,
    first_name          TEXT,
    register            TEXT,
    guardian_relation   TEXT,
    guardian_last_name  TEXT,
    guardian_first_name TEXT,
    guardian_register   TEXT,
    guardian_phone      TEXT,
    guardian_email      TEXT,
    address_detail      TEXT,
    final_payment_date  TEXT,
    tolokh_dun          TEXT,
    tolson              TEXT,
    uldegdel            TEXT,
    discount            TEXT,
    form_data           JSONB,
    contract_link       TEXT,
    pdf_path            TEXT,
    signature_path      TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

# Хуучин хүснэгтэд багана нэмэх (миграц)
_MIGRATIONS = [
    "ALTER TABLE contracts ADD COLUMN IF NOT EXISTS contract_link TEXT;",
]


# ── Эхлүүлэлт + seed ──────────────────────────────────────────────────────────
def init_db() -> None:
    """Хүснэгт, миграц, storage хавтас бэлдэж, students-ийг анх удаа seed хийнэ."""
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    SIG_DIR.mkdir(parents=True, exist_ok=True)
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(_SCHEMA)
        for stmt in _MIGRATIONS:
            conn.execute(stmt)
        conn.commit()
        _seed_students(conn)


def _seed_students(conn: "psycopg.Connection") -> None:
    """students хоосон бол `data/students.json`-оос анх удаа дүүргэнэ."""
    count = conn.execute("SELECT count(*) FROM students").fetchone()[0]
    if count:
        return
    if not STUDENTS_FILE.exists():
        print("seed skipped: students.json not found")
        return
    students = json.loads(STUDENTS_FILE.read_text(encoding="utf-8"))
    with conn.cursor() as cur:
        for s in students:
            cur.execute(
                """INSERT INTO students (id, num, class_code, data)
                   VALUES (%s, %s, %s, %s) ON CONFLICT (id) DO NOTHING""",
                (s.get("id"), s.get("num"), s.get("classCode"),
                 json.dumps(s, ensure_ascii=False)),
            )
    conn.commit()
    print(f"seeded {len(students)} students into DB")


# ── Суралцагч унших (DB-ээс) ──────────────────────────────────────────────────
def get_student_by_id(student_id: str) -> dict | None:
    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute(
            "SELECT data FROM students WHERE id = %s", (student_id,)
        ).fetchone()
    return row[0] if row else None


def get_students() -> list[dict]:
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute("SELECT data FROM students ORDER BY num").fetchall()
    return [r[0] for r in rows]


# ── Гэрээ ─────────────────────────────────────────────────────────────────────
def has_signed_contract(student_id: str) -> bool:
    """Тухайн сурагч PDF + гарын үсэгтэй гэрээ аль хэдийн үүсгэсэн эсэх."""
    if not student_id:
        return False
    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute(
            "SELECT 1 FROM contracts WHERE student_id = %s "
            "AND pdf_path IS NOT NULL AND signature_path IS NOT NULL LIMIT 1",
            (student_id,),
        ).fetchone()
    return row is not None


def _save_file(directory: Path, name: str, data: bytes) -> str:
    path = directory / name
    path.write_bytes(data)
    return str(path)


def save_contract(*, student_id: str, num: str, class_code: str, program: str,
                  form: dict, finance: dict, discount: str, contract_link: str,
                  pdf_bytes: bytes, signature_b64: str | None) -> dict:
    """Гэрээний бүртгэлийг (мэдээлэл + линк + PDF + гарын үсэг) хадгална."""
    f = form or {}
    fin = finance or {}
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"{(student_id or 'contract')}_{stamp}_{uuid.uuid4().hex[:6]}"

    pdf_path = _save_file(PDF_DIR, base + ".pdf", pdf_bytes)

    signature_path = None
    if signature_b64:
        try:
            png = base64.b64decode(signature_b64.split(",")[-1])
            signature_path = _save_file(SIG_DIR, base + ".png", png)
        except Exception as e:  # noqa: BLE001
            print("signature save skipped:", e)

    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute(
            """
            INSERT INTO contracts (
                student_id, num, class_code, program,
                last_name, first_name, register,
                guardian_relation, guardian_last_name, guardian_first_name,
                guardian_register, guardian_phone, guardian_email,
                address_detail, final_payment_date,
                tolokh_dun, tolson, uldegdel, discount,
                form_data, contract_link, pdf_path, signature_path
            ) VALUES (
                %(student_id)s, %(num)s, %(class_code)s, %(program)s,
                %(last_name)s, %(first_name)s, %(register)s,
                %(guardian_relation)s, %(guardian_last_name)s, %(guardian_first_name)s,
                %(guardian_register)s, %(guardian_phone)s, %(guardian_email)s,
                %(address_detail)s, %(final_payment_date)s,
                %(tolokh_dun)s, %(tolson)s, %(uldegdel)s, %(discount)s,
                %(form_data)s, %(contract_link)s, %(pdf_path)s, %(signature_path)s
            ) RETURNING id
            """,
            {
                "student_id": student_id, "num": num, "class_code": class_code, "program": program,
                "last_name": f.get("lastName"), "first_name": f.get("firstName"), "register": f.get("register"),
                "guardian_relation": f.get("guardianRelation"),
                "guardian_last_name": f.get("guardianLastName"),
                "guardian_first_name": f.get("guardianFirstName"),
                "guardian_register": f.get("guardianRegister"),
                "guardian_phone": f.get("guardianPhone"),
                "guardian_email": f.get("guardianEmail"),
                "address_detail": f.get("addressDetail"),
                "final_payment_date": f.get("finalPaymentDate"),
                "tolokh_dun": fin.get("tolokhDun"), "tolson": fin.get("tolson"),
                "uldegdel": fin.get("uldegdel"), "discount": discount,
                "form_data": json.dumps(f, ensure_ascii=False),
                "contract_link": contract_link,
                "pdf_path": pdf_path, "signature_path": signature_path,
            },
        ).fetchone()
        conn.commit()

    return {"id": row[0], "pdf_path": pdf_path, "signature_path": signature_path}
