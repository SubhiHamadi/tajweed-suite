"""
ikhfa_web_app.py — الإخفاء الحقيقي في القرآن الكريم (نسخة الويب، مستوى الصفحة)
نسخة Flask من ikhfa_page_app.py، مبنية على نفس تصميم md_con_web_app.py
(الألوان، الرأسية، أشرطة التحكم) لضمان مظهر موحّد عبر السويطة.
يعمل على بورت 5040 (خارج نطاق 5009–5038 المستخدم أصلاً؛ عدّله عند الحاجة).
"""
import os, re, sys, sqlite3, json, random
from flask import Flask, Blueprint, jsonify, request, send_from_directory, send_file

bp = Blueprint('ikhfa', __name__)
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# البحث عن قاعدة البيانات: مجلد المشروع أولاً (وهو ما يعمل فعلياً بعد
# النشر على استضافة سحابية)، ثم مسارات التطوير المحلية على ويندوز كاحتياط.
def _find_db_path():
    candidates = [
        '/var/data/quran.db',
        os.path.join(BASE_DIR, 'quran.db'),
        r'D:\family\quran.db',
        r'E:\family\quran.db',
    ]
    for c in candidates:
        # نتجاهل ملفًا موجودًا لكن فارغًا (0 بايت) — قد يكون ملف تمهيدي
        # فارغ انتقل بالخطأ إلى مستودع الكود، ولا يجوز اعتباره القاعدة الحقيقية.
        if os.path.exists(c) and os.path.getsize(c) > 0:
            return c
    return candidates[0]

DB_PATH = _find_db_path()

def _find_audio_base_dir():
    """يبحث عن مجلد الصوتيات (مجلد فرعي لكل قارئ) — على Render يكون
    على القرص الدائم /var/data وليس مجلد الكود القادم من GitHub."""
    candidates = ['/var/data', BASE_DIR]
    for c in candidates:
        if os.path.isdir(c):
            try:
                subdirs = [d for d in os.listdir(c) if os.path.isdir(os.path.join(c, d))]
            except Exception:
                subdirs = []
            if subdirs:
                return c
    return BASE_DIR

AUDIO_BASE_DIR = _find_audio_base_dir()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

IKHFA_COLOR = '#FF4081'  # لون موحَّد لحكم الإخفاء الحقيقي (لا يوجد سوى نوع واحد)

# ══════════════════════════════════════════════════════════════
#  حرف الإخفاء — نفس منطق ikhfa_page_app.py المحدَّث حديثاً
# ══════════════════════════════════════════════════════════════
IKHFA_LETTERS = 'صذثكجشقسدطزفتضظ'
_DIACRITICS_RE = re.compile(r'[\u064B-\u065F\u0610-\u061A\u06D6-\u06ED\u0670]')

def _strip_diacritics(s):
    return _DIACRITICS_RE.sub('', s or '')

def _ikhfa_letter(case):
    primary = case.get('primary_word') or ''
    other   = case.get('other_word') or ''
    if other:
        bare = _strip_diacritics(other)
        for ch in bare:
            if ch in IKHFA_LETTERS:
                return ch
        return bare[:1] if bare else ''
    bare = _strip_diacritics(primary)
    for i, ch in enumerate(bare):
        if ch == 'ن':
            for j in range(i + 1, len(bare)):
                if bare[j] in IKHFA_LETTERS:
                    return bare[j]
    for ch in bare:
        if ch in IKHFA_LETTERS:
            return ch
    return ''

def _note_text(case):
    letter = _ikhfa_letter(case)
    extra  = '↳ يبدأ في الآية السابقة' if case.get('is_continuation') else \
             ('↳ يكتمل في الآية التالية' if case.get('crosses') else '')
    parts = ([f'حرف الإخفاء: {letter}'] if letter else []) + ([extra] if extra else [])
    return '  —  '.join(parts)

