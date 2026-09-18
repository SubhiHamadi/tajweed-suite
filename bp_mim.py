"""
mim_web_app.py — أحكام الميم الساكنة في القرآن الكريم (نسخة الويب، مستوى الصفحة)
نسخة Flask من mim_page_app.py، بنفس هوية ikhfa_web_app.py وizhar_web_app.py
البصرية. تنقل بالصفحة (نفس نمط mim_page_app.py الأصلي).
يعمل على بورت 5045.
"""
import os, re, sys, sqlite3, json, traceback, random
from flask import Flask, Blueprint, jsonify, request, send_from_directory, send_file

bp = Blueprint('mim', __name__)
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

# ══════════════════════════════════════════════════════════════
#  ألوان/أيقونات/تعريفات أنواع الميم الساكنة — منقولة حرفياً من
#  mim_page_app.py
# ══════════════════════════════════════════════════════════════
C_GOLD2 = '#F0C755'
MIM_COLOR = {
    'إظهار شفوي': '#00C853',
    'إخفاء شفوي': '#00E5FF',
    'إدغام شفوي': '#FFD700',
}
def get_color(rule_type):
    return MIM_COLOR.get(rule_type, C_GOLD2)

MIM_ICON = {
    'إظهار شفوي': '🟢',
    'إخفاء شفوي': '🔵',
    'إدغام شفوي': '🟡',
}
def get_icon(rule_type):
    return MIM_ICON.get(rule_type, '🔹')

MIM_DEFINITIONS = {
    'إظهار شفوي': 'إظهار الميم الساكنة بوضوح من غير غنة، إذا جاء بعدها أي حرف '
                   'من حروف الهجاء غير الباء والميم، مثل: أَنۡعَمۡتَ عَلَيۡهِمۡ غَيۡرِ',
    'إخفاء شفوي': 'إخفاء الميم الساكنة بغنة مع بقاء الغنة، إذا جاء بعدها حرف '
                   'الباء، مع إغلاق الشفتين قليلاً بلا التصاق كامل، مثل: لَهُم بِئۡسَ',
    'إدغام شفوي': 'إدغام الميم الساكنة في الميم المتحركة لتصبح ميماً واحدة '
                   'مشددة بغنة، إذا جاء بعدها حرف الميم (يُسمى أيضاً مثلين صغير)، '
                   'مثل: هُم مِّن',
}

SABAB_ICON = {
    'ميم ساكنة في كلمة'    : '🔵',
    'ميم ساكنة بين كلمتين' : '🟢',
    'ميم ساكنة بين آيتين'  : '🟤',
}

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

# استيراد آمن: إن لم تتوفر word_audio_helper.py بجانب هذا الملف، يستمر
# التطبيق بالعمل عادياً، وتُعطَّل ميزة نطق الكلمة/العبارة الدقيق فقط
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
#  منطق الصفحة — منقول من PageLoadThread / FindPageThread في
#  mim_page_app.py دون أي تغيير في الاستعلامات
# ══════════════════════════════════════════════════════════════
def _load_page(page_num, type_filter=None, sabab_filter=None):
    conn = get_db(); cur = conn.cursor()
    result = []
    try:
        params, where = [page_num], ['m.PAGENUM=?']
        if type_filter and type_filter != 'الكل':
            where.append('r.rule_type=?'); params.append(type_filter)
        if sabab_filter and sabab_filter != 'الكل':
            where.append('r.sabab=?'); params.append(sabab_filter)
        wclause = 'WHERE ' + ' AND '.join(where)

        cur.execute(f"""
            SELECT DISTINCT r.suraid, r.verseid, m.SURANAME, m.ayahtext
            FROM mim_rules r
            JOIN mushafnew m ON m.SURAID=r.suraid AND m.VERSEID=r.verseid
            {wclause}
            ORDER BY r.suraid, r.verseid
        """, params)
        ayas = cur.fetchall()

        for suraid, verseid, suraname, aya_text in ayas:
            p2, w2 = [suraid, verseid], ['suraid=?', 'verseid=?']
            if type_filter and type_filter != 'الكل':
                w2.append('rule_type=?'); p2.append(type_filter)
            if sabab_filter and sabab_filter != 'الكل':
                w2.append('sabab=?'); p2.append(sabab_filter)
            cur.execute(f"""
                SELECT id, klma1, klma2, klma1_hr, klma2_hr, mim_char,
                       next_char, rule_type, sabab, word_seq, word_seq2
                FROM mim_rules WHERE {' AND '.join(w2)}
                ORDER BY word_seq, word_seq2
            """, p2)
            rows = cur.fetchall()
            cases = []
            for cid, k1, k2, k1h, k2h, mc, nc, rt, sabab, ws, ws2 in rows:
                cases.append({
                    'id': cid, 'klma1': (k1 or '').strip(), 'klma2': (k2 or '').strip(),
                    'mim_char': mc, 'next_char': nc, 'rule_type': rt, 'sabab': sabab,
                    'color': get_color(rt), 'icon': get_icon(rt),
                    'sabab_icon': SABAB_ICON.get(sabab, '🔹'),
                })
            result.append({
                'suraid': suraid, 'verseid': verseid, 'suraname': suraname,
                'aya_text': _clean_aya(aya_text or ''), 'cases': cases,
            })
    except Exception:
        result = []
    finally:
        conn.close()
    return result

