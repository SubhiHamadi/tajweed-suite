"""
lazm_web_app.py — أحكام المد اللازم في القرآن الكريم
يعمل على بورت 5009
"""
import os, re, sys, sqlite3, json
from flask import Flask, Blueprint, jsonify, request, send_from_directory, send_file

bp = Blueprint('lazm', __name__)
import sys
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.path.join(BASE_DIR, 'quran.db')

ITYPE_COLORS = {
    'لازم كلمي مثقل' : '#FF6F00',
    'لازم كلمي مخفف' : '#FF9800',
    'لازم حرفي مثقل' : '#00BCD4',
}

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_color(madd_type):
    for k, v in ITYPE_COLORS.items():
        if k.strip() == (madd_type or '').strip(): return v
    return '#FF6F00'

READER_NAMES = {
    'Aya1Aya' : 'مشاري راشد العفاسي',
    'Aya9Aya' : 'محمد صديق المنشاوي — المعلم',
    'AyaEAya' : '🇬🇧 Ibrahim Walk (English)',
    'AyaUAya' : '🇵🇰 د. فرحت هاشمي (اردو)',
}
SKIP = {'AyaAya','Husary','abdulstar','kolon','mnshawi'}

# ── نطق دقيق للكلمة/العبارة المحددة بأصوات الشيوخ الثلاثة (اختياري:
# يعمل التطبيق طبيعياً بدونه، وفقط أزرار النطق الدقيق تُعطّل) ──
try:
    from word_audio_helper import prepare_word_clip, prepare_range_clip
    _WORD_AUDIO_OK = True
except Exception:
    _WORD_AUDIO_OK = False

def _get_readers_dict():
    d = {}
    if os.path.isdir(BASE_DIR):
        for f in os.listdir(BASE_DIR):
            if f in SKIP: continue
            fp = os.path.join(BASE_DIR, f)
            if os.path.isdir(fp):
                d[f] = fp
    return d

# تنظيف نص الآية بنفس القواعد التي يعتمدها word_audio_helper داخلياً
# (إزالة الرموز الزخرفية ۞۩۝ وضغط أي مسافات متعددة إلى مسافة واحدة) —
# ضروري لضمان تطابق فهرسة الكلمات بين ما يُرسَل للواجهة وما يحسبه
# word_audio_helper لاحقاً عند تحديد توقيت كلمة بفهرسها، وإلا قد ينزاح
# الفهرس فيُشغَّل صوت كلمة مختلفة عن المحدَّدة أو يفشل تحديد توقيتها.
_DECORATIVE_MARKS = '\u06DE\u06E9\u06DD'
def _clean_aya(text):
    if not text:
        return ''
    text = text.replace('\\r\\n', ' ').replace('\\n', ' ')
    for ch in _DECORATIVE_MARKS:
        text = text.replace(ch, ' ')
    return re.sub(r'\s+', ' ', text).strip()