# ══════════════════════════════════════════════════════════════
#  تنظيف نص الآية (نفس قاعدة md_con_web_app.py)
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
#  القرّاء وملفات الصوت (نفس منطق md_con_web_app.py)
# ══════════════════════════════════════════════════════════════
READER_NAMES = {
    'Aya1Aya' : 'مشاري راشد العفاسي',
    'Aya9Aya' : 'محمد صديق المنشاوي — المعلم',
    'AyaEAya' : '🇬🇧 Ibrahim Walk (English)',
    'AyaTRAya': '🇹🇷 الترجمة التركية',
    'AyaASaya': '🇦🇿 الترجمة الأذربيجانية',
}
SKIP = {'AyaAya', 'Husary', 'abdulstar', 'kolon', 'mnshawi'}

try:
    from word_audio_helper import prepare_word_clip, prepare_range_clip
    _WORD_AUDIO_OK = True
except Exception:
    _WORD_AUDIO_OK = False

def _get_readers_dict():
    d = {}
    if os.path.isdir(AUDIO_BASE_DIR):
        for f in os.listdir(AUDIO_BASE_DIR):
            if f in SKIP:
                continue
            fp = os.path.join(AUDIO_BASE_DIR, f)
            if os.path.isdir(fp):
                d[f] = fp
    return d

# ══════════════════════════════════════════════════════════════
#  الترجمات والتفسير — نفس الجداول والمنطق المستخدم في bp_lazm.py
#  (المد اللازم)، إذ يتشاركان قاعدة البيانات نفسها quran.db
# ══════════════════════════════════════════════════════════════
def _get_translations(cur, suraid, verseid):
    en = tf = ur = ku = tr = az = ''
    try:
        cur.execute('SELECT text_en FROM quran_en WHERE suraid=? AND verseid=? LIMIT 1', (suraid, verseid))
        r = cur.fetchone(); en = r[0] if r else ''
    except Exception: pass
    try:
        cur.execute('SELECT tafseer FROM tafseer_jalalayn WHERE suraid=? AND verseid=? LIMIT 1', (suraid, verseid))
        r = cur.fetchone(); tf = r[0] if r else ''
    except Exception: pass
    try:
        cur.execute('SELECT text_ur FROM quran_ur WHERE suraid=? AND verseid=? LIMIT 1', (suraid, verseid))
        r = cur.fetchone(); ur = r[0] if r else ''
    except Exception: pass
    try:
        cur.execute('SELECT text_ku FROM quran_ku WHERE suraid=? AND verseid=? LIMIT 1', (suraid, verseid))
        r = cur.fetchone(); ku = r[0] if r else ''
    except Exception: pass
    try:
        cur.execute('SELECT text_tr FROM quran_tr WHERE suraid=? AND verseid=? LIMIT 1', (suraid, verseid))
        r = cur.fetchone(); tr = r[0] if r else ''
    except Exception: pass
    try:
        cur.execute('SELECT text_az FROM quran_az WHERE suraid=? AND verseid=? LIMIT 1', (suraid, verseid))
        r = cur.fetchone(); az = r[0] if r else ''
    except Exception: pass
    return {'en': en, 'tf': tf, 'ur': ur, 'ku': ku, 'tr': tr, 'az': az}

