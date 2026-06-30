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

## Ажиллуулах (локал)

```bash
uvicorn contract_app.app:app --host 0.0.0.0 --port 8000
```

Дараа нь линк: `http://localhost:8000/contract/<student-id>` (ж: `/contract/6041ba91`).

## Deploy (Docker-гүй, шууд серверт)

Аппын бүх зам `/contract` угтвар дор байрладаг (`/contract/<id>`, `/contract/_api/*`,
`/contract/_static/*`). Тиймээс **гол домэйн дээрх академийн сайттай мөргөлдөхгүй** —
nginx-д ганцхан `location /contract/` нэмэхэд хангалттай.

```bash
# 1) Крилл фонт (PDF-д заавал) — Postgres/nginx аль хэдийн байгаа гэж үзвэл зөвхөн энэ
sudo apt install -y python3-venv fonts-liberation

# 2) PostgreSQL дотор сан (одоо байгаа Postgres-д)
sudo -u postgres psql -c "CREATE USER contract WITH PASSWORD 'хүчтэй_нууцүг';"
sudo -u postgres psql -c "CREATE DATABASE contract_db OWNER contract;"

# 3) Код + venv
sudo mkdir -p /opt/ai-asia-contract && sudo chown $USER /opt/ai-asia-contract
cd /opt/ai-asia-contract          # төслөө энд хуулна
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env              # DATABASE_URL, PUBLIC_BASE_URL=https://ai-academy.asia

# 4) systemd сервис (127.0.0.1:8000)
sudo cp deploy/ai-contract.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ai-contract
journalctl -u ai-contract -f
```

> ⚠️ Порт **8000 нь Node.js backend-д аль хэдийн эзлэгдсэн**. Гэрээний апп **8090**
> дээр ажиллана (systemd-д тохируулсан). Чөлөөтэй өөр порт сонгож болно.

### nginx (одоо байгаа 443 блокт нэмэх)

`/etc/nginx/conf.d/ai-academy.asia.ssl.conf` доторх `listen 443 ssl`-ийн server блок
(`location / → 3000`-ийн дээр) `deploy/nginx-ai-contract.conf`-ийн `location ^~ /contract/`
блокийг нэмнэ → `proxy_pass http://127.0.0.1:8090;` (trailing slash БАЙХГҮЙ):

```bash
sudo nginx -t && sudo systemctl reload nginx
```

`/contract/_api/*`, `/contract/_static/*` бүгд `/contract/` доор тул танай `/api/` (8000),
`/auth/`, `/payment/`, `/` (Next.js) зэрэгтэй мөргөлдөхгүй.

Эхлэхэд хүснэгт + `students.json` seed автоматаар хийгдэнэ. PDF/гарын үсэг `./storage`-д,
DB-д мэдээлэл + `contract_link`. Шинэчлэлт: `git pull && .venv/bin/pip install -r requirements.txt && sudo systemctl restart ai-contract`.

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