def _find_nearest_page(current_page, direction, type_filter=None, sabab_filter=None):
    conn = get_db(); cur = conn.cursor()
    try:
        params, where = [], []
        if type_filter and type_filter != 'الكل':
            where.append('r.rule_type=?'); params.append(type_filter)
        if sabab_filter and sabab_filter != 'الكل':
            where.append('r.sabab=?'); params.append(sabab_filter)
        base_where = ('AND ' + ' AND '.join(where)) if where else ''
        if direction == 1:
            cur.execute(f"""
                SELECT DISTINCT m.PAGENUM FROM mim_rules r
                JOIN mushafnew m ON m.SURAID=r.suraid AND m.VERSEID=r.verseid
                WHERE m.PAGENUM > ? {base_where}
                ORDER BY m.PAGENUM ASC LIMIT 1
            """, [current_page] + params)
        else:
            cur.execute(f"""
                SELECT DISTINCT m.PAGENUM FROM mim_rules r
                JOIN mushafnew m ON m.SURAID=r.suraid AND m.VERSEID=r.verseid
                WHERE m.PAGENUM < ? {base_where}
                ORDER BY m.PAGENUM DESC LIMIT 1
            """, [current_page] + params)
        r = cur.fetchone()
        return r[0] if r else -1
    except Exception:
        return -1
    finally:
        conn.close()

def _random_page(type_filter=None, sabab_filter=None):
    conn = get_db(); cur = conn.cursor()
    try:
        params, where = [], []
        if type_filter and type_filter != 'الكل':
            where.append('r.rule_type=?'); params.append(type_filter)
        if sabab_filter and sabab_filter != 'الكل':
            where.append('r.sabab=?'); params.append(sabab_filter)
        base_where = ('AND ' + ' AND '.join(where)) if where else ''
        # نجلب كل أرقام الصفحات المطابقة بلا فرز عشوائي في SQL (مكلف جدًا
        # على JOIN كبير)، ثم نختار واحدة عشوائيًا داخل بايثون — أخف بكثير.
        cur.execute(f"""
            SELECT DISTINCT m.PAGENUM FROM mim_rules r
            JOIN mushafnew m ON m.SURAID=r.suraid AND m.VERSEID=r.verseid
            WHERE 1=1 {base_where}
        """, params)
        pages = [row[0] for row in cur.fetchall() if row[0] is not None]
        if not pages:
            return -99, None
        return random.choice(pages), None
    except Exception as e:
        err = traceback.format_exc()
        print('[_random_page] EXCEPTION:', err, flush=True)
        return -97, str(e) + ' || ' + err.replace('\n', ' | ')
    finally:
        conn.close()