HTML = '''<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>أحكام المد اللازم في القرآن الكريم</title>
<style>
:root {
  --navy:  #00BCD4;
  --navy2: #0A2040;
  --gold:  #D4A843;
  --gold2: #0D2847;
  --green: #00C853;
  --green2:#0A2040;
  --red:   #EF5350;
  --red2:  #0A2040;
  --bg:    #020B18;
  --card:  #0D2847;
  --border:#1A3A5C;
  --text:  #F8F4EE;
  --muted: #B0BEC5;
  --lkm:   #FF4081;
  --lkf:   #FFD700;
  --lhm:   #00E5FF;
  --lhf:   #00BCD4;
}
* { box-sizing:border-box; margin:0; padding:0; }
body {
  font-family:"Traditional Arabic","Noto Naskh Arabic",Arial,sans-serif;
  background:var(--bg); color:var(--text);
  direction:rtl; min-height:100vh; font-size:15px;
}
/* ── Header ── */
header {
  background:linear-gradient(135deg,#020B18 0%,#0A2848 50%,#020B18 100%);
  border-bottom:4px solid var(--gold);
  padding:14px 16px 12px; text-align:center;
  box-shadow:0 2px 8px rgba(212,168,67,0.15);
}
.header-title {
  font-size:clamp(15px,4.5vw,22px); font-weight:bold;
  color:#F0C755; margin-bottom:3px; letter-spacing:0.3px;
  text-shadow:0 0 12px rgba(212,168,67,0.5);
}
.header-sub { font-size:clamp(10px,2.8vw,13px); color:#00E5FF; margin-bottom:10px; }
.authors { display:flex; gap:8px; justify-content:center; flex-wrap:wrap; }
.author-card {
  background:rgba(212,168,67,0.08); border:1px solid rgba(212,168,67,0.25);
  border-radius:8px; padding:5px 12px; font-size:clamp(9px,2.5vw,12px); text-align:center;
}
.author-name { color:#F0C755; font-weight:bold; }
.author-info { color:#00E5FF; font-size:0.88em; }

/* ── Controls ── */
.controls { background:var(--card); border-bottom:1px solid var(--border); padding:12px 14px; }
.ctrl-row { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-bottom:9px; }
.ctrl-row:last-child { margin-bottom:0; }
.ctrl-label { font-size:clamp(11px,3vw,13px); color:var(--gold); white-space:nowrap; font-weight:bold; }
select, input[type=number] {
  background:#0A2040; border:1.5px solid var(--border); border-radius:8px;
  padding:7px 10px; color:var(--text); font-family:"Traditional Arabic",Arial;
  font-size:13px; flex:1; min-width:80px; appearance:none; cursor:pointer;
}
select:focus { border-color:var(--gold); outline:none; }
button { border:none; border-radius:8px; padding:8px 14px; font-family:"Traditional Arabic",Arial;
         font-size:13px; font-weight:bold; cursor:pointer; white-space:nowrap; }
.btn-go     { background:var(--gold); color:#020B18; }
.btn-random { background:rgba(0,188,212,0.15); color:var(--navy); border:1.5px solid var(--navy); }
.btn-prev   { background:rgba(0,188,212,0.15); color:var(--navy); border:1.5px solid var(--navy); }
.btn-next   { background:rgba(0,188,212,0.15); color:var(--navy); border:1.5px solid var(--navy); }
.btn-play   { background:rgba(0,200,83,0.15); color:var(--green); border:1.5px solid var(--green); }
.btn-stop   { background:rgba(239,83,80,0.15); color:var(--red); border:1.5px solid var(--red); }
.btn-dl     { background:rgba(0,200,83,0.15); color:var(--green); border:1.5px solid var(--green); }
.btn-dl:disabled { opacity:0.4; cursor:not-allowed; }
.btn-toggle { padding:5px 12px; border-radius:20px; font-size:12px; font-weight:bold;
              border:1.5px solid var(--border); background:#0A2040; color:var(--muted); cursor:pointer; }
.btn-toggle.active { color:#020B18; border-color:transparent; }
.btn-en  { border-color:var(--navy); color:var(--navy); }
.btn-en.active  { background:var(--navy); }
.btn-tf  { border-color:var(--border); color:var(--gold); }
.btn-tf.active  { background:var(--gold); }
.btn-ur  { border-color:#CE93D8; color:#CE93D8; }
.btn-ur.active  { background:#CE93D8; }
.btn-ku  { border-color:var(--green); color:var(--green); }
.btn-ku.active  { background:var(--green); }
.btn-tr  { border-color:var(--red); color:var(--red); }
.btn-tr.active  { background:var(--red); }
.btn-az  { border-color:#26A69A; color:#26A69A; }
.btn-az.active  { background:#26A69A; }
.speed-bar { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.speed-label { font-size:12px; color:var(--gold); font-weight:bold; white-space:nowrap; }
.speed-btn { padding:5px 11px; border-radius:20px; font-size:12px; font-weight:bold;
             border:1.5px solid var(--navy); background:#0A2040; color:var(--navy); cursor:pointer; }
.speed-btn.active { background:var(--navy); color:#020B18; border-color:var(--navy); }

/* ── Legend ── */
.legend { display:flex; gap:8px; padding:8px 14px; flex-wrap:wrap;
          background:var(--bg); border-bottom:1px solid var(--border); align-items:center; }
.legend-item { display:flex; align-items:center; gap:5px; font-size:12px; font-weight:bold;
               padding:3px 10px; border-radius:20px; white-space:nowrap; }
.leg-lkm { background:rgba(255,64,129,0.1); color:var(--lkm); border:2px solid var(--lkm); }
.leg-lkf { background:rgba(255,215,0,0.1); color:var(--lkf); border:2px solid var(--lkf); }
.leg-lhm { background:rgba(0,229,255,0.1); color:var(--lhm); border:2px solid var(--lhm); }
.leg-lhf { background:rgba(0,188,212,0.1); color:var(--lhf); border:2px solid var(--lhf); }

/* ── Info bar ── */
.info-bar { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap;
            padding:8px 14px; background:var(--card); border-bottom:1px solid var(--border); font-size:13px; }
.info-sura { color:#F0C755; font-weight:bold; }
.info-counts { display:flex; gap:6px; flex-wrap:wrap; }
.cnt-badge { padding:2px 10px; border-radius:20px; font-size:12px; font-weight:bold; }

/* ── Ayah Box ── */
.ayah-wrap { padding:12px 14px 4px; }
.ayah-box {
  background:linear-gradient(180deg,#0D2847 0%,#0A2040 100%);
  border:2px solid rgba(212,168,67,0.44); border-radius:16px;
  padding:18px 20px; font-family:"KFGQPC_HAFS_Uthmanic_Script_H","Traditional Arabic";
  font-size:clamp(22px,6vw,30px); line-height:270%;
  direction:rtl; text-align:right; color:#F8F4EE;
  box-shadow:0 0 20px rgba(212,168,67,0.15);
}
.translation-box {
  margin:0 14px 8px; padding:10px 14px; border-radius:10px;
  font-size:14px; line-height:185%; display:none;
  border:1px solid var(--border); background:#0A2040;
  direction:rtl; text-align:right;
}
.translation-box.show { display:block; }

/* ── Table ── */
.table-wrap { margin:12px 14px 20px; border:1px solid var(--border); border-radius:14px; overflow:hidden; }
.table-header { background:linear-gradient(90deg,#0D3060,#0D2847); padding:10px 14px; color:#F0C755;
                font-weight:bold; font-size:13px; border-bottom:2px solid var(--gold); }
table { width:100%; border-collapse:collapse; background:#061525; }
th { background:#0D3060; color:#F0C755; padding:9px 6px;
     border-bottom:2px solid var(--gold); font-size:12px; font-weight:bold; }
td { padding:9px 6px; border-bottom:1px solid var(--border); text-align:center; font-size:12px; color:var(--text); }
tr:nth-child(even) td { background:#0A2040; }
tr:last-child td { border-bottom:none; }
.word-cell { font-family:"KFGQPC_HAFS_Uthmanic_Script_H","Traditional Arabic";
             font-size:clamp(18px,5vw,24px); font-weight:bold; line-height:200%; }
.badge { display:inline-block; padding:2px 9px; border-radius:20px; font-size:11px; font-weight:bold; border:1px solid; }
.legend-item.active { box-shadow:0 0 0 2px currentColor; opacity:1 !important; }
.legend-item.dimmed { opacity:0.3; }

/* ── Word Explain Popup ── */
#wordOverlay { display:none; position:fixed; top:0;left:0;right:0;bottom:0;
               background:rgba(0,0,0,0.65); z-index:2000; align-items:center; justify-content:center; }
#wordOverlay.show { display:flex; }
#wordModal { background:#0D2847; border-radius:16px; padding:20px; max-width:400px;
             width:92%; direction:rtl; box-shadow:0 8px 40px rgba(0,0,0,0.6);
             border:2px solid rgba(212,168,67,0.55); }
#wordTitle { font-family:"KFGQPC_HAFS_Uthmanic_Script_H","Traditional Arabic";
             font-size:28px; color:#F0C755; text-align:center; margin-bottom:6px; font-weight:bold; }
#wordContext { font-size:12px; color:var(--muted); text-align:center; margin-bottom:14px; }
#wordResult { background:#061525; border-radius:10px; padding:14px; font-size:15px;
              line-height:185%; color:var(--text); border:1px solid var(--border); min-height:50px; }
.word-suggestions { display:flex; gap:6px; flex-wrap:wrap; margin-bottom:10px; }
.word-suggest-btn { padding:4px 12px; border-radius:20px; font-size:12px; cursor:pointer;
                    border:1.5px solid var(--navy); background:rgba(0,188,212,0.1); color:var(--navy);
                    font-family:"Traditional Arabic",Arial; }
.word-suggest-btn:hover { background:var(--navy); color:#020B18; }
.word-input-row { display:flex; gap:8px; margin-bottom:10px; }
.word-input { flex:1; border:1.5px solid var(--border); border-radius:10px;
              padding:8px 12px; font-family:"Traditional Arabic",Arial;
              font-size:14px; direction:rtl; background:#061525; color:var(--text); }
.word-input:focus { border-color:var(--navy); outline:none; }
.word-ask-btn { background:var(--navy); color:#020B18; border:none; border-radius:10px;
                padding:8px 14px; font-size:13px; font-weight:bold; cursor:pointer;
                font-family:"Traditional Arabic",Arial; }
#wordClose { width:100%; margin-top:12px; padding:9px; border:1.5px solid var(--red);
             border-radius:10px; background:rgba(239,83,80,0.1); cursor:pointer; font-size:14px;
             color:var(--red); font-family:"Traditional Arabic",Arial; }

/* ── Help Modal ── */
.help-overlay { display:none; position:fixed; top:0;left:0;right:0;bottom:0;
                background:rgba(0,0,0,0.65); z-index:1000; align-items:center; justify-content:center; }
.help-overlay.show { display:flex; }
.help-modal { background:#0D2847; border-radius:16px; padding:20px; max-width:420px;
              width:92%; max-height:80vh; overflow-y:auto; direction:rtl;
              border:2px solid rgba(212,168,67,0.4); }
.help-title { font-size:18px; font-weight:bold; color:#F0C755;
              text-align:center; margin-bottom:16px; border-bottom:2px solid var(--gold); padding-bottom:10px; }
.help-tabs { display:flex; gap:6px; flex-wrap:wrap; margin-bottom:14px; justify-content:center; }
.help-tab { padding:6px 14px; border-radius:20px; font-size:13px; font-weight:bold;
            cursor:pointer; border:1.5px solid var(--border); background:#0A2040; color:var(--muted); }
.help-tab-lkm.active { background:var(--lkm); color:#020B18; border-color:var(--lkm); }
.help-tab-lkf.active { background:var(--lkf); color:#020B18; border-color:var(--lkf); }
.help-tab-lhm.active { background:var(--lhm); color:#020B18; border-color:var(--lhm); }
.help-tab-lhf.active { background:var(--lhf); color:#020B18; border-color:var(--lhf); }
.hcontent { display:none; }
.hcontent.show { display:block; }
.help-def { font-size:15px; line-height:190%; color:var(--text); margin-bottom:12px; }
.help-letters { background:#061525; border-radius:10px; padding:10px 14px;
                font-size:18px; text-align:center; margin-bottom:10px; line-height:200%; color:var(--text); }
.help-example { background:rgba(212,168,67,0.1); border-radius:10px; padding:10px 14px;
                font-size:16px; line-height:200%; border:1px solid var(--gold); color:var(--text); }
.help-ex-label { font-size:12px; color:var(--gold); margin-bottom:4px; }
.help-close { width:100%; margin-top:14px; padding:10px; border:1.5px solid var(--red);
              border-radius:10px; background:rgba(239,83,80,0.1); cursor:pointer; font-size:14px;
              color:var(--red); font-family:"Traditional Arabic",Arial; }

/* ── السحب لتحديد نطاق حر ── */
.word-tok { cursor:pointer; user-select:none; -webkit-user-select:none; }
.word-tok.dragsel { background:rgba(212,168,67,0.4); border-radius:4px; }

/* ── نافذة عرض كل الحالات ── */
#allCasesOverlay { display:none; position:fixed; top:0;left:0;right:0;bottom:0;
               background:rgba(0,0,0,0.65); z-index:2000; align-items:center; justify-content:center;
               padding:16px; }
#allCasesOverlay.show { display:flex; }
#allCasesModal { background:#0D2847; border-radius:16px; padding:18px; max-width:640px;
             width:100%; max-height:82vh; overflow-y:auto; direction:rtl;
             box-shadow:0 8px 40px rgba(0,0,0,0.6); border:2px solid rgba(212,168,67,0.55); }
#allCasesTitle { font-size:16px; font-weight:bold; color:#F0C755; text-align:center;
                 margin-bottom:4px; }
#allCasesCount { font-size:12px; color:var(--navy); text-align:center; margin-bottom:12px; }
#allCasesClose { width:100%; margin-top:12px; padding:9px; border:1.5px solid var(--red);
             border-radius:10px; background:rgba(239,83,80,0.1); cursor:pointer; font-size:14px;
             color:var(--red); font-family:"Traditional Arabic",Arial; }

@media(max-width:480px) {
  .ctrl-row { flex-direction:column; align-items:stretch; }
  button, select { width:100%; }
}
</style>
</head>
<body>

<header>
  <div class="header-title">أحكام المد اللازم في القرآن الكريم</div>
  <div class="header-sub">المد اللازم الكلمي والحرفي — المثقل والمخفف</div>
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
    <select id="selSura" onchange="loadVerses()"></select>
    <span class="ctrl-label">الآية:</span>
    <select id="selVerse"></select>
    <button class="btn-go" onclick="loadAyah()">عرض</button>
    <button class="btn-random" onclick="loadRandom()">🔀 عشوائية</button>
    <button class="btn-prev" onclick="changeAyah(-1)">◄ السابقة</button>
    <button class="btn-next" onclick="changeAyah(1)">التالية ►</button>
  </div>
  <div class="ctrl-row">
    <span class="ctrl-label">القارئ:</span>
    <select id="selReader"></select>
    <button class="btn-play" onclick="playAyah()">▶ استمع</button>
    <button class="btn-stop" onclick="stopAudio()">⏹</button>
    <button class="btn-dl" id="btnDl" onclick="downloadAyah()" disabled>⬇ تحميل</button>
  </div>
  <div class="ctrl-row">
    <div class="speed-bar">
      <span class="speed-label">السرعة:</span>
      <button class="speed-btn active" onclick="setSpeed(0.75,this)">0.75x</button>
      <button class="speed-btn" onclick="setSpeed(1.0,this)">1.0x</button>
      <button class="speed-btn" onclick="setSpeed(1.25,this)">1.25x</button>
      <button class="speed-btn" onclick="setSpeed(1.5,this)">1.5x</button>
      <button class="speed-btn" onclick="setSpeed(2.0,this)">2.0x</button>
    </div>
  </div>
  <div class="ctrl-row" style="justify-content:center;gap:10px;flex-wrap:wrap;">
    <button class="btn-toggle btn-en" id="btnEn" onclick="toggleLang('en')">🇬🇧 الترجمة</button>
    <button class="btn-toggle btn-tf" id="btnTf" onclick="toggleLang('tf')">📖 التفسير</button>
    <button class="btn-toggle btn-ur" id="btnUr" onclick="toggleLang('ur')">🇵🇰 الأوردو</button>
    <button class="btn-toggle btn-ku" id="btnKu" onclick="toggleLang('ku')">🏴 الكردية</button>
    <button class="btn-toggle btn-tr" id="btnTr" onclick="toggleLang('tr')">🇹🇷 التركية</button>
    <button class="btn-toggle btn-az" id="btnAz" onclick="toggleLang('az')">🇦🇿 الأذربيجانية</button>
  </div>
  <div class="ctrl-row" style="justify-content:center;">
    <button class="btn-toggle" onclick="showHelp()" style="background:#FCE4EC;color:#880E4F;border:1.5px solid #F48FB1;padding:8px 24px;">📚 تعريفات المد اللازم</button>
    <button class="btn-toggle" onclick="showAllCases()" style="background:rgba(0,200,83,0.15);color:var(--green);border:1.5px solid var(--green);padding:8px 24px;">📋 عرض كل الحالات</button>
  </div>
</div>

<!-- نافذة عرض كل الحالات -->
<div id="allCasesOverlay" onclick="closeAllCases(event)">
  <div id="allCasesModal">
    <div id="allCasesTitle">📋 كل حالات المد اللازم في هذه الآية</div>
    <div id="allCasesCount"></div>
    <table>
      <thead>
        <tr>
          <th>ت</th><th>الكلمة</th><th>نوع المد</th><th>طول المد</th><th>الموضع</th>
        </tr>
      </thead>
      <tbody id="allCasesTable"></tbody>
    </table>
    <button id="allCasesClose" onclick="closeAllCases()">✕ إغلاق</button>
  </div>
</div>

<div class="legend">
  <div class="legend-item leg-lkm" id="leg-لازم كلمي مثقل" onclick="filterByType('لازم كلمي مثقل',this)">● لازم كلمي مثقل</div>
  <div class="legend-item leg-lkf" id="leg-لازم كلمي مخفف" onclick="filterByType('لازم كلمي مخفف',this)">● لازم كلمي مخفف</div>
  <div class="legend-item leg-lhm" id="leg-لازم حرفي مثقل" onclick="filterByType('لازم حرفي مثقل',this)">● لازم حرفي مثقل</div>
  <div class="legend-item leg-lhf" id="leg-لازم حرفي مخفف" onclick="filterByType('لازم حرفي مخفف',this)">● لازم حرفي مخفف</div>
</div>

<!-- نافذة التعريفات -->
<div class="help-overlay" id="helpOverlay" onclick="hideHelp(event)">
  <div class="help-modal">
    <div class="help-title">📚 تعريفات المد اللازم</div>
    <div style="font-size:13px;color:var(--muted);text-align:center;margin-bottom:12px;padding:8px;background:#FCE4EC;border-radius:8px;">
      المد اللازم: إطالة الصوت بحرف المد 6 حركات لزوماً إذا جاء بعده حرف ساكن سكوناً أصلياً
    </div>
    <div class="help-tabs">
      <button class="help-tab help-tab-lkm" onclick="showTab('lkm')">كلمي مثقل</button>
      <button class="help-tab help-tab-lkf" onclick="showTab('lkf')">كلمي مخفف</button>
      <button class="help-tab help-tab-lhm" onclick="showTab('lhm')">حرفي مثقل</button>
      <button class="help-tab help-tab-lhf" onclick="showTab('lhf')">حرفي مخفف</button>
    </div>

    <div class="hcontent show" id="tab-lkm">
      <div class="help-def">
        <b style="color:var(--lkm)">المد اللازم الكلمي المثقل</b><br>
        أن يأتي بعد حرف المد في نفس الكلمة حرف ساكن مُدغم (مشدد).
      </div>
      <div class="help-letters" style="color:var(--lkm)">مقدار المد: 6 حركات وجوباً</div>
      <div class="help-example">
        <div class="help-ex-label">أمثلة:</div>
        ﴿الْحَاقَّةُ﴾ &nbsp;·&nbsp; ﴿وَلَا الضَّالِّينَ﴾
      </div>
    </div>

    <div class="hcontent" id="tab-lkf">
      <div class="help-def">
        <b style="color:var(--lkf)">المد اللازم الكلمي المخفف</b><br>
        أن يأتي بعد حرف المد حرف ساكن سكوناً أصلياً غير مُدغم في كلمة واحدة.
      </div>
      <div class="help-letters" style="color:var(--lkf)">مقدار المد: 6 حركات وجوباً</div>
      <div class="help-example">
        <div class="help-ex-label">مثال (ورد مرتين فقط في القرآن):</div>
        ﴿آلْآنَ﴾ — سورة يونس الآيتان 51 و91
      </div>
    </div>

    <div class="hcontent" id="tab-lhm">
      <div class="help-def">
        <b style="color:var(--lhm)">المد اللازم الحرفي المثقل</b><br>
        يقع في الحروف المقطعة في أوائل السور، والحرف الأوسط فيه ساكن يُدغم في الحرف الذي بعده.
      </div>
      <div class="help-letters" style="color:var(--lhm)">مقدار المد: 6 حركات وجوباً</div>
      <div class="help-example">
        <div class="help-ex-label">مثال:</div>
        ﴿الم﴾ — حرف اللام يُقرأ (لام ميم) والنون تُدغم في الميم بعدها
      </div>
    </div>

    <div class="hcontent" id="tab-lhf">
      <div class="help-def">
        <b style="color:var(--lhf)">المد اللازم الحرفي المخفف</b><br>
        يقع في الحروف المقطعة، ولا يُدغم الحرف الأخير فيما بعده (غير مشدد).
      </div>
      <div class="help-letters" style="color:var(--lhf)">مقدار المد: 6 حركات وجوباً</div>
      <div class="help-example">
        <div class="help-ex-label">أمثلة:</div>
        ﴿ن﴾ — سورة القلم &nbsp;·&nbsp; ﴿ق﴾ — سورة ق &nbsp;·&nbsp; ﴿ص﴾ — سورة ص
      </div>
    </div>

    <button class="help-close" onclick="hideHelp()">✕ إغلاق</button>
  </div>
</div>

<div class="info-bar">
  <span class="info-sura" id="infoSura">اختر آية للعرض</span>
  <div class="info-counts" id="infoCounts"></div>
</div>

<div class="ayah-wrap">
  <div class="ayah-box" id="ayahBox">...</div>
</div>

<div class="translation-box" id="transBox"></div>

<div class="table-wrap">
  <div class="table-header">قائمة حالات المد اللازم المستخرجة</div>
  <table>
    <thead>
      <tr>
        <th>ت</th>
        <th>الكلمة</th>
        <th>نوع المد</th>
        <th>طول المد</th>
        <th>الموضع</th>
      </tr>
    </thead>
    <tbody id="casesTable"></tbody>
  </table>
</div>

<audio id="audioPlayer"></audio>
<audio id="clipPlayer"></audio>

<!-- نافذة معنى الكلمة -->
<div id="wordOverlay" onclick="closeWordExplain(event)">
  <div id="wordModal">
    <div id="wordTitle"></div>
    <div id="wordContext"></div>
    <div class="word-suggestions" id="reciteRow">
      <button class="word-suggest-btn" style="border-color:var(--green);color:var(--green);" onclick="playClipReciter('alafasy')">🔊 العفاسي</button>
      <button class="word-suggest-btn" style="border-color:var(--green);color:var(--green);" onclick="playClipReciter('minshawy')">🔊 المنشاوي</button>
      <button class="word-suggest-btn" style="border-color:var(--green);color:var(--green);" onclick="playClipReciter('husary')">🔊 الحصري</button>
    </div>
    <div id="clipStatus" style="font-size:11px;color:var(--muted);text-align:center;margin:-4px 0 8px;"></div>
    <div class="word-suggestions">
      <button class="word-suggest-btn" onclick="askWordQuestion(1)">ما حكمها؟</button>
      <button class="word-suggest-btn" onclick="askWordQuestion(2)">لماذا هذا الحكم؟</button>
      <button class="word-suggest-btn" onclick="askWordQuestion(3)">كيف تُنطق؟</button>
      <button class="word-suggest-btn" onclick="askWordQuestion(4)">English</button>
      <button class="word-suggest-btn" onclick="askWordQuestion(5)">اردو</button>
      <button class="word-suggest-btn" onclick="askWordQuestion(6)">کوردی</button>
      <button class="word-suggest-btn" onclick="askWordQuestion(7)">Türkçe</button>
      <button class="word-suggest-btn" onclick="askWordQuestion(8)">Azərbaycan</button>
    </div>
    <div class="word-input-row">
      <input class="word-input" id="wordInput" placeholder="اكتب سؤالك هنا..."
             onkeydown="if(event.key==='Enter') askWordQuestion()">
      <button class="word-ask-btn" onclick="askWordQuestion()">اسأل</button>
    </div>
    <div id="wordResult">اضغط على أحد الأسئلة أو اكتب سؤالك...</div>
    <button id="wordClose" onclick="closeWordExplain()">✕ إغلاق</button>
  </div>
</div>

<script>
let currentData = null;
let currentSpeed = 0.75;
let readerMode   = 'aya';
let activeLang   = null;
let activeFilter = null;
const audio = document.getElementById('audioPlayer');

// ── تحديد نطاق حر بالسحب (drag-select) ──
let currentWords = [];
let currentCaseByIdx = {};
let dragStart = null, dragEnd = null, isDragging = false;

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
  if (!box || box._dragInit) return;
  box._dragInit = true;
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
    const lo = Math.min(dragStart, dragEnd), hi = Math.max(dragStart, dragEnd);
    // نقرة بسيطة على كلمة واحدة، أو سحب لعدة كلمات: كلاهما يفتح نافذة
    // الشرح والتلاوة مباشرة دون خطوة تأكيد وسيطة
    openSelectionExplain(lo, hi);
  });
  // دعم اللمس على الجوال
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
  box.addEventListener('touchend', () => {
    document.dispatchEvent(new Event('mouseup'));
  });
}

// يفتح نافذة الشرح + التلاوة لأي مجال كلمات محدَّد (كلمة واحدة أو أكثر)
function openSelectionExplain(lo, hi) {
  if (lo == null || hi == null || !currentData) { clearSelection(); return; }
  const phrase = currentWords.slice(lo, hi + 1).join(' ');
  const rulings = [];
  for (let i = lo; i <= hi; i++) if (currentCaseByIdx[i]) rulings.push(currentCaseByIdx[i]);
  const color = rulings[0]?.color || '#D4A843';
  currentWord = phrase; currentWordSura = currentData.suraname; currentWordVerse = currentData.verseid;
  currentWordRuling = rulings.map(r => r.itype).join('، ');
  clipCtx = {type:'range', verseid: currentData.verseid, lo, hi};
  document.getElementById('clipStatus').textContent = '';
  document.getElementById('wordTitle').textContent = phrase;
  document.getElementById('wordTitle').style.color = color;
  document.getElementById('wordContext').textContent =
    `سورة ${currentData.suraname} — الآية ${currentData.verseid}${currentWordRuling ? ' — ' + currentWordRuling : ''}`;
  document.getElementById('wordResult').textContent = 'اضغط على أحد الأسئلة أو اكتب سؤالك...';
  document.getElementById('wordInput').value = '';
  document.getElementById('wordOverlay').classList.add('show');
  clearSelection();
}

// ── نافذة عرض كل الحالات ──
function showAllCases() {
  if (!currentData || !currentData.cases || !currentData.cases.length) {
    alert('لا يوجد مد لازم موثّق في هذه الآية.');
    return;
  }
  document.getElementById('allCasesCount').textContent =
    `العدد الإجمالي: ${currentData.cases.length} حالة — اضغط أي صف لعرض شرحها`;
  document.getElementById('allCasesTable').innerHTML = currentData.cases.map((c,i) => `<tr onclick="openWordExplain('${(c.word||'').replace(/'/g,"\\'")}','${currentData.suraname}',${currentData.verseid},'${c.color}',${c.position-1});closeAllCases();" style="cursor:pointer">
    <td style="color:var(--muted)">${i+1}</td>
    <td class="word-cell" style="color:${c.color}">${c.word}</td>
    <td><span class="badge" style="color:${c.color};background:${c.color}18;border-color:${c.color}66">${c.itype}</span></td>
    <td style="color:var(--muted)">${c.length || '6'} حركات</td>
    <td style="color:var(--muted);font-size:11px">كلمة ${c.position}</td>
  </tr>`).join('');
  document.getElementById('allCasesOverlay').classList.add('show');
}
function closeAllCases(e) {
  if (!e || e.target === document.getElementById('allCasesOverlay'))
    document.getElementById('allCasesOverlay').classList.remove('show');
}

const COLORS = {
  'لازم كلمي مثقل': '#FF6F00',
  'لازم كلمي مخفف': '#FF9800',
  'لازم حرفي مثقل': '#00BCD4',
};

// ── التنقل بين الآيات ──
async function changeAyah(delta) {
  if (!currentData) return;
  const type = activeFilter || 'الكل';
  showAyahNavLoading(true);
  try {
    const r = await fetch(`/api/lazm/nextayah?suraid=${currentData.suraid}&verseid=${currentData.verseid}&delta=${delta}&type=${encodeURIComponent(type)}`);
    const d = await r.json();
    showAyahNavLoading(false);
    if (d.found) {
      const p = {suraid: d.suraid, verseid: d.verseid};
      if (type !== 'الكل') p.type = type;
      const r2 = await fetch('/api/lazm/ayah?' + new URLSearchParams(p));
      const d2 = await r2.json();
      if (d2.error) return;
      currentData = d2;
      renderAyah(d2);
      syncSelects(d2);
      document.getElementById('btnDl').disabled = false;
      // تنبيه إذا الحكم المختار غير موجود
      if (activeFilter) checkFilterOnAyah(d2);
    } else {
      showNoRulingToast(delta > 0
        ? `لا توجد آية بعدها تحتوي حكم "${type}"`
        : `لا توجد آية قبلها تحتوي حكم "${type}"`);
    }
  } catch(e) { showAyahNavLoading(false); }
}

function showAyahNavLoading(on) {
  document.querySelectorAll('.btn-prev,.btn-next').forEach(b => {
    b.disabled = on;
    b.style.opacity = on ? '0.5' : '1';
  });
}

function checkFilterOnAyah(d) {
  if (!activeFilter) return;
  const hasCases = d.cases.some(c => c.itype === activeFilter);
  if (!hasCases) showNoRulingToast(`لا يوجد حكم "${activeFilter}" في هذه الآية`);
}

function showNoRulingToast(msg) {
  const old = document.getElementById('noRulingToast');
  if (old) old.remove();
  const div = document.createElement('div');
  div.id = 'noRulingToast';
  div.textContent = `⚠️ ${msg}`;
  div.style.cssText = `
    position:fixed;top:80px;left:50%;transform:translateX(-50%) translateY(-20px);
    background:#FF6F00;color:#fff;padding:12px 24px;border-radius:30px;
    font-size:15px;font-weight:bold;z-index:3000;opacity:0;
    box-shadow:0 4px 16px rgba(0,0,0,0.3);transition:all 0.4s ease;
    white-space:nowrap;font-family:"Traditional Arabic",Arial;
  `;
  document.body.appendChild(div);
  setTimeout(() => { div.style.opacity='1'; div.style.transform='translateX(-50%) translateY(0)'; }, 50);
  setTimeout(() => {
    div.style.opacity='0'; div.style.transform='translateX(-50%) translateY(-20px)';
    setTimeout(() => div.remove(), 400);
  }, 3000);
}

// ── Filter by type ──
function filterByType(type, el) {
  if (activeFilter === type) {
    activeFilter = null;
    document.querySelectorAll('.legend-item').forEach(e => e.classList.remove('active','dimmed'));
  } else {
    activeFilter = type;
    document.querySelectorAll('.legend-item').forEach(e => {
      const isActive = e.id === `leg-${type}`;
      e.classList.toggle('active', isActive);
      e.classList.toggle('dimmed', !isActive);
    });
  }
  if (currentData) {
    renderAyah(currentData);
    if (activeFilter) checkFilterOnAyah(currentData);
  }
  loadAllAyat();
}

// تحميل الآيات حسب الفلتر
async function loadAllAyat() {
  const type = activeFilter || 'الكل';
  await loadSuras(type);
}

// ── Readers ──
async function loadReaders() {
  const r = await fetch('/api/readers');
  const d = await r.json();
  const sel = document.getElementById('selReader');
  sel.innerHTML = d.map(r => `<option value="${r.id}" data-mode="${r.mode}">${r.label}</option>`).join('');
  sel.addEventListener('change', () => {
    readerMode = sel.options[sel.selectedIndex].dataset.mode || 'aya';
  });
  readerMode = sel.options[0]?.dataset.mode || 'aya';
}

// ── Suras ──
async function loadSuras(type) {
  type = type || activeFilter || 'الكل';
  const r = await fetch(`/api/lazm/suras?type=${encodeURIComponent(type)}`);
  const d = await r.json();
  const sel = document.getElementById('selSura');
  sel.innerHTML = d.map(s => `<option value="${s.suraid}">${s.suraid}. ${s.suraname}</option>`).join('');
  await loadVerses();
}

// ── Verses ──
async function loadVerses() {
  const suraid = document.getElementById('selSura').value;
  if (!suraid) return;
  const type   = activeFilter || 'الكل';
  const r = await fetch(`/api/lazm/verses?suraid=${suraid}&type=${encodeURIComponent(type)}`);
  const d = await r.json();
  const sel = document.getElementById('selVerse');
  sel.innerHTML = d.map(v => `<option value="${v}">آية ${v}</option>`).join('');
}

// ── Random ──
async function loadRandom() {
  const type = activeFilter || 'الكل';
  const p = {random:1};
  if (type !== 'الكل') p.type = type;
  const r = await fetch('/api/lazm/ayah?' + new URLSearchParams(p));
  const d = await r.json();
  if (d.error) return;
  currentData = d;
  renderAyah(d);
  syncSelects(d);
  document.getElementById('btnDl').disabled = false;
}

// ── Load Ayah ──
async function loadAyah() {
  const suraid  = document.getElementById('selSura').value;
  const verseid = document.getElementById('selVerse').value;
  const type    = activeFilter || 'الكل';
  const p = {suraid, verseid};
  if (type !== 'الكل') p.type = type;
  const r = await fetch('/api/lazm/ayah?' + new URLSearchParams(p));
  const d = await r.json();
  if (d.error) return;
  currentData = d;
  renderAyah(d);
  document.getElementById('btnDl').disabled = false;
}

// ── Sync selects ──
async function syncSelects(d) {
  const sEl = document.getElementById('selSura');
  for (let i=0; i<sEl.options.length; i++) {
    if (parseInt(sEl.options[i].value) === d.suraid) { sEl.selectedIndex=i; break; }
  }
  await loadVerses();
  const vEl = document.getElementById('selVerse');
  for (let i=0; i<vEl.options.length; i++) {
    if (parseInt(vEl.options[i].value) === d.verseid) { vEl.selectedIndex=i; break; }
  }
}

// ── Render ──
function renderAyah(d) {
  document.getElementById('infoSura').textContent =
    `سورة ${d.suraname} — الآية ${d.verseid} — صفحة ${d.pagenum}`;

  // العدادات
  const counts = {'لازم كلمي مثقل':0,'لازم كلمي مخفف':0,'لازم حرفي مثقل':0,'لازم حرفي مخفف':0};
  d.cases.forEach(c => { if (counts[c.itype] !== undefined) counts[c.itype]++; });
  const styleMap = {
    'لازم كلمي مثقل': 'background:#FFF3E0;color:#FF6F00;border:1px solid #FF6F00',
    'لازم كلمي مخفف': 'background:#FFF8E1;color:#FF9800;border:1px solid #FF9800',
    'لازم حرفي مثقل': 'background:#E0F7FA;color:#00BCD4;border:1px solid #00BCD4',
    'لازم حرفي مخفف': 'background:#E1F5FE;color:#4FC3F7;border:1px solid #4FC3F7',
  };
  document.getElementById('infoCounts').innerHTML = Object.entries(counts)
    .filter(([,n])=>n>0)
    .map(([k,n])=>`<span class="cnt-badge" style="${styleMap[k]}">${k.replace('لازم ','')}: ${n}</span>`)
    .join('');

  // تلوين الكلمات
  const words = d.aya.split(/\\s+/).filter(Boolean);
  const colored = {};
  const caseByIdx = {};
  d.cases.forEach(c => {
    const w = (c.word || '').trim();
    const idx = c.position - 1;
    if (idx >= 0 && idx < words.length && words[idx].trim() === w) {
      colored[idx] = c.color; caseByIdx[idx] = c;
    } else {
      for (let i=0; i<words.length; i++) {
        if (words[i].trim() === w && !colored[i]) { colored[i] = c.color; caseByIdx[i] = c; break; }
      }
    }
  });
  currentCaseByIdx = caseByIdx;
  currentWords = words;

  let html = words.map((w,i) =>
    colored[i]
      ? `<span class="word-tok" data-idx="${i}" style="color:${colored[i]};font-weight:bold;text-decoration:underline;text-decoration-color:${colored[i]}55;text-underline-offset:5px;">${w}</span>`
      : `<span class="word-tok" data-idx="${i}" style="color:#F8F4EE">${w}</span>`
  ).join(' ');
  html += ` <span style="color:var(--gold);font-size:0.8em">﴿${d.verseid}﴾</span>`;
  document.getElementById('ayahBox').innerHTML = html;
  initDragSelect();
  clearSelection();

  // الجدول
  document.getElementById('casesTable').innerHTML = d.cases.map((c,i) => `<tr>
    <td style="color:var(--muted)">${i+1}</td>
    <td class="word-cell" style="color:${c.color}">${c.word}</td>
    <td><span class="badge" style="color:${c.color};background:${c.color}18;border-color:${c.color}66">${c.itype}</span></td>
    <td style="color:var(--muted)">${c.length || '6'} حركات</td>
    <td style="color:var(--muted);font-size:11px">كلمة ${c.position}</td>
  </tr>`).join('');

  // الترجمة
  if (activeLang) showTranslation(d);
}

// ── Translations ──
function toggleLang(lang) {
  const btn = document.getElementById('btn' + lang.charAt(0).toUpperCase() + lang.slice(1));
  const ids = ['btnEn','btnTf','btnUr','btnKu','btnTr','btnAz'];
  const box = document.getElementById('transBox');
  if (activeLang === lang) {
    activeLang = null;
    box.classList.remove('show');
    document.querySelectorAll('.btn-toggle').forEach(b => b.classList.remove('active'));
  } else {
    activeLang = lang;
    ids.forEach(id => document.getElementById(id)?.classList.remove('active'));
    btn?.classList.add('active');
    if (currentData) showTranslation(currentData);
  }
}

function showTranslation(d) {
  const box = document.getElementById('transBox');
  if (!activeLang || !d) { box.classList.remove('show'); return; }
  const texts = {
    en: d.en   ? `🇬🇧 ${d.en}`   : '🇬🇧 غير متاح',
    tf: d.tf   ? `📖 ${d.tf}`   : '📖 غير متاح',
    ur: d.ur   ? `🇵🇰 ${d.ur}`   : '🇵🇰 غير متاح',
    ku: d.ku   ? `🏴 ${d.ku}`   : '🏴 غير متاح',
    tr: d.tr   ? `🇹🇷 ${d.tr}`   : '🇹🇷 غير متاح',
    az: d.az   ? `🇦🇿 ${d.az}`   : '🇦🇿 غير متاح',
  };
  box.textContent = texts[activeLang] || '';
  box.classList.add('show');
}

// ── Audio ──
function playAyah() {
  if (!currentData) return;
  const reader  = document.getElementById('selReader').value;
  const s = String(currentData.suraid).padStart(3,'0');
  const v = String(currentData.verseid).padStart(3,'0');
  audio.src = readerMode === 'sura' ? `/audio/${reader}/${s}.mp3` : `/audio/${reader}/${s}${v}.mp3`;
  audio.playbackRate = currentSpeed;
  audio.play().then(()=>{ audio.playbackRate = currentSpeed; }).catch(()=>{});
}

function stopAudio() { audio.pause(); audio.currentTime=0; }

function downloadAyah() {
  if (!currentData) return;
  const reader = document.getElementById('selReader').value;
  const s = String(currentData.suraid).padStart(3,'0');
  const v = String(currentData.verseid).padStart(3,'0');
  const a = document.createElement('a');
  a.href     = readerMode === 'sura' ? `/audio/${reader}/${s}.mp3` : `/audio/${reader}/${s}${v}.mp3`;
  a.download = `سورة_${currentData.suraname}_آية_${currentData.verseid}.mp3`;
  a.click();
}

function setSpeed(s, btn) {
  currentSpeed = s;
  audio.playbackRate = s;
  document.querySelectorAll('.speed-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}

// ── Word Explain ──
let currentWord = '', currentWordSura = '', currentWordVerse = '', currentWordRuling = '';
let clipCtx = null; // {type:'word'|'range', suraid, verseid, word, lo, hi}
const clipPlayer = document.getElementById('clipPlayer');

function playClipReciter(reciter) {
  if (!clipCtx || !currentData) return;
  const status = document.getElementById('clipStatus');
  const p = new URLSearchParams({suraid: currentData.suraid, verseid: clipCtx.verseid,
                                  reciter, type: clipCtx.type});
  if (clipCtx.type === 'range') { p.set('lo', clipCtx.lo); p.set('hi', clipCtx.hi); }
  else { p.set('word', clipCtx.word); }
  status.textContent = '⏳ جارٍ التحضير...';
  clipPlayer.src = '/api/lazm/clip?' + p.toString();
  clipPlayer.play().then(() => { status.textContent = ''; })
    .catch(async () => {
      try {
        const r = await fetch('/api/lazm/clip?' + p.toString());
        const d = await r.json();
        status.textContent = '⚠ ' + (d.error || 'تعذّر تشغيل المقطع.');
      } catch(e) { status.textContent = '⚠ تعذّر تشغيل المقطع.'; }
    });
}

const WORD_QUESTIONS = {
  1: 'ما حكم هذه الكلمة من أحكام المد اللازم؟',
  2: 'لماذا هذا الحكم؟ اشرح السبب.',
  3: 'كيف أنطق هذه الكلمة بشكل صحيح؟',
  4: 'What is the ruling of this word and how is it pronounced?',
  5: 'اس لفظ کا تجوید کا حکم کیا ہے؟',
  6: 'حوکمی تەجویدی ئەم وشەیە چییە؟',
  7: 'Bu kelimenin tecvid hükmü nedir ve nasıl doğru telaffuz edilir?',
  8: 'Bu sözün Quran tilavəti hökmü nədir və necə düzgün tələffüz edilir?',
};

function openWordExplain(word, sura, verse, color, idx) {
  currentWord = word; currentWordSura = sura; currentWordVerse = verse;
  // نفضّل الاعتماد على فهرس الكلمة بدل البحث النصي، لأن البحث النصي قد
  // يلتقط أول ظهور لكلمة متكررة في الآية بدل الكلمة المقصودة فعلياً.
  clipCtx = (typeof idx === 'number' && !Number.isNaN(idx))
    ? {type:'range', verseid: verse, lo: idx, hi: idx}
    : {type:'word', verseid: verse, word: word};
  document.getElementById('clipStatus').textContent = '';
  // نجيب الحكم من الجدول
  let ruling = '';
  document.querySelectorAll('#casesTable tr').forEach(row => {
    const wc = row.querySelector('.word-cell');
    if (wc && wc.textContent.trim() === word.trim()) {
      const badge = row.querySelector('.badge');
      if (badge) ruling = badge.textContent.trim();
    }
  });
  currentWordRuling = ruling;
  document.getElementById('wordTitle').textContent = word;
  document.getElementById('wordTitle').style.color = color;
  document.getElementById('wordContext').textContent = `سورة ${sura} — الآية ${verse}${ruling ? ' — ' + ruling : ''}`;
  document.getElementById('wordResult').textContent = 'اضغط على أحد الأسئلة أو اكتب سؤالك...';
  document.getElementById('wordInput').value = '';
  document.getElementById('wordOverlay').classList.add('show');
}

async function askWordQuestion(num) {
  const q = WORD_QUESTIONS[num] || document.getElementById('wordInput').value.trim();
  if (!q) return;
  document.getElementById('wordInput').value = typeof num === 'number' ? WORD_QUESTIONS[num] : q;
  document.getElementById('wordResult').innerHTML = '<i style="color:var(--muted)">⏳ جارٍ الشرح...</i>';
  try {
    const r = await fetch('/api/lazm/explain', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({word:currentWord, sura:currentWordSura, verse:currentWordVerse, question:q, ruling:currentWordRuling})
    });
    const d = await r.json();
    document.getElementById('wordResult').textContent = d.answer || currentWord;
  } catch(e) {
    document.getElementById('wordResult').textContent = `الكلمة: ${currentWord}`;
  }
}

function closeWordExplain(e) {
  if (!e || e.target === document.getElementById('wordOverlay')) {
    document.getElementById('wordOverlay').classList.remove('show');
    clipPlayer.pause();
  }
}

// ── Help ──
function showHelp() {
  document.getElementById('helpOverlay').classList.add('show');
  showTab('lkm');
}
function hideHelp(e) {
  if (!e || e.target === document.getElementById('helpOverlay'))
    document.getElementById('helpOverlay').classList.remove('show');
}
function showTab(tab) {
  document.querySelectorAll('.hcontent').forEach(el => el.classList.remove('show'));
  document.getElementById('tab-' + tab)?.classList.add('show');
  document.querySelectorAll('.help-tab').forEach(b => b.classList.remove('active'));
  document.querySelector('.help-tab-' + tab)?.classList.add('active');
}

async function init() {
  await loadReaders();
  await loadSuras('الكل');
  await loadRandom();
}
init();
</script>
</body></html>'''


