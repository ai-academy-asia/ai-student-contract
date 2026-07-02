"""
Сертификат (Certificate of Completion) бөглөх.

`public/templates/certificates/`-д байрлах Canva-аас гаргасан загвар дээрх
`#firstname` / `#lastname` / `#date` placeholder-уудыг солино. Загвар Type3
(subset) фонттой тул placeholder-ыг устгаж чадахгүй — иймд тэдгээрийн дэвсгэрийг
(хэвтээ градиентийг) дахин сэргээж бүрхээд, дээр нь шинэ нэрийг гоёмсог script
фонтоор, огноог бүдүүн фонтоор бичнэ. Бусад зүйлийг огт өөрчлөхгүй.

classCode → загвар: program_pdf-тэй адил `^Summer\\d{2}` бүлгээр шийднэ
(Summer18* → 10-14 visual/Scratch, Summer13* → 14-18 Python/Vibe coding).
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime
from pathlib import Path

import fitz  # PyMuPDF

ROOT = Path(__file__).resolve().parent.parent
CERT_DIR = ROOT / "public" / "templates" / "certificates"

# Нэр — гоёмсог бичгийн (script) фонт; огноо — бүдүүн фонт. Эхэнд env-ээр дарж болно.
SCRIPT_FONT_CANDIDATES = [
    os.environ.get("CERT_SCRIPT_FONT", ""),
    "/System/Library/Fonts/Supplemental/SnellRoundhand.ttc",          # macOS
    "/System/Library/Fonts/Supplemental/Savoye LET.ttc",
    "/usr/share/fonts/opentype/urw-base35/Z003-MediumItalic.otf",     # Linux (fonts-urw-base35)
    "/usr/share/fonts/truetype/freefont/FreeSerifItalic.ttf",
]
DATE_FONT_CANDIDATES = [
    os.environ.get("CERT_DATE_FONT", ""),
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",             # macOS
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",           # Linux
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]

NAVY = (0 / 255, 15 / 255, 49 / 255)

# Layout — AI Academy "Certificate of Completion" загварт тааруулсан (2115×2992).
# Нэрийн мөр "is hereby awarded to" (≤y1186) ба доорх зураас (y1356)-ийн хооронд.
_NX0, _NX1, _NY0, _NY1 = 402, 1556, 1190, 1354
_SAMPLE_ROWS = (1187, 1188, 1189)        # нэрийн хайрцагнаас дээх цэвэр дэвсгэр мөрүүд
_NAME_MAXW = 1380
_NAME_BASELINE = 1294
_DATE_BASELINE = 2879

# Монгол кирилл → латин (жишээ файлуудтай — Neguun Purevdorj, Tsetsenbileg — тааруулсан)
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "j", "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "ө": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ү": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh",
    "щ": "sh", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def _pick_font(candidates: list[str]) -> str | None:
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return None


def _clean(s: str | None) -> str:
    s = (s or "").strip()
    s = re.sub(r"\(.*?\)", "", s)        # тайлбар хасах: "(Asral egch)"
    s = s.split("/")[0]                  # "Удвал /Уугий" → эхнийх
    return re.sub(r"\s+", " ", s).strip()


def transliterate(s: str | None) -> str:
    """Кирилл нэрийг латинаар, үг бүрийн эхний үсгийг том болгож буцаана."""
    out = "".join(_TRANSLIT.get(ch, ch) for ch in _clean(s).lower())
    return re.sub(r"(^|[\s\-])([a-z])", lambda m: m.group(1) + m.group(2).upper(), out)


def latin_full_name(first_name: str | None, last_name: str | None) -> str:
    """#firstname #lastname форматтай: <Нэр> <Овог> (латинаар)."""
    return (transliterate(first_name) + " " + transliterate(last_name)).strip()


