/* AI Academy Asia — сургалтын гэрээ. Нэг хуудаст урсгал (vanilla JS, light theme).
   Алхмууд: Мэдээлэл шалгах → Гэрээ харах → Гарын үсэг → Дуусгах. */

// Бүх API/static нь `/contract` угтвар дор (nginx-ийн нэг location-д тааруулсан)
const API = "/contract/_api";
const STATIC = "/contract/_static";

const STEPS = ["Мэдээлэл шалгах", "Гэрээ харах", "Гарын үсэг", "Дуусгах"];

const FINAL_PAYMENT_MIN = "2026-06-15";
const FINAL_PAYMENT_MAX = "2026-07-06";

const CYRILLIC_FIELDS = ["lastName", "firstName", "guardianRelation",
  "guardianLastName", "guardianFirstName", "addressDetail"];

const EMPTY_FORM = {
  lastName: "", firstName: "", register: "",
  guardianRelation: "", guardianLastName: "", guardianFirstName: "",
  guardianRegister: "", guardianPhone: "", guardianEmail: "",
  addressDetail: "", finalPaymentDate: "",
};

const STUDENT_FIELDS = [
  { key: "lastName",  label: "Овог",              type: "text",  ph: "Овог",            req: true, cyr: true },
  { key: "firstName", label: "Нэр",               type: "text",  ph: "Нэр",             req: true, cyr: true },
  { key: "register",  label: "Регистрийн дугаар", type: "text",  ph: "АА12345678",      req: true, hint: "2 монгол үсэг + 8 орон тоо" },
];
const GUARDIAN_FIELDS = [
  { key: "guardianRelation",  label: "Суралцагчтай ямар хамааралтай", type: "text",  ph: "эх / эцэг / асран хамгаалагч", req: true, cyr: true, hint: "“Суралцагчийн … болох” хэсэгт орно" },
  { key: "guardianLastName",  label: "Овог",                          type: "text",  ph: "Овог",            req: true, cyr: true },
  { key: "guardianFirstName", label: "Нэр",                           type: "text",  ph: "Нэр",             req: true, cyr: true },
  { key: "guardianRegister",  label: "Регистрийн дугаар",             type: "text",  ph: "АА12345678",      req: true, hint: "2 монгол үсэг + 8 орон тоо" },
  { key: "guardianPhone",     label: "Утасны дугаар",                 type: "tel",   ph: "99001234",        req: true, hint: "8 орон тоо" },
  { key: "guardianEmail",     label: "И-мэйл",                        type: "email", ph: "example@mail.com" },
];
const ADDRESS_FIELDS = [
  { key: "addressDetail", label: "Оршин суух хаяг", type: "text", ph: "Улаанбаатар хот, Сүхбаатар дүүрэг, 1-р хороо, ... байр, тоот", req: true, wide: true, cyr: true, hint: "Бүтэн хаягаа криллээр бичнэ үү" },
];
const PAYMENT_FIELDS = [
  { key: "finalPaymentDate", label: "Үлдэгдэл төлбөр төлөх сүүлийн хугацаа", type: "date", req: true, wide: true, min: FINAL_PAYMENT_MIN, max: FINAL_PAYMENT_MAX, hint: "6 сарын 15 – 7 сарын 6 хооронд" },
];

const FIELDS_BY_KEY = Object.fromEntries(
  [...STUDENT_FIELDS, ...GUARDIAN_FIELDS, ...ADDRESS_FIELDS, ...PAYMENT_FIELDS].map((f) => [f.key, f])
);

const RE_REGISTER = /^[Ѐ-ӿ]{2}\d{8}$/;
const RE_PHONE = /^\d{8}$/;
const RE_EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const state = {
  student: null, notFound: false, alreadySigned: false, step: 0,
  formData: { ...EMPTY_FORM }, errors: {},
  signature: null, agreed: false, loading: false,
};