@bp.route('/lazm')
def index(): return HTML


@bp.route('/api/lazm/nextayah')
def api_nextayah():
    suraid  = int(request.args.get('suraid', 1))
    verseid = int(request.args.get('verseid', 1))
    delta   = int(request.args.get('delta', 1))
    itype   = request.args.get('type','')
    conn    = get_db(); cur = conn.cursor()
    step    = 1 if delta > 0 else -1
    found   = None
    try:
        # نجيب جميع الآيات التي تحتوي الحكم مرتبة
        if itype and itype != 'الكل':
            cur.execute('''SELECT DISTINCT SURAID, VERSEID FROM MADD_RULES
                           WHERE MADD_TYPE=?
                           ORDER BY CAST(SURAID AS INTEGER), CAST(VERSEID AS INTEGER)''', (itype,))
        else:
            cur.execute('''SELECT DISTINCT SURAID, VERSEID FROM MADD_RULES
                           ORDER BY CAST(SURAID AS INTEGER), CAST(VERSEID AS INTEGER)''')
        all_ayat = cur.fetchall()
        # نجد الموضع الحالي
        cur_idx = None
        for i, (s, v) in enumerate(all_ayat):
            if int(s) == suraid and int(v) == verseid:
                cur_idx = i; break
        if cur_idx is None:
            # الآية الحالية ليست في القائمة — نجد الأقرب
            for i, (s, v) in enumerate(all_ayat):
                if (int(s) > suraid) or (int(s) == suraid and int(v) > verseid):
                    cur_idx = i - 1 if delta < 0 else i
                    break
            if cur_idx is None: cur_idx = len(all_ayat) - 1
        nxt_idx = cur_idx + step
        if 0 <= nxt_idx < len(all_ayat):
            found = {'suraid': all_ayat[nxt_idx][0], 'verseid': all_ayat[nxt_idx][1]}
    except: pass
    conn.close()
    if found:
        return jsonify({'found': True, 'suraid': found['suraid'], 'verseid': found['verseid']})
    return jsonify({'found': False})