# ══════════════════════════════════════════════════════════════
#  الواجهة (HTML/CSS/JS)
# ══════════════════════════════════════════════════════════════
HTML = r'''<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>أحكام الميم الساكنة في القرآن الكريم</title>
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
select, input[type=number] {
  background:#0A2040; border:1.5px solid var(--border); border-radius:8px;
  padding:7px 10px; color:var(--text); font-family:"Traditional Arabic",Arial;
  font-size:13px; flex:1; min-width:80px; cursor:pointer;
}
select:focus, input:focus { border-color:var(--gold); outline:none; }
button { border:none; border-radius:8px; padding:8px 14px; font-family:"Traditional Arabic",Arial;
         font-size:13px; font-weight:bold; cursor:pointer; white-space:nowrap; }
.btn-go     { background:var(--gold); color:#020B18; }
.btn-random, .btn-prev, .btn-next { background:rgba(0,188,212,0.15); color:var(--navy); border:1.5px solid var(--navy); }
.btn-play   { background:rgba(0,200,83,0.15); color:var(--green); border:1.5px solid var(--green); }
.btn-stop   { background:rgba(239,83,80,0.15); color:var(--red); border:1.5px solid var(--red); }
.speed-bar { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.speed-label { font-size:12px; color:var(--gold); font-weight:bold; white-space:nowrap; }
.speed-btn { padding:5px 11px; border-radius:20px; font-size:12px; font-weight:bold;
             border:1.5px solid var(--navy); background:#0A2040; color:var(--navy); cursor:pointer; }
.speed-btn.active { background:var(--navy); color:#020B18; }

.legend { display:flex; gap:6px; padding:8px 14px; flex-wrap:wrap;
          background:var(--bg); border-bottom:1px solid var(--border); align-items:center; }
.legend-item { display:flex; align-items:center; gap:5px; font-size:12px; font-weight:bold;
               padding:3px 10px; border-radius:20px; white-space:nowrap; cursor:pointer; opacity:0.75; }
.legend-item.active { opacity:1; box-shadow:0 0 0 2px currentColor; }

.info-bar { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap;
            padding:8px 14px; background:var(--card); border-bottom:1px solid var(--border); font-size:13px; }
.info-page { color:#F0C755; font-weight:bold; }
.cnt-badge { padding:2px 10px; border-radius:20px; font-size:12px; font-weight:bold;
             background:rgba(212,168,67,0.15); color:var(--gold); border:1px solid var(--gold); }

.ayah-wrap { padding:12px 14px 4px; }
.ayah-meta { font-size:13px; color:#F0C755; font-weight:bold; margin-bottom:6px; }
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
.notify { display:none; margin:0 14px 10px; padding:8px 14px; border-radius:10px;
  background:rgba(255,152,0,0.12); border:1px solid #FF9800; color:#FFB74D; font-size:13px; text-align:center; }
.notify.show { display:block; }

.table-wrap { margin:12px 14px 20px; border:1px solid var(--border); border-radius:14px; overflow:hidden; }
.table-header { background:linear-gradient(90deg,#0D3060,#0D2847); padding:10px 14px; color:#F0C755;
                font-weight:bold; font-size:13px; border-bottom:2px solid var(--gold); }
.btn-showall { background:rgba(212,168,67,0.15); color:var(--gold); border:1.5px solid var(--gold);
               padding:4px 12px; font-size:11px; border-radius:20px; }
table { width:100%; border-collapse:collapse; background:#061525; }
th { background:#0D3060; color:#F0C755; padding:9px 6px; border-bottom:2px solid var(--gold);
     font-size:12px; font-weight:bold; }
td { padding:9px 6px; border-bottom:1px solid var(--border); text-align:center; font-size:12px; color:var(--text); }
tr:nth-child(even) td { background:#0A2040; }
tr:last-child td { border-bottom:none; }
tr.case-row { cursor:pointer; }
.word-cell { font-family:"KFGQPC_HAFS_Uthmanic_Script_H","Traditional Arabic";
             font-size:clamp(16px,4.5vw,20px); font-weight:bold; }

#wordOverlay, #allCasesOverlay { display:none; position:fixed; top:0;left:0;right:0;bottom:0;
  background:rgba(0,0,0,0.65); z-index:2000; align-items:center; justify-content:center; padding:16px; }
#wordOverlay.show, #allCasesOverlay.show { display:flex; }
#wordModal, .all-cases-modal { background:#0D2847; border-radius:16px; padding:20px; max-width:420px;
  width:100%; max-height:82vh; overflow-y:auto; direction:rtl;
  box-shadow:0 8px 40px rgba(0,0,0,0.6); border:2px solid rgba(212,168,67,0.55); }
.all-cases-modal { max-width:680px; }
.all-cases-modal table { width:100%; }
#wordTitle { font-family:"KFGQPC_HAFS_Uthmanic_Script_H","Traditional Arabic";
             font-size:24px; text-align:center; margin-bottom:6px; font-weight:bold; }
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
  <div class="header-title">أحكام الميم الساكنة في القرآن الكريم</div>
  <div class="header-sub">إظهار شفوي، إخفاء شفوي، إدغام شفوي (مثلين صغير)</div>
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
    <span class="ctrl-label">الصفحة:</span>
    <input type="number" id="pageInput" min="1" max="604" value="1" style="max-width:90px;">
    <button class="btn-go" onclick="loadPage(parseInt(document.getElementById('pageInput').value)||1)">عرض</button>
    <button class="btn-random" onclick="loadRandomPage()">🔀 عشوائية</button>
    <button class="btn-prev" onclick="jumpPage(-1)">◄ السابقة</button>
    <button class="btn-next" onclick="jumpPage(1)">التالية ►</button>
  </div>
  <div class="ctrl-row">
    <span class="ctrl-label">الحكم:</span>
    <select id="selType" onchange="loadPage(currentPage)"></select>
    <span class="ctrl-label">السبب:</span>
    <select id="selSabab" onchange="loadPage(currentPage)"></select>
  </div>
  <div class="ctrl-row">
    <span class="ctrl-label">القارئ:</span>
    <select id="selReader"></select>
    <button class="btn-play" onclick="playFirstAyah()">▶ استمع</button>
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

<div class="info-bar">
  <div class="info-page" id="infoPage">الصفحة —</div>
  <div class="cnt-badge" id="infoCount">0 حالة</div>
</div>

<div class="notify" id="notify"></div>

<div id="ayatContainer"></div>

<div class="table-wrap">
  <div class="table-header" style="display:flex;justify-content:space-between;align-items:center;">
    <span>📋 كل حالات الميم الساكنة في هذه الصفحة</span>
    <button class="btn-showall" onclick="showAllCases()">⛶ عرض الكل</button>
  </div>
  <table>
    <thead><tr>
      <th>السورة</th><th>الآية</th><th>الكلمة الأولى</th><th>الكلمة الثانية</th><th>الحرف التالي</th><th>الحكم</th>
    </tr></thead>
    <tbody id="casesTable"></tbody>
  </table>
</div>

<div id="allCasesOverlay" onclick="closeAllCases(event)">
  <div class="all-cases-modal">
    <div class="table-header" style="margin:-20px -20px 12px;border-radius:16px 16px 0 0;">📋 كل حالات الميم الساكنة في هذه الصفحة</div>
    <table>
      <thead><tr>
        <th>السورة</th><th>الآية</th><th>الكلمة الأولى</th><th>الكلمة الثانية</th><th>الحرف التالي</th><th>الحكم</th>
      </tr></thead>
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
let currentPage  = 1;
let currentSpeed = 1.0;
let pageVerses   = [];
let casesRowsHtml = '';
const audio = document.getElementById('audioPlayer');
const MIM_COLORS = {'إظهار شفوي':'#00C853','إخفاء شفوي':'#00E5FF','إدغام شفوي':'#FFD700'};
const MIM_DEFS = {
  'إظهار شفوي': 'إظهار الميم الساكنة بوضوح من غير غنة، إذا جاء بعدها أي حرف من حروف الهجاء غير الباء والميم، مثل: أَنۡعَمۡتَ عَلَيۡهِمۡ غَيۡرِ',
  'إخفاء شفوي': 'إخفاء الميم الساكنة بغنة مع بقاء الغنة، إذا جاء بعدها حرف الباء، مع إغلاق الشفتين قليلاً بلا التصاق كامل، مثل: لَهُم بِئۡسَ',
  'إدغام شفوي': 'إدغام الميم الساكنة في الميم المتحركة لتصبح ميماً واحدة مشددة بغنة، إذا جاء بعدها حرف الميم (يُسمى أيضاً مثلين صغير)، مثل: هُم مِّن',
};

function showNotify(msg) {
  const n = document.getElementById('notify');
  n.textContent = msg; n.classList.add('show');
  clearTimeout(window._notifyTimer);
  window._notifyTimer = setTimeout(() => n.classList.remove('show'), 4000);
}

async function loadReaders() {
  const r = await fetch('/api/readers');
  const d = await r.json();
  document.getElementById('selReader').innerHTML =
    d.map(x => `<option value="${x.id}">${x.label}</option>`).join('');
}

function buildLegend() {
  document.getElementById('legend').innerHTML = Object.entries(MIM_COLORS).map(([name,color]) =>
    `<span class="legend-item" style="background:${color}22;color:${color};border:2px solid ${color};"
      onclick="filterByType('${name}')">● ${name}</span>`).join('');
  const selType = document.getElementById('selType');
  selType.innerHTML = '<option value="الكل">الكل</option>' +
    Object.keys(MIM_COLORS).map(n => `<option value="${n}">${n}</option>`).join('');
}

async function loadSababOptions() {
  const r = await fetch('/api/mim/sabab');
  const d = await r.json();
  document.getElementById('selSabab').innerHTML =
    '<option value="الكل">الكل</option>' + d.map(s => `<option value="${s}">${s}</option>`).join('');
}

function filterByType(name) { document.getElementById('selType').value = name; loadPage(currentPage); }

function setSpeed(v, btn) {
  currentSpeed = v; audio.playbackRate = v;
  document.querySelectorAll('.speed-btn').forEach(b => b.classList.toggle('active', b === btn));
}
function stopAudio() { audio.pause(); audio.currentTime = 0; }

function playFirstAyah() {
  if (!pageVerses.length) { showNotify('لا توجد آية لتشغيلها.'); return; }
  playAyahAt(pageVerses[0].suraid, pageVerses[0].verseid);
}
function playAyahAt(suraid, verseid) {
  const reader = document.getElementById('selReader').value;
  const fname  = String(suraid).padStart(3,'0') + String(verseid).padStart(3,'0') + '.mp3';
  audio.src = `/audio/${reader}/${fname}`;
  audio.playbackRate = currentSpeed;
  audio.play().catch(() => showNotify('⚠️ ملف الصوت غير متوفر لهذا القارئ.'));
}

// ── تحديد نطاق حر بالسحب (drag-select) عبر أي عدد من صناديق الآيات
// المعروضة في الصفحة معاً — كل صندوق له مفتاحه الخاص (سورة-آية) بحيث
// لا يمتد السحب عبر آيتين مختلفتين.
let versesData = {};
let dragBoxKey = null;
let dragStart = null, dragEnd = null, isDragging = false;
let dragInit = false;

function vkey(suraid, verseid) { return suraid + '-' + verseid; }

function tokenFromEvent(e) {
  const t = e.target.closest('.word-tok[data-key]');
  return t ? { key: t.dataset.key, idx: parseInt(t.dataset.idx, 10) } : null;
}
function paintSelection() {
  if (!dragBoxKey) return;
  const lo = Math.min(dragStart, dragEnd), hi = Math.max(dragStart, dragEnd);
  document.querySelectorAll(`.word-tok[data-key="${dragBoxKey}"]`).forEach(el => {
    const i = parseInt(el.dataset.idx, 10);
    el.classList.toggle('dragsel', i >= lo && i <= hi);
  });
}
function clearSelection() {
  if (dragBoxKey) document.querySelectorAll(`.word-tok[data-key="${dragBoxKey}"]`).forEach(el => el.classList.remove('dragsel'));
  dragStart = dragEnd = null; isDragging = false; dragBoxKey = null;
}
function initDragSelect() {
  const container = document.getElementById('ayatContainer');
  if (!container || dragInit) return;
  dragInit = true;
  container.addEventListener('mousedown', e => {
    const tok = tokenFromEvent(e);
    if (!tok) return;
    isDragging = true; dragBoxKey = tok.key; dragStart = dragEnd = tok.idx; paintSelection();
    e.preventDefault();
  });
  container.addEventListener('mouseover', e => {
    if (!isDragging) return;
    const tok = tokenFromEvent(e);
    if (!tok || tok.key !== dragBoxKey) return;
    dragEnd = tok.idx; paintSelection();
  });
  document.addEventListener('mouseup', () => {
    if (!isDragging) return;
    isDragging = false;
    if (dragStart === null || dragEnd === null || !dragBoxKey) return;
    openSelectionExplain(dragBoxKey, Math.min(dragStart, dragEnd), Math.max(dragStart, dragEnd));
  });
  container.addEventListener('touchstart', e => {
    const el = document.elementFromPoint(e.touches[0].clientX, e.touches[0].clientY);
    const t = el?.closest('.word-tok[data-key]');
    if (!t) return;
    isDragging = true; dragBoxKey = t.dataset.key; dragStart = dragEnd = parseInt(t.dataset.idx, 10); paintSelection();
  }, {passive:true});
  container.addEventListener('touchmove', e => {
    if (!isDragging) return;
    const el = document.elementFromPoint(e.touches[0].clientX, e.touches[0].clientY);
    const t = el?.closest('.word-tok[data-key]');
    if (!t || t.dataset.key !== dragBoxKey) return;
    dragEnd = parseInt(t.dataset.idx, 10); paintSelection();
  }, {passive:true});
  container.addEventListener('touchend', () => { document.dispatchEvent(new Event('mouseup')); });
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

function renderPage(data) {
  pageVerses = data.verses || [];
  document.getElementById('infoPage').textContent = `الصفحة ${data.page}`;
  const totalCases = pageVerses.reduce((s,v) => s + v.cases.length, 0);
  document.getElementById('infoCount').textContent = `${totalCases} حالة`;

  const container = document.getElementById('ayatContainer');
  if (!pageVerses.length) {
    container.innerHTML = '';
    showNotify('لا يوجد أحكام ميم ساكنة موثّقة في هذه الصفحة (أو حسب الفلتر الحالي) — استخدم ◄ أو ► للانتقال لأقرب صفحة.');
    document.getElementById('casesTable').innerHTML = '';
    casesRowsHtml = '';
    return;
  }

  versesData = {};
  container.innerHTML = pageVerses.map(v => {
    const key = vkey(v.suraid, v.verseid);
    const words = v.aya_text.split(/\s+/).filter(Boolean);
    const caseByIdx = {};
    v.cases.forEach(c => {
      [c.klma1, c.klma2].forEach(w => {
        if (!w) return;
        const [lo, hi] = findWordRange(words, w);
        if (lo === -1) return;
        for (let i = lo; i <= hi; i++) { if (!caseByIdx[i]) caseByIdx[i] = c; }
      });
    });
    versesData[key] = { words, caseByIdx, suraid: v.suraid, verseid: v.verseid, suraname: v.suraname };

    const text = words.map((w, i) =>
      caseByIdx[i]
        ? `<span class="word-tok" data-key="${key}" data-idx="${i}" style="color:${caseByIdx[i].color};font-weight:bold;">${w}</span>`
        : `<span class="word-tok" data-key="${key}" data-idx="${i}" style="color:var(--text)">${w}</span>`
    ).join(' ');

    return `
      <div class="ayah-wrap">
        <div class="ayah-meta">سورة ${v.suraname} — الآية ${v.verseid}
          <span class="word-tok" style="color:var(--navy);font-size:12px;" onclick="playAyahAt(${v.suraid},${v.verseid})">🔊 استمع للآية</span>
        </div>
        <div class="ayah-box">${text}</div>
      </div>`;
  }).join('');
  initDragSelect();

  const rows = [];
  pageVerses.forEach(v => {
    const key = vkey(v.suraid, v.verseid);
    v.cases.forEach((c, ci) => {
      rows.push(`<tr class="case-row" data-key="${key}" data-caseidx="${ci}">
        <td>${v.suraname}</td><td>${v.verseid}</td>
        <td class="word-cell" style="color:${c.color};">${c.klma1}</td>
        <td class="word-cell" style="color:${c.color};">${c.klma2 || '—'}</td>
        <td style="font-weight:bold;color:var(--muted);">${c.next_char || '—'}</td>
        <td style="color:${c.color};">${c.icon} ${c.rule_type}</td>
      </tr>`);
    });
  });
  casesRowsHtml = rows.join('');
  document.getElementById('casesTable').innerHTML = casesRowsHtml;
  bindCaseRowClicks('casesTable');
}

function bindCaseRowClicks(tbodyId) {
  document.querySelectorAll(`#${tbodyId} tr.case-row`).forEach(tr => {
    tr.addEventListener('click', () => {
      const key = tr.dataset.key, ci = parseInt(tr.dataset.caseidx, 10);
      const v = pageVerses.find(vv => vkey(vv.suraid, vv.verseid) === key);
      const c = v && v.cases[ci];
      const vd = versesData[key];
      if (!v || !c || !vd) return;
      const idxs = Object.keys(vd.caseByIdx).map(Number).filter(i => vd.caseByIdx[i] === c);
      if (idxs.length) { openSelectionExplain(key, Math.min(...idxs), Math.max(...idxs)); closeAllCases(); }
    });
  });
}

function showAllCases() {
  if (!casesRowsHtml) { showNotify('لا يوجد حالات لعرضها في هذه الصفحة.'); return; }
  document.getElementById('allCasesTable').innerHTML = casesRowsHtml;
  bindCaseRowClicks('allCasesTable');
  document.getElementById('allCasesOverlay').classList.add('show');
}
function closeAllCases(e) {
  if (e && e.target.id !== 'allCasesOverlay') return;
  document.getElementById('allCasesOverlay').classList.remove('show');
}

async function loadPage(page) {
  page = Math.max(1, Math.min(604, page || 1));
  currentPage = page;
  document.getElementById('pageInput').value = page;
  const type  = document.getElementById('selType').value || 'الكل';
  const sabab = document.getElementById('selSabab').value || 'الكل';
  const r = await fetch(`/api/mim/page?page=${page}&type=${encodeURIComponent(type)}&sabab=${encodeURIComponent(sabab)}`);
  const d = await r.json();
  renderPage(d);
}

async function jumpPage(direction) {
  const type  = document.getElementById('selType').value || 'الكل';
  const sabab = document.getElementById('selSabab').value || 'الكل';
  const r = await fetch(`/api/mim/nearest?page=${currentPage}&dir=${direction}&type=${encodeURIComponent(type)}&sabab=${encodeURIComponent(sabab)}`);
  const d = await r.json();
  if (d.page && d.page > 0) loadPage(d.page);
  else showNotify('لا توجد صفحة أخرى تحتوي حالات مطابقة في هذا الاتجاه.');
}

async function loadRandomPage() {
  const type  = document.getElementById('selType').value || 'الكل';
  const sabab = document.getElementById('selSabab').value || 'الكل';
  const r = await fetch(`/api/mim/random?type=${encodeURIComponent(type)}&sabab=${encodeURIComponent(sabab)}`);
  const d = await r.json();
  loadPage(d.page || 1);
}

// يفتح نافذة الشرح + التلاوة الدقيقة لأي مجال كلمات محدَّد (كلمة واحدة
// عبر نقرة بسيطة، أو عدة كلمات عبر السحب) ضمن آية بعينها (key)
let currentWordCtx = null;
function openSelectionExplain(key, lo, hi) {
  const vd = versesData[key];
  if (!vd) { clearSelection(); return; }
  const phrase = vd.words.slice(lo, hi + 1).join(' ');
  const rulings = [];
  for (let i = lo; i <= hi; i++) if (vd.caseByIdx[i] && !rulings.includes(vd.caseByIdx[i])) rulings.push(vd.caseByIdx[i]);
  const color = rulings[0]?.color || '#D4A843';
  currentWordCtx = { suraid: vd.suraid, verseid: vd.verseid, suraname: vd.suraname, lo, hi, phrase, rulings };
  document.getElementById('wordTitle').textContent = phrase;
  document.getElementById('wordTitle').style.color = color;
  document.getElementById('wordContext').textContent =
    `سورة ${vd.suraname} — الآية ${vd.verseid}` +
    (rulings.length ? ' — ' + rulings.map(r => `${r.rule_type} (${r.sabab || ''})`).join('، ') : '');
  document.getElementById('wordResult').textContent =
    rulings.length ? (MIM_DEFS[rulings[0].rule_type] || '') : 'ميم ساكنة عادية بلا حكم شفوي موثّق هنا.';
  document.getElementById('clipStatus').textContent = '';
  document.getElementById('wordQuestion').value = '';
  document.getElementById('wordOverlay').classList.add('show');
  clearSelection();
}
function closeWordModal(e) {
  if (e && e.target.id !== 'wordOverlay') return;
  document.getElementById('wordOverlay').classList.remove('show');
}

const clipPlayer = document.getElementById('clipPlayer');
function playClipReciter(reciter) {
  if (!currentWordCtx) return;
  const status = document.getElementById('clipStatus');
  const p = new URLSearchParams({
    suraid: currentWordCtx.suraid, verseid: currentWordCtx.verseid, reciter,
    type: 'range', lo: currentWordCtx.lo, hi: currentWordCtx.hi,
  });
  status.textContent = '⏳ جارٍ التحضير...';
  clipPlayer.src = '/api/mim/clip?' + p.toString();
  clipPlayer.play().then(() => { status.textContent = ''; })
    .catch(async () => {
      try {
        const r = await fetch('/api/mim/clip?' + p.toString());
        const j = await r.json();
        status.textContent = '⚠ ' + (j.error || 'تعذّر تشغيل المقطع.');
      } catch (e) { status.textContent = '⚠ تعذّر تشغيل المقطع.'; }
    });
}

async function askAI() {
  if (!currentWordCtx) return;
  const { phrase, suraname, verseid, rulings } = currentWordCtx;
  const question = document.getElementById('wordQuestion').value.trim();
  if (!question) return;
  const resultBox = document.getElementById('wordResult');
  resultBox.textContent = '...جاري التفكير';
  try {
    const r = await fetch('/api/mim/explain', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ word: phrase, sura: suraname, verse: verseid, question,
                              ruling: rulings.map(r => r.rule_type).join('، ') })
    });
    const j = await r.json();
    resultBox.textContent = j.answer || 'تعذّر جلب الإجابة.';
  } catch (e) {
    resultBox.textContent = 'تعذّر الاتصال بالخدمة.';
  }
}

(async function init() {
  buildLegend();
  await loadReaders();
  await loadSababOptions();
  await loadPage(1);
})();
</script>
</body>
</html>'''