const root = document.getElementById("root");
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const todayISO = () => new Date().toISOString().split("T")[0];
const isDebt = (v) => v && v !== "-" && v !== "(0)" && !v.startsWith(" -");
const normalizeRegister = (v) => (v.length <= 2 ? v.toUpperCase() : v.slice(0, 2).toUpperCase() + v.slice(2));

// ── Эхлэл: суралцагчийн мэдээлэл татах ────────────────────────────────────────
fetch(`${API}/student/${window.SLUG}`)
  .then((r) => r.json())
  .then((data) => {
    if (data.error) { state.notFound = true; render(); return; }
    state.student = data;
    if (data.alreadySigned) { state.alreadySigned = true; render(); return; }
    state.formData = {
      ...EMPTY_FORM,
      lastName: data.lastName || "", firstName: data.firstName || "",
      // бүртгэлд хадгалсан холбоо барих утас/и-мэйлийг асран хамгаалагчийнхад урьдчилан бөглөнө
      guardianPhone: data.phone || "", guardianEmail: data.email || "",
    };
    render();
  })
  .catch(() => { state.notFound = true; render(); });

// ── Validation ────────────────────────────────────────────────────────────────
function validate() {
  const f = state.formData, e = {};
  if (!f.lastName.trim()) e.lastName = "Овог оруулна уу";
  if (!f.firstName.trim()) e.firstName = "Нэр оруулна уу";
  if (!f.register.trim()) e.register = "Регистр оруулна уу";
  else if (!RE_REGISTER.test(f.register.trim())) e.register = "Формат буруу — жишээ: АА12345678";

  if (!f.guardianRelation.trim()) e.guardianRelation = "Хамаарлыг оруулна уу";
  if (!f.guardianLastName.trim()) e.guardianLastName = "Овог оруулна уу";
  if (!f.guardianFirstName.trim()) e.guardianFirstName = "Нэр оруулна уу";
  if (!f.guardianRegister.trim()) e.guardianRegister = "Регистр оруулна уу";
  else if (!RE_REGISTER.test(f.guardianRegister.trim())) e.guardianRegister = "Формат буруу — жишээ: АА12345678";
  if (!f.guardianPhone.trim()) e.guardianPhone = "Утас оруулна уу";
  else if (!RE_PHONE.test(f.guardianPhone.trim())) e.guardianPhone = "Утасны дугаар 8 орон тоо байна";
  if (f.guardianEmail.trim() && !RE_EMAIL.test(f.guardianEmail.trim())) e.guardianEmail = "И-мэйл хаяг буруу байна";

  if (!f.addressDetail.trim()) e.addressDetail = "Оршин суух хаягаа оруулна уу";

  if (!f.finalPaymentDate.trim()) e.finalPaymentDate = "Эцсийн төлөх хугацааг оруулна уу";
  else if (f.finalPaymentDate < FINAL_PAYMENT_MIN || f.finalPaymentDate > FINAL_PAYMENT_MAX)
    e.finalPaymentDate = "Огноо 2026 оны 6 сарын 15 – 7 сарын 6 хооронд байх ёстой";

  for (const k of CYRILLIC_FIELDS)
    if (f[k].trim() && /[A-Za-z]/.test(f[k])) e[k] = "Зөвхөн криллээр бичнэ үү";

  state.errors = e;
  return Object.keys(e).length === 0;
}

// ── Алхмын шилжилт ────────────────────────────────────────────────────────────
function handleNext() {
  if (state.step === 0) { if (!validate()) { render(); return; } }
  if (state.step === 2) { if (!state.signature) { alert("Гарын үсэг зурна уу!"); return; } handleGenerate(); return; }
  state.step += 1; render();
}
function handleBack() { state.step -= 1; render(); }

