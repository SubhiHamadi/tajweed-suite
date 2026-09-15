"""
sakt_web_app.py — السكت في القرآن الكريم (نسخة الويب)
نسخة Flask من sakt_app.py، بنفس هوية idgham_web_app.py البصرية (تنقل
بالآية مباشرة، لأن مواضع السكت قليلة جداً — أربعة متفق عليها وموضع
خامس مختلَف فيه، فقائمة اختيار مباشرة أنسب من التنقل بالصفحة).
يعمل على بورت 5046.
"""
import os, re, sys, sqlite3, json
from flask import Flask, Blueprint, jsonify, request, send_from_directory, send_file

bp = Blueprint('sakt', __name__)
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def _find_db_path():
    candidates = [
        os.path.join(BASE_DIR, 'quran.db'),
        r'D:\family\quran.db',
        r'E:\family\quran.db',
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return candidates[0]

DB_PATH = _find_db_path()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

SAKT_COLOR = '#B39DDB'  # نفس لون بطاقة المجموعة في sakt_app.py

SAKT_DEFINITION = (
    'قطع الصوت زمناً يسيراً (أقصر من زمن التنفس) عند حرف معيّن بنية متابعة '
    'القراءة فوراً من غير تنفس، تمييزاً بين كلمتين قد يُظَن اتصالهما في '
    'المعنى لولا هذا السكت.\n\n'
    'مواضع السكت الأربعة المتفق عليها عند حفص عن عاصم:\n'
    '  ١) الكهف ١ — عِوَجًا ۜ قَيِّمًا\n'
    '  ٢) يس ٥٢ — مَّرْقَدِنَا ۜ هَـٰذَا\n'
    '  ٣) القيامة ٢٧ — مَنْ ۜ رَاقٍ\n'
    '  ٤) المطففين ١٤ — بَلْ ۜ رَانَ\n\n'
    'وموضع خامس مختلَف في حكمه (سكتة أو وقف):\n'
    '  ٥) الحاقة ٢٨ — مَالِيَهْ ۜ هَلَكَ'
)

# ══════════════════════════════════════════════════════════════
#  تنظيف نص الآية
# ══════════════════════════════════════════════════════════════
_DECORATIVE_MARKS = '\u06DE\u06E9\u06DD'
def _clean_aya(text):
    if not text:
        return ''
    text = text.replace('\r\n', ' ').replace('\n', ' ')
    for ch in _DECORATIVE_MARKS:
        text = text.replace(ch, ' ')
    return re.sub(r'\s+', ' ', text).strip()

# ══════════════════════════════════════════════════════════════
#  القرّاء وملفات الصوت
# ══════════════════════════════════════════════════════════════
READER_NAMES = {
    'Aya1Aya' : 'مشاري راشد العفاسي',
    'Aya9Aya' : 'محمد صديق المنشاوي — المعلم',
    'AyaEAya' : '🇬🇧 Ibrahim Walk (English)',
}
SKIP = {'AyaAya', 'Husary', 'abdulstar', 'kolon', 'mnshawi'}

try:
    from word_audio_helper import prepare_word_clip, prepare_range_clip
    _WORD_AUDIO_OK = True
except Exception:
    _WORD_AUDIO_OK = False

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

# ══════════════════════════════════════════════════════════════
#  منطق تحميل موضع — منقول من LoadThread في sakt_app.py دون أي
#  تغيير في الاستعلامات
# ══════════════════════════════════════════════════════════════
def _load_ayah(suraid, verseid):
    conn = get_db(); cur = conn.cursor()
    cur.execute('''
        SELECT suraid,verseid,klmat,kseq,pagenum,itype,suraname,aya
        FROM saktdirect WHERE suraid=? AND verseid=? LIMIT 1
    ''', (suraid, verseid))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {
        'suraid': row[0], 'verseid': row[1], 'klmat': (row[2] or '').strip(),
        'kseq': row[3], 'page': row[4], 'itype': row[5], 'suraname': row[6],
        'aya': _clean_aya(row[7] or ''),
    }

def _random_ayah():
    conn = get_db(); cur = conn.cursor()
    cur.execute('SELECT suraid,verseid FROM saktdirect ORDER BY RANDOM() LIMIT 1')
    r = cur.fetchone()
    conn.close()
    return (r[0], r[1]) if r else (None, None)

def _list_positions():
    conn = get_db(); cur = conn.cursor()
    cur.execute('SELECT suraid,verseid,suraname,klmat FROM saktdirect ORDER BY suraid')
    rows = cur.fetchall()
    conn.close()
    return [{'suraid': r[0], 'verseid': r[1], 'suraname': r[2], 'klmat': r[3]} for r in rows]

# ══════════════════════════════════════════════════════════════
#  الواجهة (HTML/CSS/JS)
# ══════════════════════════════════════════════════════════════
HTML = r'''<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>السكت في القرآن الكريم</title>
<style>
:root {
  --navy:  #00BCD4; --navy2: #0A2040; --gold:  #D4A843; --gold2: #0D2847;
  --green: #00C853; --red:   #EF5350; --bg:    #020B18; --card:  #0D2847;
  --border:#1A3A5C; --text:  #F8F4EE; --muted: #B0BEC5; --sakt: #B39DDB;
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
.btn-play   { background:rgba(0,200,83,0.15); color:var(--green); border:1.5px solid var(--green); }
.btn-stop   { background:rgba(239,83,80,0.15); color:var(--red); border:1.5px solid var(--red); }
.btn-def    { background:rgba(179,157,219,0.15); color:var(--sakt); border:1.5px solid var(--sakt); }
.speed-bar { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.speed-label { font-size:12px; color:var(--gold); font-weight:bold; white-space:nowrap; }
.speed-btn { padding:5px 11px; border-radius:20px; font-size:12px; font-weight:bold;
             border:1.5px solid var(--navy); background:#0A2040; color:var(--navy); cursor:pointer; }
.speed-btn.active { background:var(--navy); color:#020B18; }

.legend { display:flex; gap:6px; padding:8px 14px; flex-wrap:wrap;
          background:var(--bg); border-bottom:1px solid var(--border); align-items:center; }
.legend-item { display:flex; align-items:center; gap:5px; font-size:12px; font-weight:bold;
               padding:3px 10px; border-radius:20px; white-space:nowrap;
               background:rgba(179,157,219,0.12); color:var(--sakt); border:2px solid var(--sakt); }

.info-bar { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap;
            padding:8px 14px; background:var(--card); border-bottom:1px solid var(--border); font-size:13px; }
.info-aya { color:#F0C755; font-weight:bold; }
.cnt-badge { padding:2px 10px; border-radius:20px; font-size:12px; font-weight:bold;
             background:rgba(179,157,219,0.15); color:var(--sakt); border:1px solid var(--sakt); }

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

#wordOverlay, .help-overlay { display:none; position:fixed; top:0;left:0;right:0;bottom:0;
  background:rgba(0,0,0,0.65); z-index:2000; align-items:center; justify-content:center; padding:16px; }
#wordOverlay.show, .help-overlay.show { display:flex; }
#wordModal, .help-modal { background:#0D2847; border-radius:16px; padding:20px; max-width:420px;
  width:100%; max-height:82vh; overflow-y:auto; direction:rtl;
  box-shadow:0 8px 40px rgba(0,0,0,0.6); border:2px solid rgba(212,168,67,0.55); }
#wordTitle { font-family:"KFGQPC_HAFS_Uthmanic_Script_H","Traditional Arabic";
             font-size:26px; text-align:center; margin-bottom:6px; font-weight:bold; color:var(--sakt); }
#wordContext { font-size:12px; color:var(--muted); text-align:center; margin-bottom:14px; }
#wordResult { background:#061525; border-radius:10px; padding:14px; font-size:15px;
              line-height:185%; color:var(--text); border:1px solid var(--border); min-height:40px;
              margin-bottom:10px; white-space:pre-line; }
.word-input-row { display:flex; gap:8px; margin-bottom:10px; }
.word-input { flex:1; border:1.5px solid var(--border); border-radius:10px; padding:8px 12px;
              font-family:"Traditional Arabic",Arial; font-size:14px; direction:rtl; background:#061525; color:var(--text); }
.word-ask-btn { background:var(--navy); color:#020B18; border:none; border-radius:10px;
                padding:8px 14px; font-size:13px; font-weight:bold; cursor:pointer; }
#wordClose, .help-close { width:100%; margin-top:6px; padding:9px; border:1.5px solid var(--red);
  border-radius:10px; background:rgba(239,83,80,0.1); cursor:pointer; font-size:14px; color:var(--red); }

@media(max-width:480px) { .ctrl-row { flex-direction:column; align-items:stretch; } button, select { width:100%; } }
</style>
</head>
<body>

<header>
  <div class="header-title">السكت في القرآن الكريم</div>
  <div class="header-sub">قطع الصوت زمناً يسيراً بلا تنفس بين كلمتين</div>
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
    <span class="ctrl-label">الموضع:</span>
    <select id="selCase" onchange="onCasePick()"></select>
    <button class="btn-random" onclick="loadRandom()">🔀 موضع آخر</button>
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
  <div class="ctrl-row" style="justify-content:center;">
    <button class="btn-def" onclick="showHelp()">📚 تعريف السكت ومواضعه</button>
  </div>
</div>

<div class="legend"><div class="legend-item">● كلمة السكت</div></div>

<div class="info-bar">
  <div class="info-aya" id="infoAya">—</div>
  <div class="cnt-badge" id="infoPage"></div>
</div>

<div class="ayah-wrap">
  <div class="ayah-box" id="ayahBox">جارٍ التحميل...</div>
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
      <input type="text" class="word-input" id="wordQuestion" placeholder="اسأل عن هذا الموضع...">
      <button class="word-ask-btn" onclick="askAI()">اسأل</button>
    </div>
    <button id="wordClose" onclick="closeWordModal()">✕ إغلاق</button>
  </div>
</div>

<div class="help-overlay" id="helpOverlay" onclick="hideHelp(event)">
  <div class="help-modal" style="text-align:center;">
    <div style="font-size:16px;font-weight:bold;color:#F0C755;margin-bottom:12px;border-bottom:2px solid var(--gold);padding-bottom:10px;">📚 السكت</div>
    <div id="helpDef" style="font-size:14px;line-height:200%;color:var(--text);white-space:pre-line;text-align:right;"></div>
    <button class="help-close" onclick="hideHelp()">✕ إغلاق</button>
  </div>
</div>

<script>
let currentSpeed = 1.0;
let currentAyah  = null;
let currentWords = [];
let currentSaktIdx = -1;
const audio = document.getElementById('audioPlayer');
const clipPlayer = document.getElementById('clipPlayer');
const SAKT_DEFINITION = __SAKT_DEF_JSON__;

async function loadReaders() {
  const r = await fetch('/api/readers');
  const d = await r.json();
  document.getElementById('selReader').innerHTML =
    d.map(x => `<option value="${x.id}">${x.label}</option>`).join('');
}

async function loadPositions() {
  const r = await fetch('/api/sakt/list');
  const d = await r.json();
  document.getElementById('selCase').innerHTML = d.map(p =>
    `<option value="${p.suraid}-${p.verseid}">سورة ${p.suraname} — آية ${p.verseid} (${p.klmat})</option>`).join('');
}

function onCasePick() {
  const [suraid, verseid] = document.getElementById('selCase').value.split('-');
  loadAyah(suraid, verseid);
}

function setSpeed(v, btn) {
  currentSpeed = v; audio.playbackRate = v;
  document.querySelectorAll('.speed-btn').forEach(b => b.classList.toggle('active', b === btn));
}
function stopAudio() { audio.pause(); audio.currentTime = 0; }
function playAyah() {
  if (!currentAyah) return;
  const reader = document.getElementById('selReader').value;
  const fname = String(currentAyah.suraid).padStart(3,'0') + String(currentAyah.verseid).padStart(3,'0') + '.mp3';
  audio.src = `/audio/${reader}/${fname}`;
  audio.playbackRate = currentSpeed;
  audio.play().catch(() => alert('⚠️ ملف الصوت غير متوفر لهذا القارئ.'));
}

// ── تحديد نطاق حر بالسحب (drag-select) — آية واحدة فقط، فلا حاجة
// لمفاتيح متعددة كما في التطبيقات متعددة الآيات ──
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
// قبل المقارنة — نص quran.db الفعلي قد يختلف رسمًا عثمانيًا عن الكلمة
// المخزَّنة (سكون مختلف، وقف ملتصق بلا مسافة، همزة وصل بدل ألف عادية).
function bareChar(s) {
  return (s || '')
    .replace(/[\u064B-\u065F\u0610-\u061A\u06D6-\u06ED\u0670\u08D3-\u08FF\u0640]/g, '')
    .replace(/[\u0622\u0623\u0625\u0671]/g, '\u0627');
}
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

function renderAyah(d) {
  currentAyah = d;
  const pageStr = d.page ? `صفحة ${d.page}` : '';
  document.getElementById('infoAya').textContent = `سورة ${d.suraname} — الآية ${d.verseid}`;
  document.getElementById('infoPage').textContent = pageStr;

  const words = (d.aya || '').split(/\s+/).filter(Boolean);
  let saktRange = [-1, -1];
  if (d.klmat) {
    saktRange = findWordRange(words, d.klmat);
  }
  const [saktLo, saktHi] = saktRange;
  currentWords = words; currentSaktIdx = saktLo;

  document.getElementById('ayahBox').innerHTML = words.map((w, i) =>
    (saktLo !== -1 && i >= saktLo && i <= saktHi)
      ? `<span class="word-tok" data-idx="${i}" style="color:var(--sakt);font-weight:bold;">${w}</span>`
      : `<span class="word-tok" data-idx="${i}" style="color:var(--text)">${w}</span>`
  ).join(' ');
  initDragSelect();
  clearSelection();
}

async function loadAyah(suraid, verseid) {
  const r = await fetch(`/api/sakt/ayah?suraid=${suraid}&verseid=${verseid}`);
  const d = await r.json();
  if (d.error) return;
  document.getElementById('selCase').value = `${d.suraid}-${d.verseid}`;
  renderAyah(d);
}

async function loadRandom() {
  const r = await fetch('/api/sakt/ayah?random=1');
  const d = await r.json();
  if (d.error) return;
  document.getElementById('selCase').value = `${d.suraid}-${d.verseid}`;
  renderAyah(d);
}

let currentWordCtx = null;
function openSelectionExplain(lo, hi) {
  if (!currentAyah) return;
  const phrase = currentWords.slice(lo, hi + 1).join(' ');
  const isSakt = currentSaktIdx !== -1 && lo <= currentSaktIdx && currentSaktIdx <= hi;
  currentWordCtx = { suraid: currentAyah.suraid, verseid: currentAyah.verseid,
                      suraname: currentAyah.suraname, lo, hi, phrase, isSakt };
  document.getElementById('wordTitle').textContent = phrase;
  document.getElementById('wordTitle').style.color = isSakt ? 'var(--sakt)' : '#F0C755';
  document.getElementById('wordContext').textContent =
    `سورة ${currentAyah.suraname} — الآية ${currentAyah.verseid}` + (isSakt ? ' — كلمة السكت' : '');
  document.getElementById('wordResult').textContent = isSakt
    ? SAKT_DEFINITION
    : 'كلمة عادية — كلمة السكت في هذه الآية مظلَّلة بلون مختلف.';
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
  clipPlayer.src = '/api/sakt/clip?' + p.toString();
  clipPlayer.play().then(() => { status.textContent = ''; })
    .catch(async () => {
      try {
        const r = await fetch('/api/sakt/clip?' + p.toString());
        const j = await r.json();
        status.textContent = '⚠ ' + (j.error || 'تعذّر تشغيل المقطع.');
      } catch (e) { status.textContent = '⚠ تعذّر تشغيل المقطع.'; }
    });
}

async function askAI() {
  if (!currentWordCtx) return;
  const { phrase, suraname, verseid, isSakt } = currentWordCtx;
  const question = document.getElementById('wordQuestion').value.trim();
  if (!question) return;
  const resultBox = document.getElementById('wordResult');
  resultBox.textContent = '...جاري التفكير';
  try {
    const r = await fetch('/api/sakt/explain', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ word: phrase, sura: suraname, verse: verseid, question,
                              ruling: isSakt ? 'سكت' : '' })
    });
    const j = await r.json();
    resultBox.textContent = j.answer || 'تعذّر جلب الإجابة.';
  } catch (e) {
    resultBox.textContent = 'تعذّر الاتصال بالخدمة.';
  }
}

function showHelp() {
  document.getElementById('helpDef').textContent = SAKT_DEFINITION;
  document.getElementById('helpOverlay').classList.add('show');
}
function hideHelp(e) {
  if (e && e.target.id !== 'helpOverlay') return;
  document.getElementById('helpOverlay').classList.remove('show');
}

(async function init() {
  await loadReaders();
  await loadPositions();
  await loadRandom();
})();
</script>
</body>
</html>'''

# ══════════════════════════════════════════════════════════════
#  المسارات (Routes)
# ══════════════════════════════════════════════════════════════
@bp.route('/sakt')
def index():
    return HTML.replace('__SAKT_DEF_JSON__', json.dumps(SAKT_DEFINITION, ensure_ascii=False))

@bp.route('/api/sakt/list')
def api_list():
    return jsonify(_list_positions())

@bp.route('/api/sakt/ayah')
def api_ayah():
    if request.args.get('random'):
        suraid, verseid = _random_ayah()
        if suraid is None:
            return jsonify({'error': 'لا توجد مواضع سكت في قاعدة البيانات.'}), 404
    else:
        suraid  = request.args.get('suraid', type=int)
        verseid = request.args.get('verseid', type=int)
    d = _load_ayah(suraid, verseid)
    if not d:
        return jsonify({'error': 'تعذّر إيجاد هذا الموضع.'}), 404
    return jsonify(d)

@bp.route('/api/sakt/clip')
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

@bp.route('/api/sakt/explain', methods=['POST'])
def api_explain():
    import http.client as _hc
    data     = request.get_json(force=True)
    word     = data.get('word', '')
    sura     = data.get('sura', '')
    verse    = data.get('verse', '')
    question = data.get('question', f'ما حكم السكت في كلمة {word} في القرآن الكريم؟')
    ruling   = data.get('ruling', '')

    ruling_info = f'\nالحكم المؤكد من قاعدة البيانات: {ruling}' if ruling else ''
    API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

    try:
        system = ("You are an expert in Quran Tajweed specializing in Saktah (brief pause) rules. "
                  "Answer briefly in max 3-4 lines. "
                  "CRITICAL: The ruling provided from the database is CORRECT - never contradict it. "
                  "If question is in Arabic answer in Arabic only, otherwise match the question's language. "
                  "No markdown formatting. Plain text only.")
        prompt = f"Quran word: {word}\nSura: {sura}, Verse: {verse}{ruling_info}\nQuestion: {question}"
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