# ══════════════════════════════════════════════════════════════
#  المسارات (Routes)
# ══════════════════════════════════════════════════════════════
@bp.route('/mim')
def index():
    return HTML

@bp.route('/api/mim/page')
def api_page():
    page  = request.args.get('page', 1, type=int)
    type_filter  = request.args.get('type', 'الكل')
    sabab_filter = request.args.get('sabab', 'الكل')
    verses = _load_page(page, type_filter, sabab_filter)
    return jsonify({'page': page, 'verses': verses})

@bp.route('/api/mim/nearest')
def api_nearest():
    page      = request.args.get('page', 1, type=int)
    direction = request.args.get('dir', 1, type=int)
    type_filter  = request.args.get('type', 'الكل')
    sabab_filter = request.args.get('sabab', 'الكل')
    return jsonify({'page': _find_nearest_page(page, direction, type_filter, sabab_filter)})

@bp.route('/api/mim/random')
def api_random():
    type_filter  = request.args.get('type', 'الكل')
    sabab_filter = request.args.get('sabab', 'الكل')
    page, err = _random_page(type_filter, sabab_filter)
    resp = {'page': page}
    if err:
        resp['error'] = err
    return jsonify(resp)

@bp.route('/api/mim/sabab')
def api_sabab():
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute('SELECT DISTINCT sabab FROM mim_rules WHERE sabab IS NOT NULL ORDER BY sabab')
        rows = [r[0] for r in cur.fetchall()]
    except Exception:
        rows = []
    conn.close()
    return jsonify(rows)

@bp.route('/api/mim/clip')
def api_clip():
    """يُرجع مقطعاً صوتياً دقيقاً (كلمة واحدة أو مجال كلمات متتالية،
    محدَّد بالسحب) مقتطعاً من تلاوة أحد القرّاء الأربعة، بالاعتماد على
    word_audio_helper — نفس آلية /api/mdcon/clip تماماً."""
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

@bp.route('/api/mim/explain', methods=['POST'])
def api_explain():
    import http.client as _hc
    data     = request.get_json(force=True)
    word     = data.get('word', '')
    sura     = data.get('sura', '')
    verse    = data.get('verse', '')
    question = data.get('question', f'ما حكم الميم الساكنة في كلمة {word} في القرآن الكريم؟')
    ruling   = data.get('ruling', '')

    ruling_info = f'\nالحكم المؤكد من قاعدة البيانات: {ruling}' if ruling else ''
    API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

    try:
        system = ("You are an expert in Quran Tajweed specializing in Meem Sakinah rules "
                  "(Izhar Shafawi, Ikhfa Shafawi, Idgham Shafawi). Answer briefly in max 3-4 lines. "
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