@bp.route('/api/lazm/suras')
def api_suras():
    itype = request.args.get('type','الكل')
    conn = get_db(); cur = conn.cursor()
    try:
        if itype and itype != 'الكل':
            cur.execute('''SELECT DISTINCT r.SURAID, m.SURANAME
                           FROM MADD_RULES r
                           JOIN mushafnew m ON r.SURAID=m.SURAID AND r.VERSEID=m.VERSEID
                           WHERE r.MADD_TYPE=?
                           ORDER BY CAST(r.SURAID AS INTEGER)''', (itype,))
        else:
            cur.execute('''SELECT DISTINCT r.SURAID, m.SURANAME
                           FROM MADD_RULES r
                           JOIN mushafnew m ON r.SURAID=m.SURAID AND r.VERSEID=m.VERSEID
                           ORDER BY CAST(r.SURAID AS INTEGER)''')
        rows = [{'suraid':r[0],'suraname':r[1]} for r in cur.fetchall()]
    except: rows = []
    conn.close(); return jsonify(rows)


@bp.route('/api/lazm/verses')
def api_verses():
    suraid = request.args.get('suraid')
    itype  = request.args.get('type','الكل')
    if not suraid: return jsonify([])
    conn = get_db(); cur = conn.cursor()
    try:
        if itype and itype != 'الكل':
            cur.execute('''SELECT DISTINCT r.VERSEID FROM MADD_RULES r
                           WHERE r.SURAID=? AND r.MADD_TYPE=?
                           ORDER BY CAST(r.VERSEID AS INTEGER)''', (suraid, itype))
        else:
            cur.execute('''SELECT DISTINCT r.VERSEID FROM MADD_RULES r
                           WHERE r.SURAID=?
                           ORDER BY CAST(r.VERSEID AS INTEGER)''', (suraid,))
        rows = cur.fetchall()
    except: rows = []
    conn.close(); return jsonify([r[0] for r in rows])


