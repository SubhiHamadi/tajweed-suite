"""
idgham_special_common.py
══════════════════════════════════════════════════════════════════
وحدة مشتركة لثلاثة تطبيقات: إدغام المتجانسين، إدغام المتقاربين،
إدغام المتماثلين. كل واحد منها عدد حالاته قليل وثابت (بيانات مُضمَّنة
في الكود نفسه، وليست في قاعدة بيانات) — لذا التنقل هنا بقائمة اختيار
مباشرة (كما في sakt_web_app.py) بدل التنقل بالصفحة أو السورة/الآية.
نفس هوية بقية السويطة البصرية (الألوان، الخطوط، السحب، القرّاء الأربعة).
"""
import os, re, sys, sqlite3, json, random, threading, webbrowser
from flask import Flask, Blueprint, jsonify, request, send_from_directory, send_file

READER_NAMES = {
    'Aya1Aya' : 'مشاري راشد العفاسي',
    'Aya9Aya' : 'محمد صديق المنشاوي — المعلم',
    'AyaEAya' : '🇬🇧 Ibrahim Walk (English)',
}
SKIP = {'AyaAya', 'Husary', 'abdulstar', 'kolon', 'mnshawi'}

_DECORATIVE_MARKS = '\u06DE\u06E9\u06DD'
def _clean_aya(text):
    if not text:
        return ''
    text = text.replace('\r\n', ' ').replace('\n', ' ')
    for ch in _DECORATIVE_MARKS:
        text = text.replace(ch, ' ')
    return re.sub(r'\s+', ' ', text).strip()