async function handleGenerate() {
  const s = state.student;
  state.loading = true; render();
  try {
    const res = await fetch(`${API}/generate`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        studentId: s.id, classCode: s.classCode, program: s.program, num: s.num,
        formData: { ...state.formData, ognoo: todayISO() },
        finance: { tolokhDun: s.tolokhDun, tolson: s.tolson, uldegdel: s.uldegdel },
        signature: state.signature,
      }),
    });
    if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.error || "Алдаа гарлаа"); }
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a");
    a.href = url; a.download = `contract-${s.id}.pdf`;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
    state.step = 3;
  } catch (e) {
    alert(e.message || "Алдаа гарлаа");
  } finally {
    state.loading = false; render();
  }
}

// ── Талбар оруулах ────────────────────────────────────────────────────────────
function fieldHtml(fd) {
  const v = state.formData[fd.key];
  const err = state.errors[fd.key];
  return `
    <div class="${fd.wide ? "md:col-span-2" : ""}">
      <label class="block text-sm font-medium text-slate-700 mb-1.5">${esc(fd.label)}${fd.req ? '<span class="text-red-500 ml-1">*</span>' : ""}</label>
      <input data-key="${fd.key}" type="${fd.type}" value="${esc(v)}" placeholder="${esc(fd.ph || "")}"
        ${fd.min ? `min="${fd.min}"` : ""} ${fd.max ? `max="${fd.max}"` : ""}
        class="w-full bg-white border rounded-lg px-4 py-2.5 text-slate-900 text-sm focus:outline-none focus:ring-2 focus:ring-brand-600 focus:border-brand-600 transition placeholder:text-slate-400 ${err ? "border-red-400" : "border-slate-300"}" />
      ${err ? `<p class="text-red-600 text-xs mt-1">${esc(err)}</p>`
            : (fd.hint ? `<p class="text-slate-400 text-xs mt-1">${esc(fd.hint)}</p>` : "")}
    </div>`;
}

function sectionHtml(title, desc, accent, fields) {
  return `
    <div class="${accent === "first" ? "" : "border-t border-slate-200 pt-6"}">
      <div class="mb-3 flex items-start gap-2">
        <span class="mt-0.5 inline-block w-1 h-8 rounded ${accent && accent !== "first" ? accent : "bg-brand-600"}"></span>
        <div>
          <p class="text-sm font-semibold text-slate-900 leading-tight">${esc(title)}</p>
          ${desc ? `<p class="text-xs text-slate-500 mt-0.5">${esc(desc)}</p>` : ""}
        </div>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">${fields.map(fieldHtml).join("")}</div>
    </div>`;
}

function formStepHtml() {
  const s = state.student;
  const cards = [
    ["Нийт төлбөр", s.tolokhDun, "text-slate-900"],
    ["Урьдчилгаа", s.tolson, "text-green-600"],
    ["Үлдэгдэл", s.uldegdel, isDebt(s.uldegdel) ? "text-red-600" : "text-slate-500"],
  ].map(([l, v, c]) => `
    <div class="bg-slate-50 border border-slate-200 rounded-xl p-3 text-center">
      <p class="text-xs text-slate-500 mb-1">${esc(l)}</p>
      <p class="font-semibold text-sm ${c}">${esc(v || "—")}</p>
    </div>`).join("");
  return `
    <div class="space-y-6">
      <div>
        <h2 class="text-slate-900 font-semibold text-lg mb-1">Мэдээлэл шалгах / нөхөх</h2>
        <p class="text-slate-500 text-sm">Гэрээнд бөглөгдөх мэдээллээ шалгаад дутуу хэсгийг нөхнө үү. Бүх нэрийг криллээр бичнэ.</p>
      </div>
      <div class="grid grid-cols-3 gap-3">${cards}</div>
      ${sectionHtml("🎓 Суралцагч (хүүхэд)", "Сургалтад суралцах хүний мэдээлэл", "first", STUDENT_FIELDS)}
      ${sectionHtml("👤 Асран хамгаалагч / эцэг эх (төлөөлөгч)", "Гэрээ байгуулж, гарын үсэг зурах хууль ёсны төлөөлөгч", "bg-amber-500", GUARDIAN_FIELDS)}
      ${sectionHtml("Оршин суух хаяг", "Төлөөлөгчийн оршин суугаа бүтэн хаяг", "bg-slate-400", ADDRESS_FIELDS)}
      ${sectionHtml("Төлбөрийн нөхцөл", "", "bg-slate-400", PAYMENT_FIELDS)}
    </div>`;
}