@bp.route('/api/lazm/ayah')
def api_ayah():
    suraid  = request.args.get('suraid')
    verseid = request.args.get('verseid')
    rand    = request.args.get('random','0')
    itype   = request.args.get('type','الكل')
    conn = get_db(); cur = conn.cursor()

    if rand == '1':
        try:
            if itype and itype != 'الكل':
                cur.execute('SELECT DISTINCT SURAID,VERSEID FROM MADD_RULES WHERE MADD_TYPE=? ORDER BY RANDOM() LIMIT 1', (itype,))
            else:
                cur.execute('SELECT DISTINCT SURAID,VERSEID FROM MADD_RULES ORDER BY RANDOM() LIMIT 1')
            r = cur.fetchone()
            if r: suraid, verseid = r[0], r[1]
        except: pass

    if not suraid or not verseid:
        conn.close(); return jsonify({'error':'missing'})

    # جلب الأحكام
    try:
        if itype and itype != 'الكل':
            cur.execute('''SELECT r.WORD, r.MADD_TYPE, r.MADD_LENGTH, r.POSITION
                           FROM MADD_RULES r
                           WHERE r.SURAID=? AND r.VERSEID=? AND r.MADD_TYPE=?
                           ORDER BY r.POSITION''', (suraid, verseid, itype))
        else:
            cur.execute('''SELECT r.WORD, r.MADD_TYPE, r.MADD_LENGTH, r.POSITION
                           FROM MADD_RULES r
                           WHERE r.SURAID=? AND r.VERSEID=?
                           ORDER BY r.POSITION''', (suraid, verseid))
        cases_raw = cur.fetchall()
    except: cases_raw = []

    # جلب نص الآية
    try:
        cur.execute('''SELECT m.SURANAME, m.ayahtext, m.PAGENUM
                       FROM mushafnew m WHERE m.SURAID=? AND m.VERSEID=? LIMIT 1''',
                    (suraid, verseid))
        meta = cur.fetchone() or ('','','')
    except: meta = ('','','')

    # الترجمات
    en = tf = ur = ku = tr = az = ''
    try:
        cur.execute('SELECT text_en FROM quran_en WHERE suraid=? AND verseid=? LIMIT 1',(suraid,verseid))
        r=cur.fetchone(); en=r[0] if r else ''
    except: pass
    try:
        cur.execute('SELECT tafseer FROM tafseer_jalalayn WHERE suraid=? AND verseid=? LIMIT 1',(suraid,verseid))
        r=cur.fetchone(); tf=r[0] if r else ''
    except: pass
    try:
        cur.execute('SELECT text_ur FROM quran_ur WHERE suraid=? AND verseid=? LIMIT 1',(suraid,verseid))
        r=cur.fetchone(); ur=r[0] if r else ''
    except: pass
    try:
        cur.execute('SELECT text_ku FROM quran_ku WHERE suraid=? AND verseid=? LIMIT 1',(suraid,verseid))
        r=cur.fetchone(); ku=r[0] if r else ''
    except: pass
    try:
        cur.execute('SELECT text_tr FROM quran_tr WHERE suraid=? AND verseid=? LIMIT 1',(suraid,verseid))
        r=cur.fetchone(); tr=r[0] if r else ''
    except: pass
    try:
        cur.execute('SELECT text_az FROM quran_az WHERE suraid=? AND verseid=? LIMIT 1',(suraid,verseid))
        r=cur.fetchone(); az=r[0] if r else ''
    except: pass

    conn.close()

    cases = [{
        'word'    : c[0],
        'itype'   : c[1],
        'length'  : c[2],
        'position': c[3],
        'color'   : get_color(c[1])
    } for c in cases_raw]

    return jsonify({
        'suraid'  : int(suraid),
        'verseid' : int(verseid),
        'suraname': meta[0],
        'aya'     : _clean_aya(meta[1]),
        'pagenum' : meta[2],
        'cases'   : cases,
        'en': en, 'tf': tf, 'ur': ur, 'ku': ku, 'tr': tr, 'az': az,
    })