# ══════════════════════════════════════════════════════════════
#  منطق الصفحة — منقول من PageLoadThread / FindPageThread في
#  ikhfa_page_app.py دون أي تغيير في الاستعلامات
# ══════════════════════════════════════════════════════════════
def _load_page(page_num):
    conn = get_db(); cur = conn.cursor()
    result = []
    try:
        cur.execute("""
            SELECT SURAID, VERSEID, SURANAME, ayahtext
            FROM mushafnew WHERE PAGENUM=? ORDER BY SURAID, VERSEID
        """, (page_num,))
        page_ayat = cur.fetchall()

        for suraid, verseid, suraname, aya_text in page_ayat:
            cur.execute("""
                SELECT klma1, klma2, verseid, verseid1, kseq, itype
                FROM newtaj
                WHERE itype LIKE '%إخفاء%' AND suraid=?
                  AND (verseid=? OR (verseid1=? AND verseid<>verseid1))
                ORDER BY kseq
            """, (suraid, verseid, verseid))
            rows = cur.fetchall()

            cases = []
            for klma1, klma2, r_verseid, r_verseid1, kseq, itype in rows:
                klma1 = (klma1 or '').strip(); klma2 = (klma2 or '').strip()
                if r_verseid == verseid:
                    crosses = bool(klma2 and r_verseid1 and r_verseid1 != r_verseid)
                    cases.append({
                        'primary_word'   : klma1, 'kseq': kseq, 'itype': itype,
                        'is_continuation': False,
                        'other_word'     : klma2 if (klma2 and not crosses) else '',
                        'crosses'        : crosses,
                        'other_suraid'   : suraid if crosses else None,
                        'other_verseid'  : r_verseid1 if crosses else None,
                    })
                elif r_verseid1 == verseid and r_verseid != r_verseid1:
                    cases.append({
                        'primary_word'   : klma2, 'kseq': -1, 'itype': itype,
                        'is_continuation': True,
                        'other_word'     : klma1, 'crosses': True,
                        'other_suraid'   : suraid, 'other_verseid': r_verseid,
                    })

            cases.sort(key=lambda c: 0 if c['is_continuation'] else 1)

            if cases:
                for c in cases:
                    c['note'] = _note_text(c)
                trans = _get_translations(cur, suraid, verseid)
                result.append({
                    'suraid'  : suraid, 'verseid': verseid,
                    'suraname': suraname, 'aya_text': _clean_aya(aya_text or ''),
                    'cases'   : cases,
                    **trans,
                })
    except Exception:
        result = []
    finally:
        conn.close()
    return result

def _find_nearest_page(current_page, direction):
    conn = get_db(); cur = conn.cursor()
    try:
        if direction == 1:
            cur.execute("""
                SELECT DISTINCT m.PAGENUM FROM newtaj n
                JOIN mushafnew m ON m.SURAID=n.suraid AND m.VERSEID=n.verseid
                WHERE n.itype LIKE '%إخفاء%' AND m.PAGENUM > ?
                ORDER BY m.PAGENUM ASC LIMIT 1
            """, (current_page,))
        else:
            cur.execute("""
                SELECT DISTINCT m.PAGENUM FROM newtaj n
                JOIN mushafnew m ON m.SURAID=n.suraid AND m.VERSEID=n.verseid
                WHERE n.itype LIKE '%إخفاء%' AND m.PAGENUM < ?
                ORDER BY m.PAGENUM DESC LIMIT 1
            """, (current_page,))
        r = cur.fetchone()
        return r[0] if r else -1
    except Exception:
        return -1
    finally:
        conn.close()

def _random_page():
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("""
            SELECT DISTINCT m.PAGENUM FROM newtaj n
            JOIN mushafnew m ON m.SURAID=n.suraid AND m.VERSEID=n.verseid
            WHERE n.itype LIKE '%إخفاء%'
        """)
        pages = [row[0] for row in cur.fetchall() if row[0] is not None]
        return random.choice(pages) if pages else 1
    except Exception:
        return 1
    finally:
        conn.close()