function previewStepHtml() {
  return `
    <div>
      <h2 class="text-slate-900 font-semibold text-lg mb-1">Гэрээ харах</h2>
      <p class="text-slate-500 text-sm mb-4">Гэрээгээ доош гүйлгэн бүрэн уншиж шалгана уу.</p>
      <div class="relative rounded-xl overflow-hidden border border-slate-200 mb-4" style="height:480px">
        <div id="prevSpin" class="absolute inset-0 flex items-center justify-center bg-slate-50 z-10">
          <div class="w-7 h-7 border-2 border-brand-600 border-t-transparent rounded-full animate-spin"></div>
        </div>
        <iframe id="prevFrame" class="w-full h-full bg-white" title="Гэрээ"></iframe>
      </div>
      <label id="agreeBox" class="flex items-start gap-3 cursor-pointer rounded-xl border p-4 transition-colors ${state.agreed ? "border-brand-600 bg-brand-50" : "border-slate-300 bg-white hover:border-slate-400"}">
        <input id="agreeChk" type="checkbox" ${state.agreed ? "checked" : ""} class="mt-0.5 w-4 h-4 rounded accent-brand-600 cursor-pointer" />
        <span class="text-sm text-slate-700 leading-snug">Би дээрх гэрээний нөхцөлтэй бүрэн танилцаж, зөвшөөрч байна.</span>
      </label>
    </div>`;
}

function signatureStepHtml() {
  const f = state.formData, s = state.student;
  const rows = [
    ["Суралцагч", `${f.lastName} ${f.firstName}`],
    ["Регистр", f.register],
    ["Төлөөлөгч", `${f.guardianLastName} ${f.guardianFirstName}`],
    ["Төлөөлөгч утас", f.guardianPhone],
    ["Хаяг", f.addressDetail],
    ["Нийт төлбөр", s.tolokhDun],
    ["Үлдэгдэл", s.uldegdel],
  ].map(([l, v]) => `<div><span class="text-slate-500">${esc(l)}: </span><span class="font-medium text-slate-900">${esc(v || "—")}</span></div>`).join("");
  return `
    <div>
      <h2 class="text-slate-900 font-semibold text-lg mb-2">Гарын үсэг зурах</h2>
      <p class="text-slate-500 text-sm mb-6">Доорх хэсэгт гарын үсгээ зурна уу. Зурж дуусаад "Хадгалах" дарна.</p>
      <div class="bg-slate-50 rounded-xl p-4 mb-6 border border-slate-200">
        <p class="text-xs text-slate-500 mb-3 font-medium uppercase tracking-wider">Таны мэдээлэл</p>
        <div class="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">${rows}</div>
      </div>
      <div class="flex flex-col gap-3">
        <div class="relative border-2 border-dashed border-slate-300 rounded-xl overflow-hidden bg-white" style="height:200px">
          <canvas id="sigCanvas" class="w-full h-full cursor-crosshair"></canvas>
        </div>
        <div class="flex justify-between items-center">
          <p class="text-xs text-slate-400">Хулганаар эсвэл хурууны хавтан дээр зурна уу</p>
          <button id="sigClear" type="button" class="text-sm text-red-500 hover:text-red-700 font-medium">Арилгах</button>
        </div>
      </div>
    </div>`;
}

function doneStepHtml() {
  return `
    <div class="text-center py-8">
      <div class="text-5xl mb-4">✅</div>
      <h2 class="text-slate-900 font-semibold text-xl mb-2">Гэрээ амжилттай үүслээ</h2>
      <p class="text-slate-500 text-sm">Таны гэрээ PDF болж татагдлаа. Баярлалаа!</p>
    </div>`;
}

