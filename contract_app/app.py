"""
AI Asia сургалтын гэрээ — FastAPI (Next.js-ийг орлуулсан).

Урсгал: суралцагч `/contract/<id>` линк нээх → мэдээлэл шалгах/нөхөх →
гэрээ (PDF) урьдчилан харах → гарын үсэг зурах → бөглөгдсөн PDF татах.
Гэрээний араас classCode-д тохирох хичээлийн хөтөлбөр залгагдана.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import Response, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .students import get_student_by_id
from .fill import build_values, program_pdf, fill_contract, discount_pct
from .certificate import fill_certificate, latin_full_name
from .ai_certificate import fill_ai_certificate, get_engineer_by_id
from . import db
from . import signed_store

BASE = Path(__file__).resolve().parent
# Гэрээний нийтийн линк (DB-д хадгалах): https://ai-academy.asia/contract/<id>
CONTRACT_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "https://ai-academy.asia").rstrip("/")
# Бүх замыг энэ угтвар дор байрлуулна → nginx зөвхөн нэг `location /contract/`-оор
# проксолж, гол домэйн дээрх академийн сайттай (/, /api, /_next ...) мөргөлдөхгүй.
PREFIX = "/contract"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        db.init_db()
    except Exception as exc:  # noqa: BLE001 — DB байхгүй ч апп ажиллана
        print("DB init failed (persistence off):", exc)
    yield


app = FastAPI(title="AI Asia Contract", lifespan=lifespan)
app.mount(f"{PREFIX}/_static", StaticFiles(directory=str(BASE / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE / "templates"))


def _today() -> str:
    return date.today().isoformat()


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (
        "<html><body style='font-family:sans-serif;padding:40px'>"
        "<h2>AI Asia — Сургалтын гэрээ</h2>"
        "<p>Гэрээний линк: <code>/contract/&lt;student-id&gt;</code></p>"
        "</body></html>"
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get(PREFIX + "/{slug}", response_class=HTMLResponse)
def contract_page(request: Request, slug: str):
    return templates.TemplateResponse("contract.html", {"request": request, "slug": slug})


def _already_signed(student_id: str) -> bool:
    # 1) Файл дээрх түгжээ — DB-гүй ч найдвартай ажиллана.
    if signed_store.is_signed(student_id):
        return True
    # 2) DB (боломжтой бол) — production-д persistence-ийн эх сурвалж.
    try:
        return db.has_signed_contract(student_id)
    except Exception as exc:  # noqa: BLE001 — DB down → файлын түгжээ л шийднэ
        print("has_signed_contract check failed:", exc)
        return False


@app.get(PREFIX + "/_api/student/{student_id}")
def api_student(student_id: str):
    student = get_student_by_id(student_id)
    if not student:
        return JSONResponse({"error": "Олдсонгүй"}, status_code=404)
    # аль хэдийн баталгаажсан гэрээтэй бол дахин хандуулахгүй
    return {**student, "alreadySigned": _already_signed(student_id)}


@app.get(PREFIX + "/_api/certificate/{student_id}")
def api_certificate(student_id: str):
    """Хүүхдийн id-гаар нэр/овгийг тавьсан төгсөлтийн сертификатыг (PDF) буцаана."""
    student = get_student_by_id(student_id)
    if not student:
        return JSONResponse({"error": "Олдсонгүй"}, status_code=404)
    try:
        pdf = fill_certificate(
            class_code=student.get("classCode"),
            first_name=student.get("firstName"),
            last_name=student.get("lastName"),
            today=_today(),
        )
    except FileNotFoundError:
        return JSONResponse(
            {"error": "Энэ хөтөлбөрт тохирох сертификатын загвар алга"}, status_code=404)
    except Exception as exc:  # noqa: BLE001
        print("Certificate error:", exc)
        return JSONResponse({"error": "Сертификат үүсгэх алдаа"}, status_code=500)

    fname = f"{latin_full_name(student.get('firstName'), student.get('lastName')) or student_id}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{fname}"'})


@app.get(PREFIX + "/_api/ai-certificate/{student_id}")
def api_ai_certificate(student_id: str):
    """AI Engineer сертификат: `data/ai_engineer.json`-оос student_id-гаар олж
    AIEngineer.pdf-ийг бөглөөд PDF-ийг татаж өгнө. QR-ийг уншихад энэ эндпойнт
    дуудагдаж PDF шууд татагдана."""
    student = get_engineer_by_id(student_id)
    if not student:
        return JSONResponse({"error": "Олдсонгүй"}, status_code=404)
    try:
        pdf = fill_ai_certificate(student, base_url=CONTRACT_BASE_URL)
    except FileNotFoundError as exc:
        print("AI certificate template error:", exc)
        return JSONResponse({"error": "Сертификатын загвар алга"}, status_code=404)
    except Exception as exc:  # noqa: BLE001
        print("AI certificate error:", exc)
        return JSONResponse({"error": "Сертификат үүсгэх алдаа"}, status_code=500)

    name = f"{student.get('first_name','')} {student.get('last_name','')}".strip() or student_id
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'})


def _build_pdf(body: dict, signature: str | None) -> bytes:
    form = body.get("formData") or {}
    finance = body.get("finance") or {"tolokhDun": "", "tolson": "", "uldegdel": ""}
    today = form.get("ognoo") or _today()
    values = build_values(
        form=form,
        finance=finance,
        program=body.get("program"),
        num=body.get("num"),
        today=today,
    )
    return fill_contract(
        values=values,
        signature_b64=signature,
        append_path=program_pdf(body.get("classCode")),
    )


@app.post(PREFIX + "/_api/preview")
async def api_preview(request: Request):
    try:
        body = await request.json()
        pdf = _build_pdf(body, signature=None)
        return Response(content=pdf, media_type="application/pdf",
                        headers={"Content-Disposition": "inline; filename=preview.pdf"})
    except Exception as exc:  # noqa: BLE001
        print("Preview error:", exc)
        return JSONResponse({"error": "Урьдчилан харах алдаа"}, status_code=500)


@app.post(PREFIX + "/_api/generate")
async def api_generate(request: Request):
    try:
        body = await request.json()
        if not body.get("formData") or not body.get("signature"):
            return JSONResponse({"error": "Шаардлагатай мэдээлэл дутуу байна"}, status_code=400)
        student_id = body.get("studentId", "contract")
        # давхар баталгаажуулалтаас сэргийлэх
        if _already_signed(student_id):
            return JSONResponse({"error": "Энэ гэрээ аль хэдийн баталгаажсан байна"}, status_code=409)
        pdf = _build_pdf(body, signature=body.get("signature"))

        # Хэрэглэгчийн мэдээлэл + PDF файл + гарын үсгийг хадгалах (best-effort)
        try:
            finance = body.get("finance") or {}
            rec = db.save_contract(
                student_id=student_id, num=body.get("num", ""),
                class_code=body.get("classCode", ""), program=body.get("program", ""),
                form=body.get("formData") or {}, finance=finance,
                discount=discount_pct(finance.get("tolokhDun")),
                contract_link=f"{CONTRACT_BASE_URL}/contract/{student_id}",
                pdf_bytes=pdf, signature_b64=body.get("signature"),
            )
            print(f"contract saved: id={rec['id']} pdf={rec['pdf_path']}")
        except Exception as exc:  # noqa: BLE001 — хадгалалт амжилтгүй ч PDF-ийг буцаана
            print("DB save failed:", exc)

        # Файл дээрх нэг удаагийн түгжээг тэмдэглэх (DB-гүй ч дахин хийхийг блоклоно).
        try:
            signed_store.mark_signed(student_id, num=body.get("num", ""),
                                     class_code=body.get("classCode", ""))
        except Exception as exc:  # noqa: BLE001
            print("signed marker write failed:", exc)

        return Response(content=pdf, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="contract-{student_id}.pdf"'})
    except Exception as exc:  # noqa: BLE001
        print("Generate error:", exc)
        return JSONResponse({"error": str(exc) or "Серверийн алдаа"}, status_code=500)