# ══════════════════════════════════════════════════════════════
#  الواجهة (HTML/CSS/JS) — نفس هوية md_con_web_app.py البصرية
# ══════════════════════════════════════════════════════════════
HTML = r'''<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>الإخفاء الحقيقي في القرآن الكريم</title>
<style>
:root {
  --navy:  #00BCD4; --navy2: #0A2040; --gold:  #D4A843; --gold2: #0D2847;
  --green: #00C853; --red:   #EF5350; --bg:    #020B18; --card:  #0D2847;
  --border:#1A3A5C; --text:  #F8F4EE; --muted: #B0BEC5; --ikhfa: #FF4081;
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
.btn-random { background:rgba(0,188,212,0.15); color:var(--navy); border:1.5px solid var(--navy); }
.btn-prev, .btn-next { background:rgba(0,188,212,0.15); color:var(--navy); border:1.5px solid var(--navy); }
.btn-play   { background:rgba(0,200,83,0.15); color:var(--green); border:1.5px solid var(--green); }
.btn-stop   { background:rgba(239,83,80,0.15); color:var(--red); border:1.5px solid var(--red); }
.speed-bar { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.speed-label { font-size:12px; color:var(--gold); font-weight:bold; white-space:nowrap; }
.speed-btn { padding:5px 11px; border-radius:20px; font-size:12px; font-weight:bold;
             border:1.5px solid var(--navy); background:#0A2040; color:var(--navy); cursor:pointer; }
.speed-btn.active { background:var(--navy); color:#020B18; }

/* ── أزرار الترجمة والتفسير (بنفس نسق المد اللازم) ── */
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

.legend { display:flex; gap:8px; padding:8px 14px; flex-wrap:wrap;
          background:var(--bg); border-bottom:1px solid var(--border); align-items:center; }
.legend-item { display:flex; align-items:center; gap:5px; font-size:12px; font-weight:bold;
               padding:3px 10px; border-radius:20px; white-space:nowrap;
               background:rgba(255,64,129,0.1); color:var(--ikhfa); border:2px solid var(--ikhfa); }

.info-bar { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap;
            padding:8px 14px; background:var(--card); border-bottom:1px solid var(--border); font-size:13px; }
.info-page { color:#F0C755; font-weight:bold; }
.cnt-badge { padding:2px 10px; border-radius:20px; font-size:12px; font-weight:bold;
             background:rgba(255,64,129,0.15); color:var(--ikhfa); border:1px solid var(--ikhfa); }

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
.translation-box { margin:0 0 12px; padding:10px 14px; border-radius:10px; font-size:14px;
  line-height:185%; display:none; border:1px solid var(--border); background:#0A2040; }
.translation-box.show { display:block; }
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
table { width:100%; border-collapse:collapse; background:#061525; }
th { background:#0D3060; color:#F0C755; padding:9px 6px; border-bottom:2px solid var(--gold);
     font-size:12px; font-weight:bold; }
td { padding:9px 6px; border-bottom:1px solid var(--border); text-align:center; font-size:12px; color:var(--text); }
tr:nth-child(even) td { background:#0A2040; }
tr:last-child td { border-bottom:none; }
tr.case-row { cursor:pointer; }
.word-cell { font-family:"KFGQPC_HAFS_Uthmanic_Script_H","Traditional Arabic";
             font-size:clamp(16px,4.5vw,20px); font-weight:bold; color:var(--ikhfa); }

#wordOverlay, .help-overlay, #allCasesOverlay { display:none; position:fixed; top:0;left:0;right:0;bottom:0;
  background:rgba(0,0,0,0.65); z-index:2000; align-items:center; justify-content:center; padding:16px; }
#wordOverlay.show, .help-overlay.show, #allCasesOverlay.show { display:flex; }
#wordModal, .help-modal, .all-cases-modal { background:#0D2847; border-radius:16px; padding:20px; max-width:420px;
  width:100%; max-height:82vh; overflow-y:auto; direction:rtl;
  box-shadow:0 8px 40px rgba(0,0,0,0.6); border:2px solid rgba(212,168,67,0.55); }
.all-cases-modal { max-width:680px; }
.all-cases-modal table { width:100%; }
.btn-showall { background:rgba(212,168,67,0.15); color:var(--gold); border:1.5px solid var(--gold);
               padding:8px 24px; font-size:13px; border-radius:20px; font-weight:bold; }
#wordTitle { font-family:"KFGQPC_HAFS_Uthmanic_Script_H","Traditional Arabic";
             font-size:26px; color:#F0C755; text-align:center; margin-bottom:6px; font-weight:bold; }
#wordContext { font-size:12px; color:var(--muted); text-align:center; margin-bottom:14px; }
#wordResult { background:#061525; border-radius:10px; padding:14px; font-size:15px;
              line-height:185%; color:var(--text); border:1px solid var(--border); min-height:40px; margin-bottom:10px; }
.word-input-row { display:flex; gap:8px; margin-bottom:10px; }
.word-input { flex:1; border:1.5px solid var(--border); border-radius:10px; padding:8px 12px;
              font-family:"Traditional Arabic",Arial; font-size:14px; direction:rtl; background:#061525; color:var(--text); }
.word-ask-btn { background:var(--navy); color:#020B18; border:none; border-radius:10px;
                padding:8px 14px; font-size:13px; font-weight:bold; cursor:pointer; }
#wordClose, .help-close { width:100%; margin-top:6px; padding:9px; border:1.5px solid var(--red);
  border-radius:10px; background:rgba(239,83,80,0.1); cursor:pointer; font-size:14px; color:var(--red); }
.help-title { font-size:16px; font-weight:bold; color:#F0C755; text-align:center;
  margin-bottom:12px; border-bottom:2px solid var(--gold); padding-bottom:10px; }
.help-def { font-size:15px; line-height:190%; color:var(--text); margin-bottom:12px; }
.help-letters { background:#061525; border-radius:10px; padding:12px 14px; font-size:22px;
  text-align:center; margin-bottom:10px; letter-spacing:6px; color:var(--ikhfa); font-weight:bold; }

@media(max-width:480px) { .ctrl-row { flex-direction:column; align-items:stretch; } button, select { width:100%; } }
</style>
</head>
<body>

<header>
  <div class="header-title">الإخفاء الحقيقي في القرآن الكريم</div>
  <div class="header-sub">نون ساكنة أو تنوين تليها إحدى الحروف الخمسة عشر</div>
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
  <div class="ctrl-row" style="justify-content:center;gap:10px;flex-wrap:wrap;">
    <button class="btn-toggle btn-en" id="btnEn" onclick="toggleLang('en')">🇬🇧 الترجمة</button>
    <button class="btn-toggle btn-tf" id="btnTf" onclick="toggleLang('tf')">📖 التفسير</button>
    <button class="btn-toggle btn-ur" id="btnUr" onclick="toggleLang('ur')">🇵🇰 الأوردو</button>
    <button class="btn-toggle btn-ku" id="btnKu" onclick="toggleLang('ku')">🏴 الكردية</button>
    <button class="btn-toggle btn-tr" id="btnTr" onclick="toggleLang('tr')">🇹🇷 التركية</button>
    <button class="btn-toggle btn-az" id="btnAz" onclick="toggleLang('az')">🇦🇿 الأذربيجانية</button>
  </div>
  <div class="ctrl-row" style="justify-content:center;gap:10px;">
    <button class="btn-toggle" onclick="showHelp()"
      style="background:#EDE7F6;color:#512DA8;border:1.5px solid #9575CD;padding:8px 24px;">📚 تعريف الإخفاء الحقيقي</button>
    <button class="btn-showall" onclick="showAllCases()">⛶ عرض الكل</button>
  </div>
</div>

<div class="legend">
  <div class="legend-item">● إخفاء حقيقي</div>
</div>

<div class="info-bar">
  <div class="info-page" id="infoPage">الصفحة —</div>
  <div class="cnt-badge" id="infoCount">0 حالة</div>
</div>

<div class="notify" id="notify"></div>

<div id="ayatContainer"></div>

<div class="table-wrap">
  <div class="table-header">📋 كل حالات الإخفاء الحقيقي في هذه الصفحة</div>
  <table>
    <thead><tr>
      <th>السورة</th><th>الآية</th><th>الكلمة الأولى</th><th>الكلمة الثانية</th><th>الحكم</th><th>ملاحظة</th>
    </tr></thead>
    <tbody id="casesTable"></tbody>
  </table>
</div>

<div id="allCasesOverlay" onclick="closeAllCases(event)">
  <div class="all-cases-modal">
    <div class="table-header" style="margin:-20px -20px 12px;border-radius:16px 16px 0 0;">📋 كل حالات الإخفاء الحقيقي في هذه الصفحة</div>
    <table>
      <thead><tr>
        <th>السورة</th><th>الآية</th><th>الكلمة الأولى</th><th>الكلمة الثانية</th><th>الحكم</th><th>ملاحظة</th>
      </tr></thead>
      <tbody id="allCasesTable"></tbody>
    </table>
    <button id="wordClose" onclick="closeAllCases()" style="margin-top:12px;">✕ إغلاق</button>
  </div>
</div>

<audio id="audioPlayer"></audio>
<audio id="clipPlayer"></audio>

<!-- نافذة شرح الكلمة -->
<div id="wordOverlay" onclick="closeWordModal(event)">
  <div id="wordModal">
    <div id="wordTitle"></div>
    <div id="wordContext"></div>
    <div id="wordResult">إخفاء النون الساكنة أو التنوين عند أحد الحروف الخمسة عشر: صفة بين الإظهار والإدغام، بلا شدة، مع بقاء الغنة.</div>
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

<!-- نافذة التعريف -->
<div class="help-overlay" id="helpOverlay" onclick="hideHelp(event)">
  <div class="help-modal">
    <div class="help-title">📚 الإخفاء الحقيقي</div>
    <div class="help-def">
      إخفاء النون الساكنة أو التنوين عند لقائهما بأحد الحروف الخمسة عشر الآتية،
      بصفة بين الإظهار والإدغام، مع بقاء صفة الغنة ظاهرة في الحرف المخفى عنده.
    </div>
    <div class="help-letters">ص ذ ث ك ج ش ق س د ط ز ف ت ض ظ</div>
    <button class="help-close" onclick="hideHelp()">✕ إغلاق</button>
  </div>
</div>

<script>
let currentPage  = 1;
let currentSpeed = 1.0;
let pageVerses   = [];
let casesRowsHtml = '';
let activeLang = null;
const audio = document.getElementById('audioPlayer');

function showNotify(msg) {
  const n = document.getElementById('notify');
  n.textContent = msg; n.classList.add('show');
  clearTimeout(window._notifyTimer);
  window._notifyTimer = setTimeout(() => n.classList.remove('show'), 4000);
}

async function loadReaders() {
  const r = await fetch('/api/readers');
  const d = await r.json();
  const sel = document.getElementById('selReader');
  sel.innerHTML = d.map(x => `<option value="${x.id}">${x.label}</option>`).join('');
}

function setSpeed(v, btn) {
  currentSpeed = v; audio.playbackRate = v;
  document.querySelectorAll('.speed-btn').forEach(b => b.classList.toggle('active', b === btn));
}

function stopAudio() { audio.pause(); audio.currentTime = 0; }

function playFirstAyah() {
  if (!pageVerses.length) { showNotify('لا توجد آية لتشغيلها.'); return; }
  const v = pageVerses[0];
  const reader = document.getElementById('selReader').value;
  const fname  = String(v.suraid).padStart(3,'0') + String(v.verseid).padStart(3,'0') + '.mp3';
  audio.src = `/audio/${reader}/${fname}`;
  audio.playbackRate = currentSpeed;
  audio.play().catch(() => showNotify('⚠️ ملف الصوت غير متوفر لهذا القارئ.'));
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
// لا يمتد السحب عبر آيتين مختلفتين. نفس آلية md_con_web_app.py أساساً.
let versesData  = {};   // key -> {words, colored, caseByIdx, suraid, verseid, suraname}
let dragBoxKey  = null;
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
    showNotify('لا يوجد إخفاء حقيقي موثّق في هذه الصفحة — استخدم ◄ أو ► للانتقال لأقرب صفحة تحتوي حالات.');
    document.getElementById('casesTable').innerHTML = '';
    casesRowsHtml = '';
    return;
  }

  versesData = {};
  container.innerHTML = pageVerses.map(v => {
    const key = vkey(v.suraid, v.verseid);
    const words = v.aya_text.split(/\s+/).filter(Boolean);
    const colored = {}, caseByIdx = {};
    v.cases.forEach(c => {
      [c.primary_word, c.other_word].forEach(w => {
        if (!w) return;
        const [lo, hi] = findWordRange(words, w);
        if (lo === -1) return;
        for (let i = lo; i <= hi; i++) { if (!colored[i]) colored[i] = c; }
      });
    });
    Object.keys(colored).forEach(i => { caseByIdx[i] = colored[i]; });
    versesData[key] = { words, caseByIdx, suraid: v.suraid, verseid: v.verseid, suraname: v.suraname };

    const text = words.map((w, i) =>
      caseByIdx[i]
        ? `<span class="word-tok" data-key="${key}" data-idx="${i}" style="color:var(--ikhfa);font-weight:bold;">${w}</span>`
        : `<span class="word-tok" data-key="${key}" data-idx="${i}" style="color:var(--text)">${w}</span>`
    ).join(' ');

    return `
      <div class="ayah-wrap">
        <div class="ayah-meta">سورة ${v.suraname} — الآية ${v.verseid}
          <span class="word-tok" style="color:var(--navy);font-size:12px;" onclick="playAyahAt(${v.suraid},${v.verseid})">🔊 استمع للآية</span>
        </div>
        <div class="ayah-box">${text}</div>
        <div class="translation-box" id="trans-${v.suraid}-${v.verseid}"></div>
      </div>`;
  }).join('');
  initDragSelect();
  refreshTranslations();

  // جدول كل الحالات
  const rows = [];
  pageVerses.forEach(v => {
    const key = vkey(v.suraid, v.verseid);
    v.cases.forEach((c, ci) => {
      const first  = c.is_continuation ? (c.other_word || '—') : c.primary_word;
      const second = c.is_continuation ? c.primary_word : (c.other_word || '—');
      rows.push(`<tr class="case-row" data-key="${key}" data-caseidx="${ci}">
        <td>${v.suraname}</td><td>${v.verseid}</td>
        <td class="word-cell">${first}</td><td class="word-cell">${second}</td>
        <td>${c.itype}</td><td style="font-size:11px;color:var(--muted);">${c.note || ''}</td>
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

// ── الترجمة والتفسير (بنفس منطق المد اللازم) — لكن هنا تُعرض
// ترجمة كل آية تحت صندوقها هي مباشرة، لأن الصفحة تعرض عدة آيات معاً
const LANG_LABELS = { en: '🇬🇧', tf: '📖', ur: '🇵🇰', ku: '🏴', tr: '🇹🇷', az: '🇦🇿' };
const LANG_BTN_IDS = ['btnEn', 'btnTf', 'btnUr', 'btnKu', 'btnTr', 'btnAz'];

function toggleLang(lang) {
  if (activeLang === lang) {
    activeLang = null;
  } else {
    activeLang = lang;
  }
  LANG_BTN_IDS.forEach(id => document.getElementById(id)?.classList.remove('active'));
  if (activeLang) {
    const btn = document.getElementById('btn' + activeLang.charAt(0).toUpperCase() + activeLang.slice(1));
    btn?.classList.add('active');
  }
  refreshTranslations();
}

function refreshTranslations() {
  pageVerses.forEach(v => {
    const box = document.getElementById(`trans-${v.suraid}-${v.verseid}`);
    if (!box) return;
    if (!activeLang) { box.classList.remove('show'); box.textContent = ''; return; }
    const val = v[activeLang];
    box.textContent = `${LANG_LABELS[activeLang]} ${val || 'غير متاح'}`;
    box.classList.add('show');
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
  const r = await fetch(`/api/ikhfa/page?page=${page}`);
  const d = await r.json();
  renderPage(d);
}

async function jumpPage(direction) {
  // إن كانت الصفحة الحالية فارغة أو نريد أقرب صفحة تحتوي حالات
  const r = await fetch(`/api/ikhfa/nearest?page=${currentPage}&dir=${direction}`);
  const d = await r.json();
  if (d.page && d.page > 0) {
    loadPage(d.page);
  } else {
    showNotify('لا توجد صفحة أخرى تحتوي حالات إخفاء في هذا الاتجاه.');
  }
}

async function loadRandomPage() {
  const r = await fetch('/api/ikhfa/random');
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
  currentWordCtx = { suraid: vd.suraid, verseid: vd.verseid, suraname: vd.suraname, lo, hi, phrase, rulings };
  document.getElementById('wordTitle').textContent = phrase;
  document.getElementById('wordContext').textContent =
    `سورة ${vd.suraname} — الآية ${vd.verseid}` + (rulings.length ? ' — ' + rulings.map(r => r.itype).join('، ') : '');
  document.getElementById('wordResult').textContent =
    'إخفاء النون الساكنة أو التنوين عند أحد الحروف الخمسة عشر: صفة بين الإظهار والإدغام، بلا شدة، مع بقاء الغنة.' +
    (rulings.length && rulings[0].note ? '\n' + rulings[0].note : '');
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
  clipPlayer.src = '/api/ikhfa/clip?' + p.toString();
  clipPlayer.play().then(() => { status.textContent = ''; })
    .catch(async () => {
      try {
        const r = await fetch('/api/ikhfa/clip?' + p.toString());
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
    const r = await fetch('/api/ikhfa/explain', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        word: phrase, sura: suraname, verse: verseid, question,
        ruling: rulings.map(r => r.itype).join('، '),
      })
    });
    const d = await r.json();
    resultBox.textContent = d.answer || 'تعذّر جلب الإجابة.';
  } catch (e) {
    resultBox.textContent = 'تعذّر الاتصال بالخدمة.';
  }
}

function showHelp() { document.getElementById('helpOverlay').classList.add('show'); }
function hideHelp(e) {
  if (e && e.target.id !== 'helpOverlay') return;
  document.getElementById('helpOverlay').classList.remove('show');
}

(async function init() {
  await loadReaders();
  await loadPage(1);
})();
</script>
</body>
</html>'''

