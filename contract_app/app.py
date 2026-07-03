"""
AI Asia сургалтын гэрээ — FastAPI (Next.js-ийг орлуулсан).

Урсгал: суралцагч `/contract/<id>` линк нээх → мэдээлэл шалгах/нөхөх →
гэрээ (PDF) урьдчилан харах → гарын үсэг зурах → бөглөгдсөн PDF татах.
Гэрээний араас classCode-д тохирох хичээлийн хөтөлбөр залгагдана.
"""
from __future__ import annotations

import html
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
from .ai_certificate import fill_ai_certificate, get_engineer_by_id, verify_cert_token
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


# --- Сертификат баталгаажуулах хуудас (QR unshuulah destination) --------------
# ai-academy.asia сайтын header/footer-ийг апп-ийн өөрийн static (лого) дээр
# тулгуурлан дуурайлгаж, бүх холбоосыг гол домэйн руу чиглүүлнэ.
_SITE = "https://ai-academy.asia"
_LOGO = PREFIX + "/_static/logo.png"

# Footer баганууд (ai-academy.asia footer-ийн бүтэц/холбоосоор).
_FOOTER_COLS = [
    ("Бүтээгдэхүүн", [
        ("Хүүхдэд", f"{_SITE}/mn/summer-cohort"),
        ("Насанд хүрэгчид", f"{_SITE}/mn/summer-cohort"),
        ("Байгууллагуудад", f"{_SITE}/mn/summer-cohort"),
    ]),
    ("Байгууллага", [
        ("Бидний тухай", f"{_SITE}/mn/about"),
        ("Багш нар", f"{_SITE}/"),
        ("Хамтрагчид", f"{_SITE}/"),
    ]),
    ("Нөөц", [
        ("Блог", f"{_SITE}/mn/blog/45"),
    ]),
    ("Хууль эрх зүй", [
        ("Нууцлалын бодлого", f"{_SITE}/mn/privacy-policy"),
        ("Үйлчилгээний нөхцөл", f"{_SITE}/mn/terms"),
    ]),
]


def _site_header() -> str:
    return (
        "<header class='site-header'><div class='wrap'>"
        f"<a class='logo' href='{_SITE}/'>"
        f"<img src='{_LOGO}' alt='AI Academy Asia'>"
        "<span>AI Academy Asia</span></a>"
        f"<a class='nav-cta' href='{_SITE}/'>Нүүр хуудас</a>"
        "</div></header>"
    )


def _site_footer() -> str:
    cols = ""
    for title, links in _FOOTER_COLS:
        items = "".join(f"<li><a href='{href}'>{html.escape(label)}</a></li>"
                        for label, href in links)
        cols += f"<div class='fcol'><h4>{html.escape(title)}</h4><ul>{items}</ul></div>"
    return (
        "<footer class='site-footer'><div class='wrap ftop'>"
        "<div class='fbrand'>"
        f"<a class='logo' href='{_SITE}/'><img src='{_LOGO}' alt='AI Academy Asia'>"
        "<span>AI Academy Asia</span></a>"
        "<p>Хиймэл оюун ухааны боловсрол хүн бүрт</p></div>"
        f"<div class='fcols'>{cols}</div>"
        "</div><div class='wrap fbottom'>"
        "<span>© AI-Academy 2026. Бүх эрх хуулиар хамгаалагдсан.</span>"
        "</div></footer>"
    )


def _page_shell(title: str, inner: str) -> str:
    return (
        "<!doctype html><html lang='mn'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<link rel='icon' href='{_LOGO}'>"
        f"<title>{html.escape(title)}</title>" + _VERIFY_CSS +
        "</head><body>" + _site_header() +
        f"<main class='page'>{inner}</main>" + _site_footer() +
        "</body></html>"
    )


def _verify_page(data: dict | None) -> str:
    """Токен шалгасны дараах HTML лавлагааны хуудас. data=None → хүчингүй."""
    E = html.escape
    if not data:
        inner = (
            "<section class='card invalid'>"
            "<div class='badge'>✕</div>"
            "<h1>Хүчингүй сертификат</h1>"
            "<p class='muted'>Энэ QR-ийн токен буруу, дутуу эсвэл өөрчлөгдсөн байна. "
            "Уг сертификат AI Academy Asia-аас олгогдоогүй байж болзошгүй.</p>"
            "</section>"
        )
        return _page_shell("Сертификат — Хүчингүй", inner)

    full_name = f"{data.get('fn','')} {data.get('ln','')}".strip()
    rows = [
        ("Нэр", full_name),
        ("Сертификатын дугаар", data.get("no", "")),
        ("Capstone төсөл", data.get("cap", "")),
        ("Олгосон огноо", data.get("dt", "")),
    ]
    rows_html = "".join(
        f"<div class='row'><span class='k'>{E(k)}</span>"
        f"<span class='v'>{E(str(v))}</span></div>"
        for k, v in rows if str(v).strip()
    )
    inner = (
        "<section class='card valid'>"
        "<div class='badge'>✓</div>"
        "<h1>Баталгаажсан сертификат</h1>"
        "<p class='muted'>Энэ сертификатыг AI Academy Asia олгосон нь баталгаажлаа.</p>"
        f"<div class='details'>{rows_html}</div>"
        "<p class='brand'>AI Academy Asia · AI Engineer</p>"
        "</section>"
    )
    return _page_shell(f"Баталгаажсан — {full_name}", inner)


