"""
Гэрээний PDF template (`public/templates/contract.pdf`)-ийн `#snake_case` / `<TOKEN>`
placeholder-уудыг хэрэглэгчийн утгаар бөглөж, гарын үсгийн зургийг тавьж, classCode-д
тохирох хичээлийн хөтөлбөрийг араас нь залгана. Бүх логик нэг газар, in-process.
"""
from __future__ import annotations

import os
import re
import base64
from pathlib import Path

import fitz  # PyMuPDF

# ── Замууд ───────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "public" / "templates" / "contract.pdf"
PROGRAMS_DIR = ROOT / "public" / "templates" / "programs"

# Бөглөсөн утгууд BOLD-оор гарна — крилл дэмждэг bold фонт сонгоно.
# (macOS дээр Times New Roman, Linux/Docker дээр Liberation/DejaVu — PDF_FONT-оор дарж болно)
FONT_CANDIDATES = [
    os.environ.get("PDF_FONT", ""),
    # macOS
    "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
    # Linux (Docker) — fonts-liberation (Times-metric, Cyrillic) / fonts-dejavu
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]

SIG_TOKEN = "#signature"        # гарын үсэг тавих placeholder
BASE_FEE = 3_560_000            # нийт төлбөр — хөнгөлөлтийг үүнээс тооцно


# ── Утга бэлдэх туслахууд ─────────────────────────────────────────────────────
def _font_path() -> str:
    for p in FONT_CANDIDATES:
        if p and os.path.exists(p):
            return p
    raise RuntimeError("No Cyrillic font found; set PDF_FONT env var")


def _pad(s: str) -> str:
    return (s or "").rjust(2, "0")


def _money(value: str | None) -> str:
    v = (value or "").strip()
    if not v or v == "-":
        return "—"
    return re.sub(r"₮?$", "", v) + "₮"


def _to_number(value: str | None) -> int:
    digits = re.sub(r"[^\d]", "", value or "")
    return int(digits) if digits else 0


def discount_pct(tolokh_dun: str | None) -> str:
    """Хөнгөлөлтийн хувь = (3,560,000 − tolokhDun) / 3,560,000."""
    t = _to_number(tolokh_dun)
    if not t or t >= BASE_FEE:
        return "0%"
    return f"{round((BASE_FEE - t) / BASE_FEE * 100)}%"


def _contract_no_fallback(seed: str) -> str:
    m = re.search(r"\d+", seed or "")
    digits = m.group(0) if m else ""
    return (digits[-4:] or "0001").rjust(4, "0")


def program_pdf(class_code: str | None) -> str:
    """
    classCode-д тохирох хөтөлбөрийн PDF зам.
    1) яг `<classCode>.pdf`, 2) байхгүй бол насны бүлгийн (`^Summer\\d{2}`) файл.
    """
    if not class_code:
        return ""
    exact = PROGRAMS_DIR / f"{class_code}.pdf"
    if exact.exists():
        return str(exact)
    m = re.match(r"^Summer\d{2}", class_code)
    if m and PROGRAMS_DIR.exists():
        group = m.group(0)
        for f in sorted(os.listdir(PROGRAMS_DIR)):
            if f.endswith(".pdf") and f.startswith(group):
                return str(PROGRAMS_DIR / f)
    return ""


def build_values(form: dict, finance: dict, program: str | None,
                 num: str | None, today: str) -> dict:
    """Form өгөгдлийг template-ийн literal placeholder token-уудад буулгана."""
    f = form or {}
    fin = finance or {}
    parts = (today or "").split("-")
    month = parts[1] if len(parts) > 1 else ""
    day = parts[2] if len(parts) > 2 else ""
    return {
        "#month": _pad(month),
        "#day": _pad(day),
        "#contact_name": (num or "").strip() or _contract_no_fallback(
            f.get("register") or f.get("guardianRegister") or ""),
        "#last_name": f.get("lastName", ""),
        "#first_name": f.get("firstName", ""),
        "#register": f.get("register", ""),
        "#g_relation": f.get("guardianRelation", ""),
        "#address_detail": f.get("addressDetail", ""),
        "#g_last_name": f.get("guardianLastName", ""),
        "#g_first_name": f.get("guardianFirstName", ""),
        "#g_register": f.get("guardianRegister", ""),
        "<COVERAGE_PROGRAM>": program or "Summer Bootcamp 10-13",
        "#discount": discount_pct(fin.get("tolokhDun")),
        "#advance": _money(fin.get("tolson")),
        "#balance": _money(fin.get("uldegdel")),
        "#final_payment_date": (f.get("finalPaymentDate", "") or "").replace("-", "."),
        "#phone": f.get("guardianPhone", ""),
        "#email": f.get("guardianEmail", ""),
    }