# ══════════════════════════════════════════════════════════════
#  المسارات (Routes)
# ══════════════════════════════════════════════════════════════
@bp.route('/ikhfa')
def index():
    return HTML

@bp.route('/api/ikhfa/page')
def api_page():
    page = request.args.get('page', 1, type=int)
    verses = _load_page(page)
    return jsonify({'page': page, 'verses': verses})

@bp.route('/api/ikhfa/nearest')
def api_nearest():
    page = request.args.get('page', 1, type=int)
    direction = request.args.get('dir', 1, type=int)
    nearest = _find_nearest_page(page, direction)
    return jsonify({'page': nearest})

@bp.route('/api/ikhfa/random')
def api_random():
    return jsonify({'page': _random_page()})

@bp.route('/api/ikhfa/clip')
def api_clip():
    """مقطع صوتي دقيق لكلمة أو مجال كلمات (يتطلب word_audio_helper.py)."""
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
        clip_path, info = prepare_range_clip(AUDIO_BASE_DIR, readers_dict, suraid, verseid, aya_text, lo, hi, reciter)
    else:
        word = request.args.get('word', '')
        clip_path, info = prepare_word_clip(AUDIO_BASE_DIR, readers_dict, suraid, verseid, aya_text, word, reciter)
    if not clip_path:
        return jsonify({'error': info or 'تعذّر تجهيز المقطع.'}), 404
    return send_file(clip_path, mimetype='audio/mpeg')

@bp.route('/api/ikhfa/explain', methods=['POST'])
def api_explain():
    import http.client as _hc
    data     = request.get_json(force=True)
    word     = data.get('word', '')
    sura     = data.get('sura', '')
    verse    = data.get('verse', '')
    question = data.get('question', f'ما حكم إخفاء كلمة {word} في القرآن الكريم؟')
    ruling   = data.get('ruling', '')

    ruling_info = f'\nالحكم المؤكد من قاعدة البيانات: {ruling}' if ruling else ''
    API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

    try:
        system = ("You are an expert in Quran Tajweed specializing in Ikhfa Haqiqi (real concealment) rules. "
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


