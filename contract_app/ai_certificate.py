"""
AI Engineer сертификат (AIEngineer.pdf) бөглөх.

`public/templates/certificates/AIEngineer.pdf` загвар нь жинхэнэ embedded фонттой
(OpenSans, Liana) тул placeholder текстийг **redaction**-оор цэвэрхэн устгаад, дээр нь
шинэ утгыг тохирох фонт/хэмжээгээр бичнэ. Мэдээллийг `data/ai_engineer.json`-оос
`student_id`-гаар олж авна.

Placeholder-ууд:
    #certificate_no  → student_id            (Open Sans, 14pt, төвлөрсөн)
    #firstname       → first_name            (Liana, 40pt)
    #lastname        → last_name             (Liana, 40pt)
    #capstone_topic  → project_name_en       (Open Sans, 12pt)
    QR (зүүн доод badge) → HMAC-hash-аар баталгаажсан, өөртөө сертификатын мэдээлэл
                          агуулсан (base64) токен → лавлагааны хуудас руу.

QR нь id-аар API дуудахгүй. Оронд нь сертификатын талбаруудыг JSON→base64url болгож,
`CERT_SIGNING_SECRET`-ээр HMAC-SHA256 hash хийж `<payload>.<sig>` токен үүсгэнэ. QR-д
`{base_url}/contract/cert/verify?t=<token>` URL-ийг кодолно. Уншихад лавлагааны хуудас
токеныг **DB-гүйгээр** задалж, hash-ыг дахин тооцож шалгаад мэдээллийг шууд харуулна.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import os
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import fitz  # PyMuPDF

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "ai_engineer.json"
TEMPLATE = ROOT / "public" / "templates" / "certificates" / "AIEngineer.pdf"
FONT_DIR = Path(__file__).resolve().parent / "fonts"

# Нэмж бичих бүх текстийн өнгө — #3d3939 (dark grey).
INK = (0x3d / 255, 0x39 / 255, 0x39 / 255)

# --- QR токен: өөртөө агуулсан, HMAC-аар баталгаажсан ------------------------
# Секретийг production-д заавал env-ээр өгнө (default-ыг сольж болохгүй).
CERT_SECRET = os.environ.get("CERT_SIGNING_SECRET",
                             "ai-academy-asia-cert-2026-CHANGE-ME")


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64u_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(body: str) -> str:
    return _b64u(hmac.new(CERT_SECRET.encode("utf-8"), body.encode("ascii"),
                          hashlib.sha256).digest())


def make_cert_token(payload: dict) -> str:
    """payload(JSON)-ыг base64url болгож, HMAC-SHA256 hash хавсаргаж `body.sig` токен."""
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    body = _b64u(raw)
    return f"{body}.{_sign(body)}"


def verify_cert_token(token: str) -> dict | None:
    """Токеныг DB-гүйгээр шалгах: hash таарвал payload dict, эс бол None."""
    if not token or "." not in token:
        return None
    body, _, sig = token.partition(".")
    if not hmac.compare_digest(sig, _sign(body)):   # tamper / буруу секрет
        return None
    try:
        return json.loads(_b64u_decode(body).decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None

# --- Фонтууд ------------------------------------------------------------------
# Нэр — Liana (script, загварын эх #firstname/#lastname-тэй ижил).
# contract_app/fonts/Liana.ttf (эсвэл CERT_NAME_FONT env-ээр).
# Байхгүй бол Crimson Pro serif, эцэст нь системийн serif руу fallback хийнэ.
NAME_FONT_CANDIDATES = [
    os.environ.get("CERT_NAME_FONT", ""),
    str(FONT_DIR / "Liana.ttf"),
    str(FONT_DIR / "CrimsonPro-Regular.ttf"),
    "/System/Library/Fonts/Supplemental/Georgia.ttf",                 # macOS fallback
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",               # Linux fallback
    "/usr/share/fonts/truetype/freefont/FreeSerif.ttf",
]
# Бусад бичвэр — Open Sans.
BODY_FONT_CANDIDATES = [
    os.environ.get("CERT_BODY_FONT", ""),
    str(FONT_DIR / "OpenSans-Regular.ttf"),
    "/usr/share/fonts/truetype/open-sans/OpenSans-Regular.ttf",       # Linux
    "/System/Library/Fonts/Supplemental/Arial.ttf",                   # macOS fallback
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]
# Огноо — загварын #date нь OpenSans Bold Italic; байхгүй бол энгийн body руу.
DATE_FONT_CANDIDATES = [
    os.environ.get("CERT_DATE_FONT", ""),
    str(FONT_DIR / "OpenSans-BoldItalic.ttf"),
    "/System/Library/Fonts/Supplemental/Arial Bold Italic.ttf",       # macOS fallback
    "/usr/share/fonts/truetype/liberation/LiberationSans-BoldItalic.ttf",
]

# --- Placeholder байрлал (AIEngineer.pdf, 842×595) ---------------------------
# search_for-оор баталгаажуулсан.
_CERT_NO_RECT = fitz.Rect(375.87, 39.66, 472.48, 58.73)     # #certificate_no
_NAME_RECT = fitz.Rect(266.03, 203.66, 576.15, 271.59)      # #firstname #lastname
# "Capstone project: #capstone_topic" мөр letter-spacing-тэй тул search_for олохгүй.
# '#' үг x0≈210.4-с эхэлдэг; өмнөх "Capstone project:"-ийг хэвээр үлдээж, түүнээс
# хойшхийг л устгана.
_CAPSTONE_LINE = fitz.Rect(65.5, 361.7, 335.9, 378.1)
_CAPSTONE_VALUE_X0 = 210.4                                  # '#' -ийн эхлэл
_CAPSTONE_VALUE_X1 = 788.0                                  # утга сунах баруун хязгаар
# #date — доод голд ганцаараа (BoldItalic 17). Yesterday-г төвлүүлж бичнэ.
_DATE_RECT = fitz.Rect(397.28, 566.02, 444.90, 589.17)
# Нэрийн доорх зураас y≈267.4; нэрийг түүнээс жоохон дээш тавина.
_NAME_UNDERLINE_Y = 267.4
_NAME_CENTER_X = 421.09                                      # (266+576)/2
_NAME_MAXW = 520.0                                          # зурааны өргөнд багтаана
# Загвар дээрх жишээ QR (доод зүүн badge доторх) — үүн дээр шинэ QR-ийг давхарлана.
_QR_RECT = fitz.Rect(86.3, 431.6, 164.9, 510.0)

_CERT_NO_SIZE = 14.0
_NAME_SIZE = 46.0
_CAPSTONE_SIZE = 15.0
_DATE_SIZE = 17.0


def _pick_font(candidates: list[str]) -> str | None:
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return None


def _find_rect(pg, token: str, fallback: "fitz.Rect | None"):
    """Placeholder-ийг search_for-оор олж эхний rect-ийг буцаана (олдохгүй бол
    fallback). Template өөрчлөгдсөн ч байрлалыг динамикаар олж мөрдөнө."""
    try:
        hits = pg.search_for(token)
    except Exception:  # noqa: BLE001
        hits = []
    return hits[0] if hits else fallback


# --- Мэдээлэл -----------------------------------------------------------------
def _load_students() -> list[dict]:
    try:
        return (json.loads(DATA_FILE.read_text(encoding="utf-8")) or {}).get("students", [])
    except Exception as exc:  # noqa: BLE001
        print("ai_engineer.json read failed:", exc)
        return []


def get_engineer_by_id(student_id: str) -> dict | None:
    """`data/ai_engineer.json`-оос student_id-гаар суралцагчийг олж буцаана."""
    sid = str(student_id).strip()
    return next((s for s in _load_students() if str(s.get("student_id")) == sid), None)


# --- QR -----------------------------------------------------------------------
def _qr_png(data: str) -> bytes | None:
    """URL-ийг кодолсон QR-ийн PNG bytes — модулиуд нь **бөөрөнхий** булантай.
    qrcode суулгасан бол локалаар (StyledPilImage + RoundedModuleDrawer), эс бол
    qrserver.com-оор (интернет шаардлагатай). Алдвал None."""
    try:
        import qrcode  # type: ignore
        from qrcode.image.styledpil import StyledPilImage
        from qrcode.image.styles.moduledrawers.pil import RoundedModuleDrawer

        qr = qrcode.QRCode(border=1, box_size=16,
                           error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(image_factory=StyledPilImage,
                            module_drawer=RoundedModuleDrawer())
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        pass
    except Exception as exc:  # noqa: BLE001
        print("local rounded QR failed:", exc)
    try:
        # qrserver: бөөрөнхий модуль дэмждэггүй тул fallback (хурц) хувилбар.
        url = ("https://api.qrserver.com/v1/create-qr-code/?size=600x600&margin=2&data="
               + urllib.parse.quote(data, safe=""))
        with urllib.request.urlopen(url, timeout=8) as resp:
            return resp.read()
    except Exception as exc:  # noqa: BLE001
        print("qrserver QR failed:", exc)
        return None


# --- Бөглөх -------------------------------------------------------------------
def _fit_size(font: fitz.Font, text: str, max_w: float, start: float, floor: float = 6.0) -> float:
    size = start
    while size > floor and font.text_length(text, fontsize=size) > max_w:
        size -= 0.5
    return size


def fill_ai_certificate(student: dict, base_url: str = "") -> bytes:
    """Суралцагчийн мэдээллээр AIEngineer.pdf-ийг бөглөж PDF (bytes) буцаана."""
    if not TEMPLATE.exists():
        raise FileNotFoundError(f"Template not found: {TEMPLATE}")

    name_font_path = _pick_font(NAME_FONT_CANDIDATES)
    body_font_path = _pick_font(BODY_FONT_CANDIDATES)
    if not name_font_path or not body_font_path:
        raise RuntimeError("Certificate fonts not found; set CERT_NAME_FONT / CERT_BODY_FONT")

    student_id = str(student.get("student_id") or "").strip()
    first_name = (student.get("first_name") or "").strip()
    last_name = (student.get("last_name") or "").strip()
    capstone = (student.get("project_name_en") or "").strip()

    doc = fitz.open(str(TEMPLATE))
    pg = doc[0]

    # --- Placeholder-уудыг динамикаар олох (template өөрчлөгдсөн ч мөрдөнө) ---
    cert_no_rect = _find_rect(pg, "#certificate_no", _CERT_NO_RECT)
    fn_rect = _find_rect(pg, "#firstname", None)
    ln_rect = _find_rect(pg, "#lastname", None)
    if fn_rect and ln_rect:
        name_rect = fitz.Rect(min(fn_rect.x0, ln_rect.x0), min(fn_rect.y0, ln_rect.y0),
                              max(fn_rect.x1, ln_rect.x1), max(fn_rect.y1, ln_rect.y1))
    else:
        name_rect = fn_rect or ln_rect or _NAME_RECT
    date_rect = _find_rect(pg, "#date", _DATE_RECT)
    # Нэрийн redaction нь "is hereby awarded to" мөртэй огтолж түүнийг устгахаас
    # сэргийлж, redaction-ийн дээд хязгаарыг тэр мөрийн доор шахна.
    awarded = _find_rect(pg, "is hereby awarded to", None)
    name_top = name_rect.y0
    if awarded and awarded.y1 > name_rect.y0:
        name_top = awarded.y1 + 1.5

    # 1) Placeholder текстийг устгах (redaction). fill=False → доорх цаас (сул
    #    градиент/текстур) хэвээр харагдана; цагаанаар дүүргэвэл бүдэг тэгш өнцөгт
    #    үлдэнэ.
    pg.add_redact_annot(cert_no_rect, fill=False)
    pg.add_redact_annot(fitz.Rect(name_rect.x0, name_top, name_rect.x1, name_rect.y1),
                        fill=False)
    pg.add_redact_annot(
        fitz.Rect(_CAPSTONE_VALUE_X0 - 1.5, _CAPSTONE_LINE.y0 - 1,
                  _CAPSTONE_LINE.x1 + 2, _CAPSTONE_LINE.y1 + 1),
        fill=False,
    )
    pg.add_redact_annot(date_rect, fill=False)
    # Жишээ QR-ийг арилгах (доор нь шинэ QR тавина).
    pg.add_redact_annot(_QR_RECT, fill=False)
    pg.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

    body_font = fitz.Font(fontfile=body_font_path)
    name_font = fitz.Font(fontfile=name_font_path)
    date_font_path = _pick_font(DATE_FONT_CANDIDATES) or body_font_path
    date_font = fitz.Font(fontfile=date_font_path)

    # 2) #certificate_no — Open Sans 14, төвлөрсөн (baseline нь placeholder-ийн доод хэсэг).
    cx = (cert_no_rect.x0 + cert_no_rect.x1) / 2
    tw = body_font.text_length(student_id, fontsize=_CERT_NO_SIZE)
    pg.insert_text((cx - tw / 2, cert_no_rect.y1 - 4.2), student_id,
                   fontfile=body_font_path, fontname="osbody",
                   fontsize=_CERT_NO_SIZE, color=INK)

    # 3) Нэр овог — Liana, төвлөрсөн; placeholder-ийн голд, доод захаас жоохон дээш.
    full_name = (first_name + " " + last_name).strip()
    name_cx = (name_rect.x0 + name_rect.x1) / 2
    nsize = _fit_size(name_font, full_name, name_rect.width - 8, _NAME_SIZE, floor=20.0)
    ntw = name_font.text_length(full_name, fontsize=nsize)
    pg.insert_text((name_cx - ntw / 2, name_rect.y1 - 12.0), full_name,
                   fontfile=name_font_path, fontname="cname",
                   fontsize=nsize, color=INK)

    # 4) #capstone_topic — Open Sans 12, "Capstone project: "-ийн ард.
    if capstone:
        # Утга нь placeholder-ийн богино мөрөөр биш, баруун захад (x≈788) хүртэл
        # сунаж болно; урт бол л багасгана (10pt-ээс доошгүй).
        max_w = _CAPSTONE_VALUE_X1 - _CAPSTONE_VALUE_X0
        csize = _fit_size(body_font, capstone, max_w, _CAPSTONE_SIZE, floor=10.0)
        pg.insert_text((_CAPSTONE_VALUE_X0, _CAPSTONE_LINE.y1 - 3.2), capstone,
                       fontfile=body_font_path, fontname="oscap",
                       fontsize=csize, color=INK)

    # 5) #date — хэвлэж буй өдрөөс өмнөх өдөр (yesterday), төвлөрсөн, BoldItalic 17.
    yday = date.today() - timedelta(days=1)
    date_str = f"{yday.strftime('%B')} {yday.day}, {yday.year}"
    dtw = date_font.text_length(date_str, fontsize=_DATE_SIZE)
    dcx = (date_rect.x0 + date_rect.x1) / 2
    pg.insert_text((dcx - dtw / 2, date_rect.y1 - 9.0), date_str,
                   fontfile=date_font_path, fontname="osdate",
                   fontsize=_DATE_SIZE, color=INK)

    # 6) QR — id-аар API дуудахгүй; сертификатын мэдээллийг өөрт нь агуулсан,
    #    HMAC-аар баталгаажсан токеныг лавлагааны хуудас руу кодолно.
    token = make_cert_token({
        "no": student_id, "fn": first_name, "ln": last_name,
        "cap": capstone, "dt": date_str,
    })
    root = base_url.rstrip("/") if base_url else ""
    verify_url = f"{root}/contract/cert/verify?t={urllib.parse.quote(token, safe='')}"
    png = _qr_png(verify_url)
    if png:
        pg.insert_image(_QR_RECT, stream=png, keep_proportion=True)

    return doc.write(deflate=True, garbage=3)