@bp.route('/api/lazm/explain', methods=['POST'])
def api_explain():
    import json as jl, http.client, sys as _sys
    data     = request.get_json(force=True)
    word     = data.get('word','')
    sura     = data.get('sura','')
    verse    = data.get('verse','')
    question = data.get('question', f'ما معنى كلمة {word} في القرآن الكريم؟')
    ruling   = data.get('ruling','')

    ruling_info = f'\nالحكم المؤكد من قاعدة البيانات: {ruling}' if ruling else ''
    API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

    try:
        system = ("You are an expert in Quran Tajweed specializing in Madd rules. "
                  "Answer briefly in max 3-4 lines. "
                  "CRITICAL: The ruling provided from the database is CORRECT - never contradict it. "
                  "If the database says it is Madd Lazim, then it IS Madd Lazim - do not deny this. "
                  "If question is in Arabic answer in Arabic only. "
                  "If question is in English answer in English only. "
                  "If question is in Urdu answer in Urdu only. "
                  "If question is in Kurdish answer in Kurdish only. "
                  "If question is in Turkish answer in Turkish only. "
                  "If question is in Azerbaijani answer in Azerbaijani only. "
                  "Never mix languages. No markdown formatting. Plain text only. "
                  "FACT: Madd Lazim is always 6 harakaat.")
        prompt = f"Quran word: {word}\nSura: {sura}, Verse: {verse}{ruling_info}\nQuestion: {question}"
        body = jl.dumps({
            'model':'claude-sonnet-4-6','max_tokens':200,
            'system':system,
            'messages':[{'role':'user','content':prompt}]
        }, ensure_ascii=False).encode('utf-8')
        conn = http.client.HTTPSConnection('api.anthropic.com', timeout=15)
        conn.request('POST','/v1/messages',body=body,headers={
            'Content-Type':'application/json; charset=utf-8',
            'x-api-key':API_KEY,'anthropic-version':'2023-06-01'
        })
        resp = jl.loads(conn.getresponse().read().decode('utf-8'))
        conn.close()
        return jsonify({'answer': resp['content'][0]['text']})
    except Exception as e:
        err = str(e).encode('ascii','replace').decode('ascii')
        return jsonify({'answer': f'Error: {err}'})



@bp.route('/api/lazm/clip')
def api_clip():
    """يُرجع مقطعاً صوتياً دقيقاً (كلمة واحدة أو مجال كلمات متتالية)
    مقتطعاً من تلاوة أحد الشيوخ الثلاثة، بالاعتماد على word_audio_helper."""
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
        clip_path, info = prepare_range_clip(BASE_DIR, readers_dict, suraid, verseid,
                                              aya_text, lo, hi, reciter)
    else:
        word = request.args.get('word', '')
        clip_path, info = prepare_word_clip(BASE_DIR, readers_dict, suraid, verseid,
                                             aya_text, word, reciter)
    if not clip_path:
        return jsonify({'error': info or 'تعذّر تجهيز المقطع.'}), 404
    return send_file(clip_path, mimetype='audio/mpeg')


