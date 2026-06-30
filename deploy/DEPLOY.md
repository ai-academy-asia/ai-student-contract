# Deploy заавар — AI Academy гэрээний апп

Сервер: Ubuntu/Debian, nginx + PostgreSQL + домэйн (`ai-academy.asia`) бэлэн.
Апп нь **порт 8090** дээр ажиллана (8000 нь Node.js backend-д эзлэгдсэн).
Доорх `<...>`-уудыг өөрийн утгаар солино.

---

## 0. Системийн хамаарал (серверт, нэг удаа)

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip fonts-liberation rsync
# (PostgreSQL, nginx аль хэдийн суусан)
```
`fonts-liberation` — PDF дээрх крилл фонтод заавал хэрэгтэй.

---

## 1. Төслийг сервер рүү хуулах

Серверт хавтас үүсгэх (root-аар):
```bash
mkdir -p /root/backend/ai-asia-contract
```

**Локал компьютер дээрээс** (төслийн хавтсанд байж):

```bash
rsync -avz --delete \
  --exclude '.git' --exclude '.venv' --exclude 'storage' \
  --exclude 'data.csv' --exclude '__pycache__' --exclude '.DS_Store' \
  ./ root@161.97.136.164:/root/backend/ai-asia-contract/
```

---

## 2. PostgreSQL — хэрэглэгч + сан үүсгэх (серверт)

```bash
sudo -u postgres psql <<'SQL'
CREATE USER contract WITH PASSWORD 'T3nger*';
CREATE DATABASE contract_db OWNER contract;
GRANT ALL PRIVILEGES ON DATABASE contract_db TO contract;
SQL
```

> Хүснэгт (`students`, `contracts`) болон `students.json` seed нь апп **анх асахад
> автоматаар** үүснэ — гараар юу ч хийх шаардлагагүй.

Холболтоо шалгах:
```bash
psql "postgresql://contract:<db-password>@localhost:5432/contract_db" -c '\dt'
```

---

## 3. Python venv + хамаарал суулгах (серверт)

```bash
cd /root/backend/ai-asia-contract
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

---

## 4. Тохиргоо (.env)

```bash
cp .env.example .env
nano .env
```
```ini
DATABASE_URL=postgresql://contract:T3nger*@localhost:5432/contract_db
PUBLIC_BASE_URL=https://ai-academy.asia
```

---

## 5. Гараар туршиж үзэх

```bash
cd /root/backend/ai-asia-contract
set -a; . ./.env; set +a
.venv/bin/uvicorn contract_app.app:app --host 127.0.0.1 --port 8090
```
Өөр терминалд:
```bash
curl http://127.0.0.1:8090/health                 # {"status":"ok"}
curl -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8090/contract/3d7efe97
```
Дараа нь `Ctrl+C`-ээр зогсооно.

---

## 6. systemd сервис (байнгын ажиллагаа + автостарт)

Сервис нь **root**-аар, `/root/backend/ai-asia-contract`-д ажиллана (root эзэмшдэг тул
нэмэлт эрх тохируулах шаардлагагүй).

```bash
cp /root/backend/ai-asia-contract/deploy/ai-contract.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now ai-contract
systemctl status ai-contract           # active (running) байх ёстой
journalctl -u ai-contract -n 30 --no-pager   # "seeded N students" лог харагдана
```

> `deploy/ai-contract.service`: `User=root`, `WorkingDirectory=/root/backend/ai-asia-contract`,
> `EnvironmentFile=.../.env`, порт **8090**, `--workers 2`.

---

## 7. nginx — `/contract` чиглүүлэлт нэмэх

`/etc/nginx/conf.d/ai-academy.asia.ssl.conf` доторх **`listen 443 ssl`** server
блокийн `location / { …:3000 }`-ийн **ДЭЭР** дараахыг нэмнэ:

```nginx
location ^~ /contract/ {
    proxy_pass http://127.0.0.1:8090;        # trailing slash БАЙХГҮЙ!
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 60s;
}
```
```bash
sudo nginx -t && sudo systemctl reload nginx
```

---

## 8. Бүрэн шалгах

```bash
curl -o /dev/null -w "%{http_code}\n" https://ai-academy.asia/contract/<student-id>
```
Браузераар `https://ai-academy.asia/contract/<student-id>` нээж: мэдээлэл бөглөх →
гэрээ харах → гарын үсэг зурах → PDF татах. PDF/гарын үсэг `/root/backend/ai-asia-contract/storage/`-д,
мэдээлэл + `contract_link` PostgreSQL-д хадгалагдана.

---

## 9. Шинэчлэлт хийх

```bash
# локалаас дахин хуулах (1-р алхам шиг) дараа серверт:
cd /root/backend/ai-asia-contract
.venv/bin/pip install -r requirements.txt   # шинэ хамаарал байвал
systemctl restart ai-contract
```
> rsync хийхдээ `--exclude 'storage'`, `--exclude '.venv'`, `--exclude '.env'` хадгалагдсан
> мэдээлэл/тохиргоог дарж бичихгүй гэдгийг анхаар.

## Тусламж (алдаа гарвал)
- `journalctl -u ai-contract -f` — аппын лог.
- `DB init failed ...` гарвал `.env`-ийн `DATABASE_URL` болон Postgres ажиллаж буйг шалга.
- PDF дээр крилл харагдахгүй бол `fonts-liberation` суусан эсэх, эсвэл `.env`-д
  `PDF_FONT=<crillic .ttf зам>` зааж өг.
- Порт зөрчил: 8090 чөлөөтэй эсэх — `ss -ltnp | grep 8090`.