# ── Гарын үсгийн зураг — цагаан дэвсгэрийг ил тод болгох ───────────────────────
def _transparent_png(raw: bytes) -> bytes:
    pix = fitz.Pixmap(raw)
    if pix.colorspace and pix.colorspace.name != fitz.csRGB.name:
        pix = fitz.Pixmap(fitz.csRGB, pix)
    w, h = pix.width, pix.height
    s = pix.samples
    mask = bytearray(w * h)
    WHITE = 235
    if pix.alpha:  # RGBA
        for i in range(w * h):
            r, g, b, a = s[i * 4], s[i * 4 + 1], s[i * 4 + 2], s[i * 4 + 3]
            mask[i] = 0 if (a == 0 or (r >= WHITE and g >= WHITE and b >= WHITE)) else a
    else:          # RGB
        for i in range(w * h):
            r, g, b = s[i * 3], s[i * 3 + 1], s[i * 3 + 2]
            mask[i] = 0 if (r >= WHITE and g >= WHITE and b >= WHITE) else 255
        pix = fitz.Pixmap(pix, 1)
    pix.set_alpha(bytes(mask))
    return pix.tobytes("png")


# ── PDF бөглөх гол функц ───────────────────────────────────────────────────────
def fill_contract(values: dict, signature_b64: str | None = None,
                  append_path: str | None = None) -> bytes:
    font = _font_path()
    measure = fitz.Font(fontfile=font)
    doc = fitz.open(str(TEMPLATE))

    def fit_size(text: str, base: float, x0: float, right_bound: float | None) -> float:
        """Текст дараагийн үг рүү давах бол фонтыг багасгаж багтаана."""
        if not right_bound:
            return base
        avail = right_bound - x0 - 2
        if avail <= 0:
            return base
        w = measure.text_length(text, fontsize=base)
        if w <= avail:
            return base
        return max(round(base * avail / w, 1), 3.0)

    inserts = []   # (page, x, baseline, text, size)
    sig_rects = []

    for pno in range(doc.page_count):
        pg = doc[pno]
        words = pg.get_text("words")
        for token, val in values.items():
            if val is None:
                val = ""
            rects = pg.search_for(token)
            if not rects:
                continue
            text = str(val).upper()  # бөглөсөн утга — UPPERCASE
            for r in rects:
                pg.add_redact_annot(r, fill=(1, 1, 1))
                rights = [w[0] for w in words if abs(w[1] - r.y0) < 3 and w[0] >= r.x1 - 0.5]
                rb = min(rights) if rights else None
                base = round((r.y1 - r.y0) * 0.86, 1)
                size = fit_size(text, base, r.x0, rb)
                baseline = r.y1 - (r.y1 - r.y0) * 0.22
                inserts.append((pno, r.x0, baseline, text, size))

        for r in pg.search_for(SIG_TOKEN):
            pg.add_redact_annot(r, fill=(1, 1, 1))
            sig_rects.append((pno, r))

    for pno in range(doc.page_count):
        doc[pno].apply_redactions()

    for (pno, x, by, text, size) in inserts:
        if text == "":
            continue
        doc[pno].insert_text((x, by), text, fontfile=font, fontname="tnrb",
                             fontsize=size, color=(0, 0, 0))

    if signature_b64:
        try:
            png = _transparent_png(base64.b64decode(signature_b64.split(",")[-1]))
            for (pno, r) in sig_rects:
                box = fitz.Rect(r.x0 - 60, r.y0, r.x0 + 150, r.y1 + 34)
                doc[pno].insert_image(box, stream=png, keep_proportion=True, overlay=True)
        except Exception as e:  # corrupt signature shouldn't block the contract
            print("signature insert skipped:", e)

    if append_path and os.path.exists(append_path):
        try:
            with fitz.open(append_path) as prog:
                doc.insert_pdf(prog)
        except Exception as e:
            print("program append skipped:", e)

    return doc.write(deflate=True, garbage=3)