// ── Үндсэн render ─────────────────────────────────────────────────────────────
function render() {
  if (state.notFound) {
    root.innerHTML = `<div class="min-h-[60vh] flex flex-col items-center justify-center gap-2 text-center">
      <div class="text-5xl mb-3">🔍</div>
      <p class="text-slate-900 text-xl font-semibold">Линк олдсонгүй</p>
      <p class="text-slate-500 text-sm mt-1">Линкийг AI Academy Asia-аас дахин авна уу.</p></div>`;
    return;
  }
  if (state.alreadySigned) {
    root.innerHTML = `<div class="min-h-[60vh] flex flex-col items-center justify-center gap-2 text-center">
      <div class="text-5xl mb-3">🔒</div>
      <p class="text-slate-900 text-xl font-semibold">Гэрээ аль хэдийн баталгаажсан</p>
      <p class="text-slate-500 text-sm mt-1 max-w-sm">Энэ суралцагчийн гэрээ урьд нь гарын үсэг зурж баталгаажсан тул дахин бөглөх боломжгүй. Шаардлагатай бол AI Academy Asia-тай холбогдоно уу.</p></div>`;
    return;
  }
  if (!state.student) return;

  const s = state.student;
  const stepDots = STEPS.map((label, i) => {
    const active = i === state.step, done = i < state.step;
    return `<div class="flex items-center ${i < STEPS.length - 1 ? "flex-1" : ""}">
      <div class="flex flex-col items-center">
        <div class="w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold ${done || active ? "bg-brand-600 text-white" : "bg-slate-200 text-slate-500"}">${done ? "✓" : i + 1}</div>
        <span class="text-[10px] mt-1 ${active ? "text-slate-900 font-medium" : "text-slate-400"}">${esc(label)}</span>
      </div>
      ${i < STEPS.length - 1 ? `<div class="flex-1 h-0.5 mx-1 ${done ? "bg-brand-600" : "bg-slate-200"}"></div>` : ""}
    </div>`;
  }).join("");

  const stepBody = [formStepHtml, previewStepHtml, signatureStepHtml, doneStepHtml][state.step]();

  const nextDisabled = (state.step === 1 && !state.agreed) || (state.step === 2 && !state.signature) || state.loading;
  const isLast = state.step === 2;
  const nav = state.step < 3 ? `
    <div class="flex justify-between mt-6">
      ${state.step > 0 ? `<button id="backBtn" class="flex items-center gap-2 text-slate-500 hover:text-slate-900 font-medium">← Буцах</button>` : "<div></div>"}
      <button id="nextBtn" ${nextDisabled ? "disabled" : ""}
        class="flex items-center gap-2 text-white font-semibold px-6 py-2.5 rounded-xl transition-colors shadow-sm disabled:opacity-40 disabled:cursor-not-allowed ${isLast ? "bg-green-600 hover:bg-green-700" : "bg-brand-600 hover:bg-brand-700"}">
        ${state.loading ? "PDF үүсгэж байна..." : (isLast ? "Хадгалах →" : "Үргэлжлүүлэх →")}
      </button>
    </div>` : "";

  root.innerHTML = `
    <header class="mb-8">
      <div class="flex items-center gap-3 mb-8">
        <img src="${STATIC}/logo.png" alt="AI Academy Asia" class="h-9 w-auto" />
        <div class="leading-tight">
          <div class="text-slate-900 font-bold tracking-tight">AI Academy Asia</div>
          <div class="text-[11px] text-brand-700 font-medium">AI for all</div>
        </div>
        <span class="ml-auto text-slate-400 text-sm">${esc(s.program || "")}</span>
      </div>
      <div class="text-center">
        <h1 class="text-2xl font-extrabold text-slate-900 mb-1 tracking-tight">Сургалтын гэрээ</h1>
        <p class="text-slate-500 text-sm">${esc(s.classCode || "")}</p>
      </div>
    </header>
    <div class="flex items-center mb-8">${stepDots}</div>
    <div class="bg-white border border-slate-200 rounded-2xl p-8 shadow-sm">${stepBody}</div>
    ${nav}`;

  wireStep();
}