_VERIFY_CSS = (
    "<style>"
    ":root{color-scheme:light dark;--bg:#f4f5f7;--fg:#1f2328;--card:#fff;"
    "--muted:#6b7280;--line:#eceef1;--brand:#2563eb;--head:#0b1220}"
    "@media(prefers-color-scheme:dark){:root{--bg:#0d1117;--fg:#e6edf3;"
    "--card:#161b22;--muted:#9aa4b2;--line:#30363d;--brand:#5b8cff;--head:#0b1220}}"
    "*{box-sizing:border-box}"
    "body{margin:0;min-height:100vh;display:flex;flex-direction:column;"
    "font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;"
    "background:var(--bg);color:var(--fg)}"
    "a{text-decoration:none;color:inherit}"
    ".wrap{max-width:1080px;margin:0 auto;padding:0 24px;width:100%}"
    # header
    ".site-header{background:var(--head);color:#fff;position:sticky;top:0;z-index:5}"
    ".site-header .wrap{display:flex;align-items:center;justify-content:space-between;"
    "height:64px}"
    ".logo{display:flex;align-items:center;gap:10px;font-weight:700;color:#fff}"
    ".logo img{height:32px;width:auto;display:block}"
    ".nav-cta{background:var(--brand);color:#fff;padding:9px 16px;border-radius:8px;"
    "font-size:14px;font-weight:600}"
    # main
    ".page{flex:1;display:flex;align-items:center;justify-content:center;padding:40px 24px}"
    ".card{width:100%;max-width:440px;background:var(--card);border-radius:16px;"
    "padding:36px 28px;text-align:center;box-shadow:0 8px 40px rgba(0,0,0,.12)}"
    ".badge{width:72px;height:72px;border-radius:50%;margin:0 auto 18px;"
    "display:flex;align-items:center;justify-content:center;font-size:38px;"
    "color:#fff;font-weight:700}"
    ".valid .badge{background:#3645ff}.invalid .badge{background:#d64545}"
    ".card h1{font-size:22px;margin:0 0 8px}"
    ".muted{color:var(--muted);font-size:14px;line-height:1.5;margin:0 0 22px}"
    ".details{text-align:left;border-top:1px solid var(--line);margin-bottom:20px}"
    ".row{display:flex;justify-content:space-between;gap:16px;padding:12px 2px;"
    "border-bottom:1px solid var(--line);font-size:14px}"
    ".k{color:var(--muted);flex:0 0 auto}.v{font-weight:600;text-align:right}"
    ".brand{font-size:12px;letter-spacing:.04em;color:var(--muted);margin:0}"
    # footer
    ".site-footer{background:var(--head);color:#cbd5e1;margin-top:auto}"
    ".ftop{display:flex;flex-wrap:wrap;gap:32px;justify-content:space-between;"
    "padding-top:40px;padding-bottom:28px}"
    ".fbrand{max-width:260px}.fbrand .logo{color:#fff;margin-bottom:10px}"
    ".fbrand p{font-size:13px;color:#94a3b8;margin:0;line-height:1.5}"
    ".fcols{display:flex;flex-wrap:wrap;gap:40px}"
    ".fcol h4{font-size:13px;color:#fff;margin:0 0 12px;font-weight:600}"
    ".fcol ul{list-style:none;margin:0;padding:0;display:grid;gap:8px}"
    ".fcol a{font-size:13px;color:#94a3b8}.fcol a:hover{color:#fff}"
    ".fbottom{border-top:1px solid rgba(255,255,255,.08);padding-top:16px;"
    "padding-bottom:24px;font-size:12px;color:#94a3b8}"
    "@media(max-width:640px){.ftop{flex-direction:column;gap:24px}"
    ".fcols{gap:28px}.nav-cta{padding:8px 12px}}"
    "</style>"
)


@app.get(PREFIX + "/cert/verify", response_class=HTMLResponse)
def cert_verify(t: str = ""):
    """AI Engineer сертификатын QR-ыг уншихад дуудагдах лавлагааны хуудас.
    Токеныг DB-гүйгээр HMAC-SHA256-аар шалгаж, зөв бол сертификатын мэдээллийг
    харуулна; буруу/өөрчлөгдсөн бол 'Хүчингүй' хуудас буцаана."""
    data = verify_cert_token(t)
    status = 200 if data else 400
    return HTMLResponse(_verify_page(data), status_code=status)


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
