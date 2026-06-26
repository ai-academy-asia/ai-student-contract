"""Суралцагчид — PostgreSQL-ээс уншина (анх удаа `data/students.json`-оос seed хийгдэнэ)."""
from .db import get_student_by_id, get_students

__all__ = ["get_student_by_id", "get_students"]