// ── Алхам бүрийн event холболт ────────────────────────────────────────────────
function wireStep() {
  const backBtn = document.getElementById("backBtn");
  const nextBtn = document.getElementById("nextBtn");
  if (backBtn) backBtn.onclick = handleBack;
  if (nextBtn) nextBtn.onclick = handleNext;

  if (state.step === 0) {
    root.querySelectorAll("input[data-key]").forEach((inp) => {
      inp.addEventListener("input", (e) => {
        const key = inp.dataset.key;
        let val = e.target.value;
        if (key === "register" || key === "guardianRegister") val = normalizeRegister(val);
        else if (CYRILLIC_FIELDS.includes(key)) val = val.replace(/[A-Za-z]/g, "");
        if (val !== e.target.value) e.target.value = val;
        state.formData[key] = val;
        // утга оруулмагц улаан алдааг шууд цэвэрлэх (дахин render-гүйгээр)
        if (state.errors[key]) {
          delete state.errors[key];
          inp.classList.remove("border-red-400");
          inp.classList.add("border-slate-300");
          const msg = inp.parentElement.querySelector("p");
          const fd = FIELDS_BY_KEY[key];
          if (msg) {
            if (fd && fd.hint) { msg.className = "text-slate-400 text-xs mt-1"; msg.textContent = fd.hint; }
            else msg.remove();
          }
        }
      });
    });
  }

  if (state.step === 1) loadPreview();
  if (state.step === 2) initSignature();
}

function loadPreview() {
  const s = state.student;
  state.agreed = false;
  const frame = document.getElementById("prevFrame");
  const spin = document.getElementById("prevSpin");
  const chk = document.getElementById("agreeChk");
  const box = document.getElementById("agreeBox");
  let url = null;

  fetch(`${API}/preview`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      classCode: s.classCode, program: s.program, num: s.num,
      formData: { ...state.formData, ognoo: todayISO() },
      finance: { tolokhDun: s.tolokhDun, tolson: s.tolson, uldegdel: s.uldegdel },
    }),
  })
    .then((r) => { if (!r.ok) throw new Error("preview"); return r.blob(); })
    .then((blob) => {
      url = URL.createObjectURL(blob);
      frame.src = `${url}#toolbar=0&view=FitH`;
      frame.onload = () => { if (spin) spin.style.display = "none"; };
      setTimeout(() => { if (spin) spin.style.display = "none"; }, 1500);
    })
    .catch(() => { if (spin) spin.innerHTML = '<p class="text-slate-400 text-sm">Гэрээ ачааллахад алдаа гарлаа</p>'; });

  chk.addEventListener("change", (e) => {
    state.agreed = e.target.checked;
    document.getElementById("nextBtn").disabled = !state.agreed;
    box.className = `flex items-start gap-3 cursor-pointer rounded-xl border p-4 transition-colors ${state.agreed ? "border-brand-600 bg-brand-50" : "border-slate-300 bg-white hover:border-slate-400"}`;
  });
}

function initSignature() {
  const canvas = document.getElementById("sigCanvas");
  const ratio = Math.max(window.devicePixelRatio || 1, 1);
  canvas.width = canvas.offsetWidth * ratio;
  canvas.height = canvas.offsetHeight * ratio;
  canvas.getContext("2d").scale(ratio, ratio);

  const pad = new SignaturePad(canvas, {
    backgroundColor: "rgba(0,0,0,0)",
    penColor: "#1e293b", minWidth: 1.5, maxWidth: 3,
  });
  pad.addEventListener("endStroke", () => {
    state.signature = pad.isEmpty() ? null : pad.toDataURL("image/png");
    document.getElementById("nextBtn").disabled = !state.signature;
  });
  document.getElementById("sigClear").onclick = () => {
    pad.clear(); state.signature = null;
    document.getElementById("nextBtn").disabled = true;
  };
}
