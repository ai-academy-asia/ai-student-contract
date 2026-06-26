# AI Asia — Сургалтын гэрээ (FastAPI)

Суралцагч линкээрээ орж, мэдээллээ шалгаад, гэрээгээ урьдчилан хараад, гарын үсэг
зурж, бөглөгдсөн PDF-ээ татаж авдаг систем. Гэрээний араас classCode-д тохирох
хичээлийн хөтөлбөр автоматаар залгагдана.

> Бүхэлдээ **Python (FastAPI + PyMuPDF)** дээр. Node.js / Next.js хэрэглэхгүй.
> (Хуучин Next.js хувилбар `legacy_nextjs/`-д хадгалагдсан.)

## Суулгах

```bash
python3 -m pip install -r requirements.txt
# (Times New Roman фонт байхгүй орчинд: PDF_FONT=<crillic .ttf зам> тохируулна)
```

## Өгөгдлийн сан (PostgreSQL)

Гэрээ үүсгэх бүрд хэрэглэгчийн мэдээлэл, **PDF файл**, **гарын үсэг** хадгалагдана.

```bash
export DATABASE_URL="postgresql://<user>:<pass>@<host>:5432/contract_db"
# default: postgresql://admin:admin123@localhost:5432/contract_db (локал Docker)
```

- Хүснэгт `contracts` нь эхлэхэд автоматаар үүснэ (`db.init_db`).
- PDF → `storage/pdfs/`, гарын үсэг → `storage/signatures/` (зам нь DB-д бичигдэнэ).
- DB байхгүй/унтарсан үед апп ажилласаар (хадгалалт алгасна, PDF татагдсаар).

## Ажиллуулах

```bash
uvicorn contract_app.app:app --host 0.0.0.0 --port 8000
```

Дараа нь линк: `http://localhost:8000/contract/<student-id>` (ж: `/contract/6041ba91`).

## Бүтэц

```
contract_app/
  app.py            # FastAPI — маршрутууд (/contract/{id}, /api/student, /api/preview, /api/generate)
  fill.py           # PDF бөглөх логик (PyMuPDF) — build_values, program_pdf, fill_contract
  students.py       # data/students.json уншина
  templates/contract.html   # хуудасны бүрхүүл (Tailwind + signature_pad CDN)
  static/app.js     # 4 алхмын урсгал, validation, гарын үсэг (vanilla JS)
public/templates/
  contract.pdf      # placeholder-тай гэрээний загвар (#snake_case + <COVERAGE_PROGRAM>)
  programs/<classCode>.pdf  # ангийн хичээлийн хөтөлбөр (бүлгийн prefix-ээр ч таарна)
data/students.json  # суралцагчдын мэдээлэл
```

## Онцлог
- Бөглөсөн талбарууд **тод (bold) + ТОМ үсгээр**.
- Нэрс/хаягт **зөвхөн крилл** (латин үсэг автоматаар хасагдана).
- Хөнгөлөлтийн хувь **(3,560,000 − tolokhDun)/3,560,000**-аар автоматаар бодогдоно.
- Эцсийн төлөх огноо **2026-06-15 .. 2026-07-06** хооронд.
- Гэрээний дугаар = суралцагчийн `num`.
- Гарын үсэг ил тод дэвсгэртэйгээр зураасан дээр тавигдана.
- Урт хаяг дараагийн текст рүү давахгүй (фонт автоматаар багтана).