def _find_db_path(base_dir):
    candidates = [
        os.path.join(base_dir, 'quran.db'),
        r'D:\family\quran.db',
        r'E:\family\quran.db',
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return candidates[0]

try:
    from word_audio_helper import prepare_word_clip, prepare_range_clip
    _WORD_AUDIO_OK = True
except Exception:
    _WORD_AUDIO_OK = False


def build_app(ruletype, title, subtitle, cases, api_prefix, intro_def=None,
              as_blueprint=False, home_path='/'):
    """
    ruletype : اسم الحكم الداخلي (لا يُعرض، للتمييز فقط)
    title    : عنوان الصفحة الظاهر
    subtitle : السطر الفرعي تحت العنوان
    cases    : قائمة القواميس (نُسخة مطابقة تمامًا لقائمة CASES في نسخة
               PyQt6 الأصلية — نفس المفاتيح: title/suraid/verseid/
               suraname/ayah/word/makhraj/letters/pronounce/note/color)
    api_prefix: بادئة مسارات API (مثل 'mjs' لإدغام المتجانسين)
    intro_def : تعريف عام اختياري يُعرض في نافذة مساعدة أعلى القائمة
    as_blueprint / home_path : نفس آلية qlqhnlamat_common.py — تبني
        Blueprint قابلاً للتركيب ضمن التطبيق الموحَّد بدل تطبيق مستقل،
        دون أي تغيير في الاستخدام المستقل الحالي عند الإبقاء على القيمة
        الافتراضية False.
    """
    app = Blueprint(f'idghamsp_{api_prefix}', __name__) if as_blueprint else Flask(__name__)

    if getattr(sys, 'frozen', False):
        BASE_DIR = os.path.dirname(sys.executable)
    else:
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    # على Render (أو أي استضافة تستخدم قرصًا دائمًا منفصلاً)، يكون
    # quran.db ومجلدات الصوت موجودة على /data بدل مجلد الكود نفسه —
    # نُحوّل BASE_DIR إليه تلقائيًا عند توفره، فتستفيد كل عمليات البحث
    # عن قاعدة البيانات ومجلدات القرّاء أدناه دون أي تعديل آخر.
    if os.path.isdir('/data') and os.path.exists('/data/quran.db'):
        BASE_DIR = '/data'
    DB_PATH = _find_db_path(BASE_DIR)

    # نحلّ نص الآية الكامل ورقم الصفحة لكل حالة مرة واحدة عند الإقلاع،
    # بنفس أسلوب _resolve_pagenums في النسخة الأصلية
    def get_db():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def _resolve_cases():
        try:
            conn = get_db(); cur = conn.cursor()
            for c in cases:
                cur.execute('SELECT SURANAME, ayahtext, PAGENUM FROM mushafnew WHERE SURAID=? AND VERSEID=? LIMIT 1',
                            (c['suraid'], c['verseid']))
                r = cur.fetchone()
                if r:
                    c['suraname'] = c.get('suraname') or r[0]
                    c['aya_full'] = _clean_aya(r[1])
                    c['pagenum']  = r[2]
                else:
                    c['aya_full'] = _clean_aya(c.get('ayah', ''))
                    c['pagenum']  = None
            conn.close()
        except Exception:
            for c in cases:
                c.setdefault('aya_full', _clean_aya(c.get('ayah', '')))
                c.setdefault('pagenum', None)
    _resolve_cases()

    def _get_readers_dict():
        d = {}
        if os.path.isdir(BASE_DIR):
            for f in os.listdir(BASE_DIR):
                if f in SKIP:
                    continue
                fp = os.path.join(BASE_DIR, f)
                if os.path.isdir(fp):
                    d[f] = fp
        return d

    def _case_payload(idx):
        c = cases[idx]
        return {
            'idx': idx, 'title': c['title'], 'suraid': c['suraid'], 'verseid': c['verseid'],
            'suraname': c.get('suraname', ''), 'aya': c.get('aya_full', ''), 'word': c.get('word', ''),
            'makhraj': c.get('makhraj', ''), 'letters': c.get('letters', ''),
            'pronounce': c.get('pronounce', ''), 'note': c.get('note'),
            'color': c.get('color', '#D4A843'),
        }

    HTML = r'''<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__TITLE__</title>
<style>
:root {
  --navy:  #00BCD4; --navy2: #0A2040; --gold:  #D4A843; --gold2: #0D2847;
  --green: #00C853; --red:   #EF5350; --bg:    #020B18; --card:  #0D2847;
  --border:#1A3A5C; --text:  #F8F4EE; --muted: #B0BEC5;
}
* { box-sizing:border-box; margin:0; padding:0; }
body {
  font-family:"Traditional Arabic","Noto Naskh Arabic",Arial,sans-serif;
  background:var(--bg); color:var(--text); direction:rtl; min-height:100vh; font-size:15px;
}
header {
  background:linear-gradient(135deg,#020B18 0%,#0A2848 50%,#020B18 100%);
  border-bottom:4px solid var(--gold); padding:14px 16px 12px; text-align:center;
  box-shadow:0 2px 8px rgba(212,168,67,0.15);
}
.header-title { font-size:clamp(15px,4.5vw,22px); font-weight:bold; color:#F0C755;
  margin-bottom:3px; letter-spacing:0.3px; text-shadow:0 0 12px rgba(212,168,67,0.5); }
.header-sub { font-size:clamp(10px,2.8vw,13px); color:#00E5FF; margin-bottom:10px; }
.authors { display:flex; gap:8px; justify-content:center; flex-wrap:wrap; }
.author-card { background:rgba(212,168,67,0.08); border:1px solid rgba(212,168,67,0.25);
  border-radius:8px; padding:5px 12px; font-size:clamp(9px,2.5vw,12px); text-align:center; }
.author-name { color:#F0C755; font-weight:bold; }
.author-info { color:#00E5FF; font-size:0.88em; }

.controls { background:var(--card); border-bottom:1px solid var(--border); padding:12px 14px; }
.ctrl-row { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-bottom:9px; }
.ctrl-row:last-child { margin-bottom:0; }
.ctrl-label { font-size:clamp(11px,3vw,13px); color:var(--gold); white-space:nowrap; font-weight:bold; }
select {
  background:#0A2040; border:1.5px solid var(--border); border-radius:8px;
  padding:7px 10px; color:var(--text); font-family:"Traditional Arabic",Arial;
  font-size:13px; flex:1; min-width:80px; cursor:pointer;
}
select:focus { border-color:var(--gold); outline:none; }
button { border:none; border-radius:8px; padding:8px 14px; font-family:"Traditional Arabic",Arial;
         font-size:13px; font-weight:bold; cursor:pointer; white-space:nowrap; }
.btn-random { background:rgba(0,188,212,0.15); color:var(--navy); border:1.5px solid var(--navy); }
.btn-prev, .btn-next { background:rgba(0,188,212,0.15); color:var(--navy); border:1.5px solid var(--navy); }
.btn-play   { background:rgba(0,200,83,0.15); color:var(--green); border:1.5px solid var(--green); }
.btn-stop   { background:rgba(239,83,80,0.15); color:var(--red); border:1.5px solid var(--red); }
.speed-bar { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.speed-label { font-size:12px; color:var(--gold); font-weight:bold; white-space:nowrap; }
.speed-btn { padding:5px 11px; border-radius:20px; font-size:12px; font-weight:bold;
             border:1.5px solid var(--navy); background:#0A2040; color:var(--navy); cursor:pointer; }
.speed-btn.active { background:var(--navy); color:#020B18; }

.btn-go { background:var(--gold); color:#020B18; }
.btn-showall { background:rgba(212,168,67,0.15); color:var(--gold); border:1.5px solid var(--gold);
               padding:4px 12px; font-size:11px; border-radius:20px; }

.legend { display:flex; gap:14px; padding:8px 14px; flex-wrap:wrap;
          background:var(--bg); border-bottom:1px solid var(--border); }
.legend-item { font-size:12px; font-weight:bold; cursor:pointer; white-space:nowrap; opacity:0.85; }
.legend-item.active { text-decoration:underline; opacity:1; }
.hint { font-size:11px; color:var(--muted); text-align:center; padding:6px 14px; opacity:0.75; }
.notify { display:none; margin:0 14px 10px; padding:8px 14px; border-radius:10px;
  background:rgba(239,83,80,0.12); border:1px solid var(--red); color:#FF8A80; font-size:13px; text-align:center; }
.notify.show { display:block; }

.info-bar { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap;
            padding:8px 14px; background:var(--card); border-bottom:1px solid var(--border); font-size:13px; }
.info-aya { color:#F0C755; font-weight:bold; }
.cnt-badge { padding:2px 10px; border-radius:20px; font-size:12px; font-weight:bold;
             background:rgba(212,168,67,0.15); color:var(--gold); border:1px solid var(--gold); }

.ayah-wrap { padding:12px 14px 4px; }
.ayah-box {
  background:linear-gradient(180deg,#0D2847 0%,#0A2040 100%);
  border:2px solid rgba(212,168,67,0.44); border-radius:16px;
  padding:18px 20px; font-family:"KFGQPC_HAFS_Uthmanic_Script_H","Traditional Arabic";
  font-size:clamp(20px,5.5vw,28px); line-height:250%;
  direction:rtl; text-align:right; color:#F8F4EE; margin-bottom:14px;
  box-shadow:0 0 20px rgba(212,168,67,0.15);
}
.word-tok { cursor:pointer; }
.word-tok.dragsel { background:rgba(212,168,67,0.4); border-radius:4px; }
.clip-reciters { display:flex; gap:6px; flex-wrap:wrap; justify-content:center; margin-bottom:6px; }
.clip-btn { border:1.5px solid var(--green); color:var(--green); background:rgba(0,200,83,0.1);
            border-radius:20px; padding:5px 12px; font-size:12px; cursor:pointer; }
#clipStatus { font-size:11px; color:var(--muted); text-align:center; margin:-2px 0 8px; min-height:14px; }

.detail-card { margin:0 14px 16px; padding:14px 16px; border-radius:14px; background:var(--card);
               border:1px solid var(--border); }
.detail-row { margin-bottom:10px; font-size:13px; line-height:180%; }
.detail-row:last-child { margin-bottom:0; }
.detail-label { color:var(--gold); font-weight:bold; display:block; margin-bottom:2px; }
.pronounce-label { cursor:pointer; }
.pronounce-label:hover { text-decoration:underline; }
.pronounce-status { font-size:11px; color:var(--muted); }
.detail-note { background:rgba(255,152,0,0.1); border:1px solid #FF9800; color:#FFB74D;
               border-radius:10px; padding:10px 12px; font-size:12.5px; line-height:175%; }

.table-wrap { margin:0 14px 16px; border:1px solid var(--border); border-radius:14px; overflow:hidden; }
.table-header { background:linear-gradient(90deg,#0D3060,#0D2847); padding:10px 14px; color:#F0C755;
                font-weight:bold; font-size:13px; border-bottom:2px solid var(--gold); }
table { width:100%; border-collapse:collapse; background:#061525; }
th { background:#0D3060; color:#F0C755; padding:9px 6px; border-bottom:2px solid var(--gold);
     font-size:12px; font-weight:bold; }
td { padding:9px 6px; border-bottom:1px solid var(--border); text-align:center; font-size:12px; color:var(--text); }
tr:nth-child(even) td { background:#0A2040; }
tr:last-child td { border-bottom:none; }
tr.case-row { cursor:pointer; }
.word-cell { font-family:"KFGQPC_HAFS_Uthmanic_Script_H","Traditional Arabic";
             font-size:clamp(15px,4.5vw,18px); font-weight:bold; }
#allCasesOverlay { display:none; position:fixed; top:0;left:0;right:0;bottom:0;
  background:rgba(0,0,0,0.65); z-index:2000; align-items:center; justify-content:center; padding:16px; }
#allCasesOverlay.show { display:flex; }
.all-cases-modal { background:#0D2847; border-radius:16px; padding:20px; max-width:680px;
  width:100%; max-height:82vh; overflow-y:auto; direction:rtl;
  box-shadow:0 8px 40px rgba(0,0,0,0.6); border:2px solid rgba(212,168,67,0.55); }
.all-cases-modal table { width:100%; }

#wordOverlay { display:none; position:fixed; top:0;left:0;right:0;bottom:0;
  background:rgba(0,0,0,0.65); z-index:2000; align-items:center; justify-content:center; padding:16px; }
#wordOverlay.show { display:flex; }
#wordModal { background:#0D2847; border-radius:16px; padding:20px; max-width:420px;
  width:100%; max-height:82vh; overflow-y:auto; direction:rtl;
  box-shadow:0 8px 40px rgba(0,0,0,0.6); border:2px solid rgba(212,168,67,0.55); }
#wordTitle { font-family:"KFGQPC_HAFS_Uthmanic_Script_H","Traditional Arabic";
             font-size:26px; text-align:center; margin-bottom:6px; font-weight:bold; }
#wordContext { font-size:12px; color:var(--muted); text-align:center; margin-bottom:14px; }
#wordResult { background:#061525; border-radius:10px; padding:14px; font-size:15px;
              line-height:185%; color:var(--text); border:1px solid var(--border); min-height:40px; margin-bottom:10px; }
.word-input-row { display:flex; gap:8px; margin-bottom:10px; }
.word-input { flex:1; border:1.5px solid var(--border); border-radius:10px; padding:8px 12px;
              font-family:"Traditional Arabic",Arial; font-size:14px; direction:rtl; background:#061525; color:var(--text); }
.word-ask-btn { background:var(--navy); color:#020B18; border:none; border-radius:10px;
                padding:8px 14px; font-size:13px; font-weight:bold; cursor:pointer; }
#wordClose { width:100%; margin-top:6px; padding:9px; border:1.5px solid var(--red);
  border-radius:10px; background:rgba(239,83,80,0.1); cursor:pointer; font-size:14px; color:var(--red); }

@media(max-width:480px) { .ctrl-row { flex-direction:column; align-items:stretch; } button, select { width:100%; } }
</style>
</head>
<body>

<header>
  <div class="header-title">__TITLE__</div>
  <div class="header-sub">__SUBTITLE__</div>
  <div class="authors">
    <div class="author-card">
      <div class="author-name">د. صبحي حمادي حمدون</div>
      <div class="author-info">جامعة النور — الموصل</div>
    </div>
    <div class="author-card">
      <div class="author-name">د. محمد حميد الطائي</div>
      <div class="author-info">جامعة التقنية والعلوم التطبيقية — صحار</div>
    </div>
  </div>
</header>

<div class="controls">
  <div class="ctrl-row">
    <span class="ctrl-label">السورة:</span>
    <select id="selSura" onchange="onSuraChange()"></select>
    <span class="ctrl-label">الآية:</span>
    <select id="selVerse"></select>
    <button class="btn-go" onclick="onGo()">عرض</button>
    <button class="btn-showall" onclick="showAllCases()">⛶ عرض الكل</button>
    <button class="btn-random" onclick="loadRandom()">🔀 عشوائي</button>
  </div>
  <div class="ctrl-row">
    <span class="ctrl-label">القارئ:</span>
    <select id="selReader"></select>
    <button class="btn-play" onclick="playAyah()">▶ استمع</button>
    <button class="btn-stop" onclick="stopAudio()">⏹</button>
  </div>
  <div class="ctrl-row">
    <div class="speed-bar">
      <span class="speed-label">السرعة:</span>
      <button class="speed-btn" onclick="setSpeed(0.75,this)">0.75x</button>
      <button class="speed-btn active" onclick="setSpeed(1.0,this)">1.0x</button>
      <button class="speed-btn" onclick="setSpeed(1.25,this)">1.25x</button>
      <button class="speed-btn" onclick="setSpeed(1.5,this)">1.5x</button>
      <button class="speed-btn" onclick="setSpeed(2.0,this)">2.0x</button>
    </div>
  </div>
</div>

<div class="legend" id="legend"></div>
<div class="hint">💡 اضغط على الكلمة الملوّنة لشرحها — أو اسحب من كلمة إلى أخرى لتحديد عبارة وسماعها</div>

<div class="info-bar">
  <div class="info-aya" id="infoAya">—</div>
  <div class="cnt-badge" id="infoCount"></div>
</div>

<div class="notify" id="notify"></div>

<div class="ayah-wrap">
  <div class="ayah-box" id="ayahBox">جارٍ التحميل...</div>
</div>

<div class="detail-card" id="detailCard"></div>

<div id="allCasesOverlay" onclick="closeAllCases(event)">
  <div class="all-cases-modal">
    <div class="table-header" style="margin:-20px -20px 12px;border-radius:16px 16px 0 0;">📋 كل الحالات الموثّقة</div>
    <table>
      <thead><tr><th>السورة</th><th>الآية</th><th>الكلمة</th><th>النوع</th></tr></thead>
      <tbody id="allCasesTable"></tbody>
    </table>
    <button id="wordClose" onclick="closeAllCases()" style="margin-top:12px;">✕ إغلاق</button>
  </div>
</div>

<audio id="audioPlayer"></audio>
<audio id="clipPlayer"></audio>

<div id="wordOverlay" onclick="closeWordModal(event)">
  <div id="wordModal">
    <div id="wordTitle"></div>
    <div id="wordContext"></div>
    <div id="wordResult"></div>
    <div class="clip-reciters">
      <button class="clip-btn" onclick="playClipReciter('alafasy')">🔊 العفاسي</button>
      <button class="clip-btn" onclick="playClipReciter('minshawy')">🔊 المنشاوي</button>
      <button class="clip-btn" onclick="playClipReciter('husary')">🔊 الحصري</button>
      <button class="clip-btn" onclick="playClipReciter('abdulbasit')">🔊 عبدالباسط</button>
    </div>
    <div id="clipStatus"></div>
    <div class="word-input-row">
      <input type="text" class="word-input" id="wordQuestion" placeholder="اسأل عن هذه الحالة...">
      <button class="word-ask-btn" onclick="askAI()">اسأل</button>
    </div>
    <button id="wordClose" onclick="closeWordModal()">✕ إغلاق</button>
  </div>
</div>

<script>
const API_PREFIX = '__API_PREFIX__';
let currentSpeed = 1.0;
let currentCase  = null;   // البيانات الحالية المعروضة (قد تكون بلا حالة إدغام موثّقة)
let currentWords = [];
let currentRange = [-1, -1];
let allCasesList = [];     // من /list — تُستخدم للأسطورة وجدول "عرض الكل"
const audio = document.getElementById('audioPlayer');
const clipPlayer = document.getElementById('clipPlayer');

function showNotify(msg) {
  const n = document.getElementById('notify');
  n.textContent = msg; n.classList.add('show');
}
function hideNotify() { document.getElementById('notify').classList.remove('show'); }

async function loadReaders() {
  const r = await fetch('/api/readers');
  const d = await r.json();
  document.getElementById('selReader').innerHTML =
    d.map(x => `<option value="${x.id}">${x.label}</option>`).join('');
}

async function loadSuras() {
  const r = await fetch(`/api/${API_PREFIX}/suras`);
  const d = await r.json();
  document.getElementById('selSura').innerHTML =
    d.map(s => `<option value="${s.suraid}">${s.suraid}. ${s.suraname}</option>`).join('');
}

async function loadVerses(suraid) {
  const r = await fetch(`/api/${API_PREFIX}/verses?suraid=${suraid}`);
  const d = await r.json();
  document.getElementById('selVerse').innerHTML =
    d.map(v => `<option value="${v}">${v}</option>`).join('');
}

async function onSuraChange() {
  const suraid = document.getElementById('selSura').value;
  await loadVerses(suraid);
  onGo();
}
function onGo() {
  const suraid  = document.getElementById('selSura').value;
  const verseid = document.getElementById('selVerse').value;
  if (suraid && verseid) loadAyah(parseInt(suraid,10), parseInt(verseid,10));
}

async function loadList() {
  const r = await fetch(`/api/${API_PREFIX}/list`);
  allCasesList = await r.json();
  buildLegend();
}

function buildLegend() {
  document.getElementById('legend').innerHTML = allCasesList.map(c =>
    `<span class="legend-item" id="leg-${c.idx}" style="color:${c.color};"
      onclick="loadAyah(${c.suraid},${c.verseid})">● ${c.title}</span>`).join('');
}
function markActiveLegend(idx) {
  document.querySelectorAll('.legend-item').forEach(el => el.classList.remove('active'));
  if (idx !== null && idx !== undefined) {
    document.getElementById(`leg-${idx}`)?.classList.add('active');
  }
}

function setSpeed(v, btn) {
  currentSpeed = v; audio.playbackRate = v;
  document.querySelectorAll('.speed-btn').forEach(b => b.classList.toggle('active', b === btn));
}
function stopAudio() { audio.pause(); audio.currentTime = 0; }
function playAyah() {
  if (!currentCase) return;
  const reader = document.getElementById('selReader').value;
  const fname = String(currentCase.suraid).padStart(3,'0') + String(currentCase.verseid).padStart(3,'0') + '.mp3';
  audio.src = `/audio/${reader}/${fname}`;
  audio.playbackRate = currentSpeed;
  audio.play().catch(() => alert('⚠️ ملف الصوت غير متوفر لهذا القارئ.'));
}

// ── سحب لتحديد مجال حر (نفس آلية بقية السويطة) ──
let dragStart = null, dragEnd = null, isDragging = false, dragInit = false;
function tokenIdxFromEvent(e) {
  const t = e.target.closest('.word-tok');
  return t ? parseInt(t.dataset.idx, 10) : null;
}
function paintSelection() {
  const box = document.getElementById('ayahBox');
  const lo = Math.min(dragStart, dragEnd), hi = Math.max(dragStart, dragEnd);
  box.querySelectorAll('.word-tok').forEach(el => {
    const i = parseInt(el.dataset.idx, 10);
    el.classList.toggle('dragsel', i >= lo && i <= hi);
  });
}
function clearSelection() {
  dragStart = dragEnd = null; isDragging = false;
  document.getElementById('ayahBox')?.querySelectorAll('.word-tok').forEach(el => el.classList.remove('dragsel'));
}
function initDragSelect() {
  const box = document.getElementById('ayahBox');
  if (!box || dragInit) return;
  dragInit = true;
  box.addEventListener('mousedown', e => {
    const idx = tokenIdxFromEvent(e);
    if (idx === null) return;
    isDragging = true; dragStart = dragEnd = idx; paintSelection();
    e.preventDefault();
  });
  box.addEventListener('mouseover', e => {
    if (!isDragging) return;
    const idx = tokenIdxFromEvent(e);
    if (idx === null) return;
    dragEnd = idx; paintSelection();
  });
  document.addEventListener('mouseup', () => {
    if (!isDragging) return;
    isDragging = false;
    if (dragStart === null || dragEnd === null) return;
    openSelectionExplain(Math.min(dragStart, dragEnd), Math.max(dragStart, dragEnd));
  });
  box.addEventListener('touchstart', e => {
    const el = document.elementFromPoint(e.touches[0].clientX, e.touches[0].clientY);
    const t = el?.closest('.word-tok');
    if (!t) return;
    isDragging = true; dragStart = dragEnd = parseInt(t.dataset.idx, 10); paintSelection();
  }, {passive:true});
  box.addEventListener('touchmove', e => {
    if (!isDragging) return;
    const el = document.elementFromPoint(e.touches[0].clientX, e.touches[0].clientY);
    const t = el?.closest('.word-tok');
    if (!t) return;
    dragEnd = parseInt(t.dataset.idx, 10); paintSelection();
  }, {passive:true});
  box.addEventListener('touchend', () => { document.dispatchEvent(new Event('mouseup')); });
}

// يزيل التشكيل وعلامات الوقف القرآنية، ويوحّد صور الألف (آ أ إ ٱ ← ا)
// قبل المقارنة — النص الفعلي في quran.db يستخدم رسمًا عثمانيًا يختلف
// حرفيًا عن الكتابة اليدوية القياسية لبيانات الحالة، حتى لو تطابقا
// نطقًا: قد تُلصق علامة الوقف بآخر الكلمة بلا مسافة (وَجَدتُّمُوهُمۡۖ)،
// وقد تُكتب همزة الوصل ٱ بدل الألف العادية ا (ٱرۡكَب).
function bareChar(s) {
  return (s || '')
    .replace(/[\u064B-\u065F\u0610-\u061A\u06D6-\u06ED\u0670\u08D3-\u08FF\u0640]/g, '')
    .replace(/[\u0622\u0623\u0625\u0671]/g, '\u0627');
}

// يبحث عن عبارة الحكم داخل الآية بمطابقة السلسلة المجرَّدة من التشكيل
// دفعة واحدة (بلا اعتماد على انقسام العبارة إلى نفس عدد الكلمات في كلا
// الجانبين) — أكثر متانة من مقارنة الكلمات واحدة تلو الأخرى، لأن التباس
// الرسم العثماني أعلاه قد يُغيّر عدد الكلمات الظاهرة أيضاً (كإلصاق
// علامة وقف كانت مكتوبة كوحدة مستقلة في بيانات الحالة اليدوية).
function findWordRange(words, targetPhrase) {
  let bareFull = '';
  const charOwner = [];
  words.forEach((w, wi) => {
    const b = bareChar(w);
    for (const ch of b) { bareFull += ch; charOwner.push(wi); }
  });
  const targetBare = bareChar((targetPhrase || '').replace(/\s+/g, ''));
  if (!targetBare) return [-1, -1];
  const pos = bareFull.indexOf(targetBare);
  if (pos === -1) return [-1, -1];
  return [charOwner[pos], charOwner[pos + targetBare.length - 1]];
}

function renderCase(d) {
  currentCase = d;
  document.getElementById('infoAya').textContent =
    d.matched ? `${d.title} — سورة ${d.suraname}، الآية ${d.verseid}` : `سورة ${d.suraname} — الآية ${d.verseid}`;
  document.getElementById('infoCount').textContent = d.matched ? '✓ حالة موثّقة' : '';
  markActiveLegend(d.matched ? d.idx : null);
  if (d.matched) hideNotify();
  else showNotify('❌ لا يوجد حكم إدغام موثّق في هذه الآية — جرّب أحد العناصر الملوّنة أعلاه، أو زر "عشوائي".');

  const words = (d.aya || '').split(/\s+/).filter(Boolean);
  const [lo, hi] = findWordRange(words, d.word || '');
  currentWords = words; currentRange = [lo, hi];

  document.getElementById('ayahBox').innerHTML = words.map((w, i) =>
    (lo !== -1 && i >= lo && i <= hi)
      ? `<span class="word-tok" data-idx="${i}" style="color:${d.color};font-weight:bold;">${w}</span>`
      : `<span class="word-tok" data-idx="${i}" style="color:var(--text)">${w}</span>`
  ).join(' ');
  initDragSelect();
  clearSelection();

  document.getElementById('detailCard').innerHTML = d.matched ? `
    <div class="detail-row"><span class="detail-label">📍 المخرج</span>${d.makhraj || ''}</div>
    <div class="detail-row"><span class="detail-label">📖 توضيح الإدغام</span>${d.letters || ''}</div>
    <div class="detail-row">
      <span class="detail-label pronounce-label" onclick="playPronounceClip()">🔊 كيفية النطق (اضغط للاستماع)</span>
      ${d.pronounce || ''}
      <span id="pronounceStatus" class="pronounce-status"></span>
    </div>
    ${d.note ? `<div class="detail-row detail-note">⚠️ ${d.note}</div>` : ''}
  ` : '';
}

function playPronounceClip() {
  if (!currentCase || currentRange[0] === -1) return;
  const status = document.getElementById('pronounceStatus');
  const p = new URLSearchParams({
    suraid: currentCase.suraid, verseid: currentCase.verseid, reciter: 'alafasy',
    type: 'range', lo: currentRange[0], hi: currentRange[1],
  });
  status.textContent = ' ⏳';
  clipPlayer.src = `/api/${API_PREFIX}/clip?` + p.toString();
  clipPlayer.play().then(() => { status.textContent = ''; })
    .catch(async () => {
      try {
        const r = await fetch(`/api/${API_PREFIX}/clip?` + p.toString());
        const j = await r.json();
        status.textContent = ' ⚠ ' + (j.error || 'تعذّر التشغيل');
      } catch (e) { status.textContent = ' ⚠ تعذّر التشغيل'; }
    });
}

async function loadAyah(suraid, verseid) {
  const r = await fetch(`/api/${API_PREFIX}/ayah?suraid=${suraid}&verseid=${verseid}`);
  const d = await r.json();
  if (d.error) return;
  document.getElementById('selSura').value = suraid;
  if (document.getElementById('selVerse').dataset.sura != suraid) {
    await loadVerses(suraid);
    document.getElementById('selVerse').dataset.sura = suraid;
  }
  document.getElementById('selVerse').value = verseid;
  renderCase(d);
}

async function loadRandom() {
  const r = await fetch(`/api/${API_PREFIX}/random`);
  const d = await r.json();
  loadAyah(d.suraid, d.verseid);
}

function showAllCases() {
  document.getElementById('allCasesTable').innerHTML = allCasesList.map(c => `
    <tr class="case-row" data-suraid="${c.suraid}" data-verseid="${c.verseid}">
      <td>${c.suraname}</td><td>${c.verseid}</td>
      <td class="word-cell" style="color:${c.color};">${c.word || c.title}</td>
      <td style="color:${c.color};">${c.title}</td>
    </tr>`).join('');
  document.querySelectorAll('#allCasesTable tr.case-row').forEach(tr => {
    tr.addEventListener('click', () => {
      loadAyah(parseInt(tr.dataset.suraid,10), parseInt(tr.dataset.verseid,10));
      closeAllCases();
    });
  });
  document.getElementById('allCasesOverlay').classList.add('show');
}
function closeAllCases(e) {
  if (e && e.target.id !== 'allCasesOverlay') return;
  document.getElementById('allCasesOverlay').classList.remove('show');
}

let currentWordCtx = null;
function openSelectionExplain(lo, hi) {
  if (!currentCase) return;
  const phrase = currentWords.slice(lo, hi + 1).join(' ');
  const isTarget = currentRange[0] !== -1 && lo <= currentRange[1] && hi >= currentRange[0];
  currentWordCtx = { suraid: currentCase.suraid, verseid: currentCase.verseid, lo, hi, phrase };
  document.getElementById('wordTitle').textContent = phrase;
  document.getElementById('wordTitle').style.color = isTarget ? currentCase.color : '#F0C755';
  document.getElementById('wordContext').textContent =
    `سورة ${currentCase.suraname} — الآية ${currentCase.verseid}` + (isTarget ? ` — ${currentCase.title}` : '');
  document.getElementById('wordResult').textContent = isTarget
    ? currentCase.letters
    : 'كلمة عادية — موضع الإدغام في هذه الآية مظلَّل بلون مختلف.';
  document.getElementById('clipStatus').textContent = '';
  document.getElementById('wordQuestion').value = '';
  document.getElementById('wordOverlay').classList.add('show');
  clearSelection();
}
function closeWordModal(e) {
  if (e && e.target.id !== 'wordOverlay') return;
  document.getElementById('wordOverlay').classList.remove('show');
}

function playClipReciter(reciter) {
  if (!currentWordCtx) return;
  const status = document.getElementById('clipStatus');
  const p = new URLSearchParams({
    suraid: currentWordCtx.suraid, verseid: currentWordCtx.verseid, reciter,
    type: 'range', lo: currentWordCtx.lo, hi: currentWordCtx.hi,
  });
  status.textContent = '⏳ جارٍ التحضير...';
  clipPlayer.src = `/api/${API_PREFIX}/clip?` + p.toString();
  clipPlayer.play().then(() => { status.textContent = ''; })
    .catch(async () => {
      try {
        const r = await fetch(`/api/${API_PREFIX}/clip?` + p.toString());
        const j = await r.json();
        status.textContent = '⚠ ' + (j.error || 'تعذّر تشغيل المقطع.');
      } catch (e) { status.textContent = '⚠ تعذّر تشغيل المقطع.'; }
    });
}

async function askAI() {
  if (!currentWordCtx || !currentCase) return;
  const { phrase, suraid, verseid } = currentWordCtx;
  const question = document.getElementById('wordQuestion').value.trim();
  if (!question) return;
  const resultBox = document.getElementById('wordResult');
  resultBox.textContent = '...جاري التفكير';
  try {
    const r = await fetch(`/api/${API_PREFIX}/explain`, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ word: phrase, sura: currentCase.suraname, verse: verseid, question,
                              ruling: currentCase.title })
    });
    const j = await r.json();
    resultBox.textContent = j.answer || 'تعذّر جلب الإجابة.';
  } catch (e) {
    resultBox.textContent = 'تعذّر الاتصال بالخدمة.';
  }
}

(async function init() {
  await loadReaders();
  await loadSuras();
  await loadList();
  const first = allCasesList[0];
  if (first) await loadAyah(first.suraid, first.verseid);
})();
</script>
</body>
</html>'''

    @app.route(home_path if as_blueprint else '/')
    def index():
        return (HTML.replace('__TITLE__', title)
                    .replace('__SUBTITLE__', subtitle)
                    .replace('__API_PREFIX__', api_prefix))

    @app.route(f'/api/{api_prefix}/list')
    def api_list():
        return jsonify([{'idx': i, 'title': c['title'], 'suraid': c['suraid'], 'verseid': c['verseid'],
                          'suraname': c.get('suraname', ''), 'word': c.get('word', ''), 'color': c.get('color', '#D4A843')}
                         for i, c in enumerate(cases)])

    @app.route(f'/api/{api_prefix}/suras')
    def api_suras():
        conn = get_db(); cur = conn.cursor()
        try:
            cur.execute('SELECT DISTINCT SURAID, SURANAME FROM mushafnew ORDER BY SURAID')
            rows = cur.fetchall()
        except Exception:
            rows = []
        conn.close()
        return jsonify([{'suraid': r[0], 'suraname': r[1]} for r in rows])

    @app.route(f'/api/{api_prefix}/verses')
    def api_verses():
        suraid = request.args.get('suraid', type=int)
        conn = get_db(); cur = conn.cursor()
        try:
            cur.execute('SELECT DISTINCT VERSEID FROM mushafnew WHERE SURAID=? ORDER BY VERSEID', (suraid,))
            rows = [r[0] for r in cur.fetchall()]
        except Exception:
            rows = []
        conn.close()
        return jsonify(rows)

    @app.route(f'/api/{api_prefix}/ayah')
    def api_ayah():
        """يعرض أي سورة/آية يختارها المستخدم — إن كانت إحدى الحالات
        الموثّقة يُرجع تفاصيلها كاملة (matched=true)، وإلا يُرجع نص
        الآية مجرّداً (matched=false) بنفس أسلوب _load_ayah الأصلي."""
        suraid  = request.args.get('suraid', type=int)
        verseid = request.args.get('verseid', type=int)
        idx = next((i for i, c in enumerate(cases) if c['suraid'] == suraid and c['verseid'] == verseid), None)
        if idx is not None:
            payload = _case_payload(idx)
            payload['matched'] = True
            return jsonify(payload)
        conn = get_db(); cur = conn.cursor()
        cur.execute('SELECT SURANAME, ayahtext FROM mushafnew WHERE SURAID=? AND VERSEID=? LIMIT 1', (suraid, verseid))
        r = cur.fetchone(); conn.close()
        if not r:
            return jsonify({'error': 'غير موجود'}), 404
        return jsonify({
            'idx': None, 'title': None, 'suraid': suraid, 'verseid': verseid,
            'suraname': r[0] or '', 'aya': _clean_aya(r[1] or ''), 'word': '',
            'makhraj': '', 'letters': '', 'pronounce': '', 'note': None,
            'color': None, 'matched': False,
        })

    @app.route(f'/api/{api_prefix}/random')
    def api_random():
        idx = random.randrange(len(cases))
        c = cases[idx]
        return jsonify({'idx': idx, 'suraid': c['suraid'], 'verseid': c['verseid']})

    if not as_blueprint:
        @app.route('/api/readers')
        def api_readers():
            readers = []
            if os.path.isdir(BASE_DIR):
                for f in sorted(os.listdir(BASE_DIR)):
                    if f in SKIP:
                        continue
                    fp = os.path.join(BASE_DIR, f)
                    if not os.path.isdir(fp):
                        continue
                    files = os.listdir(fp)
                    aya_mp3s = [x for x in files if x.endswith('.mp3') and len(x) == 10]
                    if aya_mp3s:
                        readers.append({'id': f, 'label': READER_NAMES.get(f, f)})
            if not readers:
                readers.append({'id': 'Aya1Aya', 'label': 'مشاري راشد العفاسي'})
            return jsonify(readers)

        @app.route('/audio/<reader>/<fname>')
        def serve_audio(reader, fname):
            d = os.path.join(BASE_DIR, reader)
            if os.path.isdir(d):
                return send_from_directory(d, fname)
            return '', 404

    @app.route(f'/api/{api_prefix}/clip')
    def api_clip():
        if not _WORD_AUDIO_OK:
            return jsonify({'error': 'ميزة النطق الدقيق غير متوفرة: ضع word_audio_helper.py بجانب هذا الملف.'}), 404
        suraid  = request.args.get('suraid')
        verseid = request.args.get('verseid')
        reciter = request.args.get('reciter', 'alafasy')
        ctype   = request.args.get('type', 'word')
        if not suraid or not verseid:
            return jsonify({'error': 'بيانات ناقصة.'}), 400
        conn = get_db(); cur = conn.cursor()
        cur.execute('SELECT ayahtext FROM mushafnew WHERE SURAID=? AND VERSEID=? LIMIT 1', (suraid, verseid))
        r = cur.fetchone(); conn.close()
        aya_text = (r[0] if r else '') or ''
        if not aya_text:
            return jsonify({'error': 'تعذّر جلب نص الآية.'}), 404

        readers_dict = _get_readers_dict()
        if ctype == 'range':
            try:
                lo, hi = int(request.args.get('lo')), int(request.args.get('hi'))
            except (TypeError, ValueError):
                return jsonify({'error': 'مجال كلمات غير صالح.'}), 400
            clip_path, info = prepare_range_clip(BASE_DIR, readers_dict, suraid, verseid, aya_text, lo, hi, reciter)
        else:
            word = request.args.get('word', '')
            clip_path, info = prepare_word_clip(BASE_DIR, readers_dict, suraid, verseid, aya_text, word, reciter)
        if not clip_path:
            return jsonify({'error': info or 'تعذّر تجهيز المقطع.'}), 404
        return send_file(clip_path, mimetype='audio/mpeg')

    @app.route(f'/api/{api_prefix}/explain', methods=['POST'])
    def api_explain():
        import http.client as _hc
        data     = request.get_json(force=True)
        word     = data.get('word', '')
        sura     = data.get('sura', '')
        verse    = data.get('verse', '')
        question = data.get('question', f'ما حكم إدغام {word} في القرآن الكريم؟')
        ruling   = data.get('ruling', '')

        ruling_info = f'\nالحكم المؤكد من قاعدة البيانات: {ruling}' if ruling else ''
        API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

        try:
            system = ("You are an expert in Quran Tajweed specializing in Idgham Mutajanisayn/"
                      "Mutaqaribayn/Mutamathilayn (homogeneous/close/identical letter assimilation) rules. "
                      "Answer briefly in max 3-4 lines. "
                      "CRITICAL: The ruling provided from the database is CORRECT - never contradict it. "
                      "If question is in Arabic answer in Arabic only, otherwise match the question's language. "
                      "No markdown formatting. Plain text only.")
            prompt = f"Quran phrase: {word}\nSura: {sura}, Verse: {verse}{ruling_info}\nQuestion: {question}"
            body = json.dumps({
                'model': 'claude-sonnet-4-6', 'max_tokens': 200,
                'system': system, 'messages': [{'role': 'user', 'content': prompt}]
            }, ensure_ascii=False).encode('utf-8')
            conn = _hc.HTTPSConnection('api.anthropic.com', timeout=15)
            conn.request('POST', '/v1/messages', body=body, headers={
                'Content-Type': 'application/json; charset=utf-8',
                'x-api-key': API_KEY, 'anthropic-version': '2023-06-01'
            })
            resp = json.loads(conn.getresponse().read().decode('utf-8'))
            conn.close()
            return jsonify({'answer': resp['content'][0]['text']})
        except Exception as e:
            err = str(e).encode('ascii', 'replace').decode('ascii')
            return jsonify({'answer': f'Error: {err}'})

    return app


def run(app, port):
    threading.Timer(1.5, lambda: webbrowser.open(f'http://localhost:{port}')).start()
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