def certificate_pdf(class_code: str | None) -> str:
    """classCode-д тохирох сертификатын загварын зам (`program_pdf`-тэй адил логик)."""
    if not class_code:
        return ""
    exact = CERT_DIR / f"{class_code}.pdf"
    if exact.exists():
        return str(exact)
    m = re.match(r"^Summer\d{2}", class_code)
    if m and CERT_DIR.exists():
        group = m.group(0)
        for f in sorted(os.listdir(CERT_DIR)):
            if f.endswith(".pdf") and f.startswith(group):
                return str(CERT_DIR / f)
    return ""


def _fmt_date(today: str | None) -> str:
    """ISO огноог 'June 30' болгоно (загвар дотор ', 2026' нь хэвээр үлдэнэ)."""
    try:
        d = datetime.strptime((today or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        d = date.today()
    return f"{d.strftime('%B')} {d.day}"


def fill_certificate(class_code: str | None, first_name: str | None,
                     last_name: str | None, today: str | None = None) -> bytes:
    """classCode-д тохирох загварыг хүүхдийн нэр/огноогоор бөглөж PDF (bytes) буцаана."""
    template = certificate_pdf(class_code)
    if not template:
        raise FileNotFoundError(f"No certificate template for classCode={class_code!r}")

    name = latin_full_name(first_name, last_name)
    date_str = _fmt_date(today)
    script_font = _pick_font(SCRIPT_FONT_CANDIDATES)
    date_font = _pick_font(DATE_FONT_CANDIDATES)
    if not script_font or not date_font:
        raise RuntimeError("Certificate fonts not found; set CERT_SCRIPT_FONT / CERT_DATE_FONT")

    doc = fitz.open(template)
    pg = doc[0]
    pix = pg.get_pixmap()
    n, w, s = pix.n, pix.width, pix.samples

    def bg(x, y):
        k = (int(y) * w + int(x)) * n
        return s[k], s[k + 1], s[k + 2]

    # 1) placeholder-ыг дэвсгэрээр бүрхэх: бүтэн бүрхэвч + хэвтээ градиентийг сэргээх
    cols = [max(bg(x, y) for y in _SAMPLE_ROWS) for x in range(_NX0, _NX1)]
    avg = tuple(sum(c[i] for c in cols) / len(cols) / 255 for i in range(3))
    pg.draw_rect(fitz.Rect(_NX0, _NY0, _NX1, _NY1), color=None, fill=avg)
    for i, x in enumerate(range(_NX0, _NX1)):
        r, g, b = cols[i]
        pg.draw_rect(fitz.Rect(x, _NY0, x + 1.4, _NY1), color=None,
                     fill=(r / 255, g / 255, b / 255))

    # #date-г яг бүрхэх (', 2026'-г хэвээр)
    dr = pg.search_for("#date")[0]
    comma = pg.search_for(", 2026")[0]
    dbg = bg(dr.x0 - 8, (dr.y0 + dr.y1) / 2)
    pg.draw_rect(fitz.Rect(dr.x0 - 4, dr.y0 - 7, dr.x1 + 0.5, dr.y1 + 8),
                 color=None, fill=tuple(c / 255 for c in dbg))

    # 2) нэр — голлуулж, script фонтоор (урт нэр бол багасгаж багтаана)
    sf = fitz.Font(fontfile=script_font)
    nsize = 108.0
    while nsize > 40 and sf.text_length(name, fontsize=nsize) > _NAME_MAXW:
        nsize -= 1
    tw = sf.text_length(name, fontsize=nsize)
    pg.insert_text((pg.rect.width / 2 - tw / 2, _NAME_BASELINE), name,
                   fontfile=script_font, fontname="cscript", fontsize=nsize, color=NAVY)

    # огноо — #date-ийн эхэлж байсан байрлалд, бүдүүн фонтоор, таслалд хүртэл багтаах
    df = fitz.Font(fontfile=date_font)
    maxw = comma.x0 - dr.x0 - 6
    dsize = 32.0
    while dsize > 8 and df.text_length(date_str, fontsize=dsize) > maxw:
        dsize -= 0.5
    pg.insert_text((dr.x0, _DATE_BASELINE), date_str,
                   fontfile=date_font, fontname="cdate", fontsize=dsize, color=NAVY)

    return doc.write(deflate=True, garbage=3)
