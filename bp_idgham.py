"""
idgham_web_app.py — أحكام الإدغام في القرآن الكريم (نسخة الويب)
نسخة Flask من Idgham_app.py، بنفس هوية md_con_web_app.py وikhfa_web_app.py
البصرية. تنقل بالسورة/الآية (وليس بالصفحة) لأن Idgham_app.py الأصلي
مبني أصلاً على هذا النمط.
يعمل على بورت 5041 (خارج نطاق 5009–5038 المستخدم أصلاً، وخارج 5040
الذي يستخدمه ikhfa_web_app.py).
"""
import os, re, sys, sqlite3, json
from flask import Flask, Blueprint, jsonify, request, send_from_directory, send_file

bp = Blueprint('idgham', __name__)
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
#  ألوان/أيقونات/تعريفات أنواع الإدغام — منقولة حرفياً من Idgham_app.py
# ══════════════════════════════════════════════════════════════
ITYPE_COLORS = {
    'إدغام كامل بلا غنة(تنوين)'          : '#00C853',
    'إدغام كامل بلا غنة(نون ساكنة)'       : '#00E5FF',
    'إدغام ناقص بغنة(تنوين)'             : '#FF9800',
    'إدغام ناقص بغنة(نون ساكنة)'         : '#FFD700',
    'ادغام متقارب القاف + الكاف'          : '#7C4DFF',
    'إدغام متقارب لام وراء'               : '#E040FB',
    'إدغام (شفوي) المثلان الصغير في كلمتين': '#FF4081',
    'إدغام المثلان الصغير في كلمتين '    : '#FF4081',
    'إدغام كامل بلا غنة أن لا'           : '#69F0AE',
}
def get_color(itype):
    for k, v in ITYPE_COLORS.items():
        if k.strip() == (itype or '').strip():
            return v
    return '#F0C755'

ITYPE_ICONS = {
    'إدغام كامل بلا غنة(تنوين)'          : '🟢',
    'إدغام كامل بلا غنة(نون ساكنة)'       : '🔵',
    'إدغام ناقص بغنة(تنوين)'             : '🟠',
    'إدغام ناقص بغنة(نون ساكنة)'         : '🟡',
    'ادغام متقارب القاف + الكاف'          : '🟣',
    'إدغام متقارب لام وراء'               : '🟪',
    'إدغام (شفوي) المثلان الصغير في كلمتين': '🩷',
    'إدغام المثلان الصغير في كلمتين '    : '🩷',
    'إدغام كامل بلا غنة أن لا'           : '🟩',
}
def get_icon(itype):
    for k, v in ITYPE_ICONS.items():
        if k.strip() == (itype or '').strip():
            return v
    return '🔹'

ITYPE_DEFINITIONS = {
    'إدغام كامل بلا غنة(نون ساكنة)':
        'نون ساكنة تليها لام أو راء في أول الكلمة التالية، فتُدغم فيها '
        'إدغاماً كاملاً وتزول الغنة تماماً، مثل: مِن رَّبِّهِمۡ',
    'إدغام كامل بلا غنة(تنوين)':
        'تنوين يليه لام أو راء في أول الكلمة التالية، فيُدغم إدغاماً '
        'كاملاً بلا غنة، مثل: غَفُورٌ رَّحِيمٌ',
    'إدغام ناقص بغنة(نون ساكنة)':
        'نون ساكنة تليها واو أو ياء في أول الكلمة التالية، فتُدغم فيها '
        'إدغاماً ناقصاً مع بقاء صفة الغنة ظاهرة، مثل: مَنۡ يَقُولُ',
    'إدغام ناقص بغنة(تنوين)':
        'تنوين يليه واو أو ياء في أول الكلمة التالية، فيُدغم إدغاماً '
        'ناقصاً مع بقاء الغنة، مثل: هُدًى وَرَحۡمَةٍ',
    'ادغام متقارب القاف + الكاف':
        'إدغام صغير بين القاف والكاف عند تقارب مخرجيهما، إذا سكنت القاف '
        'وجاءت بعدها كاف في أول الكلمة التالية، مثل: أَلَمۡ نَخۡلُقكُّم',
    'إدغام متقارب لام وراء':
        'إدغام صغير بين اللام والراء عند تقارب مخرجيهما، إذا سكنت اللام '
        'وجاءت بعدها راء في أول الكلمة التالية، مثل: قُل رَّبِّ',
    'إدغام (شفوي) المثلان الصغير في كلمتين':
        'إدغام الميم الساكنة في ميم متحركة من كلمة تالية (مثلان: ميم مع '
        'ميم)، فتصبحان ميماً واحدة مشددة بغنة، مثل: لَكُم مَّا',
    'إدغام المثلان الصغير في كلمتين ':
        'إدغام حرفين متماثلين (من نفس المخرج والصفة) عند التقائهما بين '
        'كلمتين، فيُدغم الأول في الثاني ويصيران حرفاً واحداً مشدداً.',
    'إدغام كامل بلا غنة أن لا':
        'حالة خاصة لإدغام كلمة «أَنْ» في «لَا» إدغاماً كاملاً بلا غنة، '
        'مثل: أَن لَّا',
}

_FALLBACK_PALETTE = [
    ('#26C6DA', '🔷'), ('#EC407A', '🔶'), ('#AB47BC', '💠'),
    ('#66BB6A', '🔸'), ('#FFA726', '🔺'), ('#5C6BC0', '🔻'),
    ('#8D6E63', '⬥'),  ('#26A69A', '⬦'),
]
try:
    _c = sqlite3.connect(DB_PATH); _cur = _c.cursor()
    _cur.execute('SELECT DISTINCT itype FROM idghamdirect ORDER BY itype')
    _all_db_types = [r[0] for r in _cur.fetchall()]
    _c.close()
except Exception:
    _all_db_types = []
_pi = 0
for _t in _all_db_types:
    if _t.strip() not in [k.strip() for k in ITYPE_COLORS]:
        _color, _icon = _FALLBACK_PALETTE[_pi % len(_FALLBACK_PALETTE)]
        ITYPE_COLORS[_t] = _color
        ITYPE_ICONS[_t]  = _icon
        _pi += 1
    if _t.strip() not in [k.strip() for k in ITYPE_DEFINITIONS]:
        ITYPE_DEFINITIONS[_t] = ('إدغام صغير عند تجانس مخرجَي حرفين متجاورين '
                                  '(يتفقان في المخرج ويختلفان في الصفة).')

# ══════════════════════════════════════════════════════════════
#  حرف الإدغام — نفس المنطق المضاف لـ Idgham_app.py وidgham_page_common.py
# ══════════════════════════════════════════════════════════════
_IDGHAM_TYPE_LETTERS = {
    'إدغام كامل بلا غنة(نون ساكنة)'       : 'لر',
    'إدغام كامل بلا غنة(تنوين)'          : 'لر',
    'إدغام ناقص بغنة(نون ساكنة)'         : 'وي',
    'إدغام ناقص بغنة(تنوين)'             : 'وي',
    'ادغام متقارب القاف + الكاف'          : 'ك',
    'إدغام متقارب لام وراء'               : 'ر',
    'إدغام (شفوي) المثلان الصغير في كلمتين': 'م',
    'إدغام كامل بلا غنة أن لا'           : 'ل',
}
_IDGHAM_DIACRITICS_RE = re.compile(r'[\u064B-\u0650\u0652-\u065F\u0610-\u061A\u06D6-\u06ED\u0670]')
_SHADDA = '\u0651'

def _strip_diacritics_idgham(s):
    return _IDGHAM_DIACRITICS_RE.sub('', s or '')

def _base_letter_before(text, i):
    j = i - 1
    while j >= 0 and (_IDGHAM_DIACRITICS_RE.match(text[j]) or text[j] == _SHADDA):
        j -= 1
    return text[j] if j >= 0 else ''

def _idgham_letter(klmat, itype):
    text = (klmat or '').strip()
    itype_key = (itype or '').strip()
    candidates = _IDGHAM_TYPE_LETTERS.get(itype_key)
    if candidates:
        for i, ch in enumerate(text):
            if ch == _SHADDA:
                base = _base_letter_before(text, i)
                if base in candidates:
                    return base
    for i, ch in enumerate(text):
        if ch == _SHADDA:
            base = _base_letter_before(text, i)
            if base:
                return base
    words = text.split()
    if len(words) > 1:
        bare = _strip_diacritics_idgham(words[-1])
        return bare[:1] if bare else ''
    return ''

# ══════════════════════════════════════════════════════════════
#  تنظيف نص الآية (نفس قاعدة md_con_web_app.py / ikhfa_web_app.py)
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
    """يبني قاموس (اسم_المجلد → المسار الكامل) لكل قرّاء التلاوة الكاملة
    — يُمرَّر إلى word_audio_helper الذي يحتاجه لتحديد توقيت الكلمة."""
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
#  منطق الآية — منقول من LoadThread في Idgham_app.py دون أي تغيير
#  في الاستعلامات
# ══════════════════════════════════════════════════════════════
def _load_ayah(suraid, verseid, itype_filter=None):
    conn = get_db(); cur = conn.cursor()
    has_filter = itype_filter and itype_filter != 'الكل'
    if has_filter:
        cur.execute('''SELECT klmat,kseq,itype FROM idghamdirect
            WHERE suraid=? AND verseid=? AND itype=? ORDER BY kseq''',
            (suraid, verseid, itype_filter))
    else:
        cur.execute('''SELECT klmat,kseq,itype FROM idghamdirect
            WHERE suraid=? AND verseid=? ORDER BY kseq''',
            (suraid, verseid))
    cases_raw = cur.fetchall()
    cur.execute('SELECT SURANAME, ayahtext FROM mushafnew WHERE SURAID=? AND VERSEID=?',
                (suraid, verseid))
    info = cur.fetchone() or ('', '')
    conn.close()

    cases = []
    for klmat, kseq, itype in cases_raw:
        cases.append({
            'klmat' : (klmat or '').strip(),
            'kseq'  : kseq,
            'itype' : itype,
            'color' : get_color(itype),
            'icon'  : get_icon(itype),
            'letter': _idgham_letter(klmat, itype),
        })
    return {
        'suraid': suraid, 'verseid': verseid,
        'suraname': info[0], 'aya': _clean_aya(info[1]),
        'cases': cases,
    }

def _random_ayah(itype_filter=None):
    conn = get_db(); cur = conn.cursor()
    has_filter = itype_filter and itype_filter != 'الكل'
    if has_filter:
        cur.execute('''SELECT DISTINCT suraid,verseid FROM idghamdirect
            WHERE itype=? ORDER BY RANDOM() LIMIT 1''', (itype_filter,))
    else:
        cur.execute('SELECT DISTINCT suraid,verseid FROM idghamdirect ORDER BY RANDOM() LIMIT 1')
    r = cur.fetchone()
    conn.close()
    return (r[0], r[1]) if r else (1, 1)

# ══════════════════════════════════════════════════════════════
#  الواجهة (HTML/CSS/JS)
# ══════════════════════════════════════════════════════════════
HTML = r'''<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>أحكام الإدغام في القرآن الكريم</title>
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
.btn-random { background:rgba(0,188,212,0.15); color:var(--navy); border:1.5px solid var(--navy); }
.btn-play   { background:rgba(0,200,83,0.15); color:var(--green); border:1.5px solid var(--green); }
.btn-stop   { background:rgba(239,83,80,0.15); color:var(--red); border:1.5px solid var(--red); }
.speed-bar { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.speed-label { font-size:12px; color:var(--gold); font-weight:bold; white-space:nowrap; }
.speed-btn { padding:5px 11px; border-radius:20px; font-size:12px; font-weight:bold;
             border:1.5px solid var(--navy); background:#0A2040; color:var(--navy); cursor:pointer; }
.speed-btn.active { background:var(--navy); color:#020B18; }

.legend { display:flex; gap:6px; padding:8px 14px; flex-wrap:wrap;
          background:var(--bg); border-bottom:1px solid var(--border); align-items:center; }
.legend-item { display:flex; align-items:center; gap:5px; font-size:11px; font-weight:bold;
               padding:3px 9px; border-radius:20px; white-space:nowrap; cursor:pointer; opacity:0.75; }
.legend-item.active { opacity:1; box-shadow:0 0 0 2px currentColor; }

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
             font-size:clamp(16px,4.5vw,20px); font-weight:bold; }

#wordOverlay, .help-overlay, #allCasesOverlay { display:none; position:fixed; top:0;left:0;right:0;bottom:0;
  background:rgba(0,0,0,0.65); z-index:2000; align-items:center; justify-content:center; padding:16px; }
#wordOverlay.show, .help-overlay.show, #allCasesOverlay.show { display:flex; }
#wordModal, .help-modal, .all-cases-modal { background:#0D2847; border-radius:16px; padding:20px; max-width:420px;
  width:100%; max-height:82vh; overflow-y:auto; direction:rtl;
  box-shadow:0 8px 40px rgba(0,0,0,0.6); border:2px solid rgba(212,168,67,0.55); }
.all-cases-modal { max-width:680px; }
.all-cases-modal table { width:100%; }
.btn-showall { background:rgba(212,168,67,0.15); color:var(--gold); border:1.5px solid var(--gold);
               padding:4px 12px; font-size:11px; border-radius:20px; }
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
#wordClose, .help-close { width:100%; margin-top:6px; padding:9px; border:1.5px solid var(--red);
  border-radius:10px; background:rgba(239,83,80,0.1); cursor:pointer; font-size:14px; color:var(--red); }

@media(max-width:480px) { .ctrl-row { flex-direction:column; align-items:stretch; } button, select { width:100%; } }
</style>
</head>
<body>

<header>
  <div class="header-title">أحكام الإدغام في القرآن الكريم</div>
  <div class="header-sub">ناقص، كامل، متقارب، مثلين</div>
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
    <input type="number" id="verseInput" min="1" value="1" style="max-width:80px;">
    <button class="btn-go" onclick="loadAyah()">عرض</button>
    <button class="btn-random" onclick="loadRandom()">🔀 عشوائية</button>
  </div>
  <div class="ctrl-row">
    <span class="ctrl-label">تصفية النوع:</span>
    <select id="selType" onchange="loadAyah()"></select>
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

<div class="info-bar">
  <div class="info-aya" id="infoAya">—</div>
  <div class="cnt-badge" id="infoCount">0 حالة</div>
</div>

<div class="ayah-wrap">
  <div class="ayah-box" id="ayahBox">جارٍ التحميل...</div>
</div>

<div class="table-wrap">
  <div class="table-header" style="display:flex;justify-content:space-between;align-items:center;">
    <span>📋 حالات الإدغام في هذه الآية</span>
    <button class="btn-showall" onclick="showAllCases()">⛶ عرض الكل</button>
  </div>
  <table>
    <thead><tr><th>الكلمات</th><th>نوع الإدغام</th><th>حرف الإدغام</th></tr></thead>
    <tbody id="casesTable"></tbody>
  </table>
</div>

<div id="allCasesOverlay" onclick="closeAllCases(event)">
  <div class="all-cases-modal">
    <div class="table-header" style="margin:-20px -20px 12px;border-radius:16px 16px 0 0;">📋 حالات الإدغام في هذه الآية</div>
    <table>
      <thead><tr><th>الكلمات</th><th>نوع الإدغام</th><th>حرف الإدغام</th></tr></thead>
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
let currentSpeed = 1.0;
let currentAyah  = null;
let casesRowsHtml = '';
const audio = document.getElementById('audioPlayer');

async function loadReaders() {
  const r = await fetch('/api/readers');
  const d = await r.json();
  document.getElementById('selReader').innerHTML =
    d.map(x => `<option value="${x.id}">${x.label}</option>`).join('');
}

async function loadSuras() {
  const r = await fetch('/api/idgham/suras');
  const d = await r.json();
  document.getElementById('selSura').innerHTML =
    d.map(s => `<option value="${s.suraid}">${s.suraid}. ${s.suraname}</option>`).join('');
}

async function loadTypes() {
  const r = await fetch('/api/idgham/types');
  const d = await r.json();
  document.getElementById('selType').innerHTML =
    '<option value="الكل">الكل</option>' +
    d.map(t => `<option value="${t.itype}">${t.icon} ${t.itype.trim()}</option>`).join('');
  document.getElementById('legend').innerHTML =
    d.map(t => `<span class="legend-item" style="background:${t.color}22;color:${t.color};border:2px solid ${t.color};"
      onclick="filterByType('${t.itype.replace(/'/g,"&#39;")}')">${t.icon} ${t.itype.trim()}</span>`).join('');
}

function filterByType(itype) {
  document.getElementById('selType').value = itype;
  loadAyah();
}

function onSuraChange() { document.getElementById('verseInput').value = 1; loadAyah(); }

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

// ── تحديد نطاق حر بالسحب (drag-select) — نفس آلية md_con_web_app.py ──
let currentWords = [];
let currentCaseByIdx = {};
let dragStart = null, dragEnd = null, isDragging = false;
let ayahDragInit = false;

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
  if (!box || ayahDragInit) return;
  ayahDragInit = true;
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
    openSelectionExplain(lo, hi);
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
// قبل المقارنة — نفس الإصلاح المُثبَت في idgham_special_common.py، إذ
// يختلف رسم الكلمة الفعلي في quran.db عن النص المكتوب يدويًا (سكون
// مختلف، وقف ملتصق بلا مسافة، همزة وصل بدل ألف عادية...).
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
  document.getElementById('infoAya').textContent = `سورة ${d.suraname} — الآية ${d.verseid}`;
  document.getElementById('infoCount').textContent = `${d.cases.length} حالة`;

  // نجزّئ الآية كاملةً لكلمات مفردة (لدعم السحب على أي كلمة، محكومة
  // كانت أو عادية)، ونحدّد نطاق كل حالة بمطابقة مجرَّدة من التشكيل
  // بدل مطابقة حرفية هشة قد تفشل مع فروق الرسم العثماني.
  const words = d.aya.split(/\s+/).filter(Boolean);
  const colored = {}, caseByIdx = {};
  d.cases.forEach(c => {
    const [lo, hi] = findWordRange(words, c.klmat);
    if (lo === -1) return;
    for (let i = lo; i <= hi; i++) { colored[i] = c.color; caseByIdx[i] = c; }
  });
  currentWords = words; currentCaseByIdx = caseByIdx;

  document.getElementById('ayahBox').innerHTML = words.map((w, i) =>
    colored[i]
      ? `<span class="word-tok" data-idx="${i}" style="color:${colored[i]};font-weight:bold;">${w}</span>`
      : `<span class="word-tok" data-idx="${i}" style="color:var(--text)">${w}</span>`
  ).join(' ');
  initDragSelect();
  clearSelection();

  casesRowsHtml = d.cases.map((c, idx) => `
    <tr class="case-row" data-caseidx="${idx}">
      <td class="word-cell" style="color:${c.color};">${c.klmat}</td>
      <td>${c.icon} ${c.itype.trim()}</td>
      <td class="word-cell" style="color:${c.color};">${c.letter || '—'}</td>
    </tr>`).join('');
  document.getElementById('casesTable').innerHTML = casesRowsHtml;
  bindCaseRowClicks('casesTable', d);
}

function bindCaseRowClicks(tbodyId, d) {
  document.querySelectorAll(`#${tbodyId} tr.case-row`).forEach(tr => {
    tr.addEventListener('click', () => {
      const c = d.cases[parseInt(tr.dataset.caseidx)];
      const idxs = Object.keys(currentCaseByIdx).map(Number).filter(i => currentCaseByIdx[i] === c);
      if (idxs.length) { openSelectionExplain(Math.min(...idxs), Math.max(...idxs)); closeAllCases(); }
    });
  });
}

function showAllCases() {
  if (!casesRowsHtml || !currentAyah) { return; }
  document.getElementById('allCasesTable').innerHTML = casesRowsHtml;
  bindCaseRowClicks('allCasesTable', currentAyah);
  document.getElementById('allCasesOverlay').classList.add('show');
}
function closeAllCases(e) {
  if (e && e.target.id !== 'allCasesOverlay') return;
  document.getElementById('allCasesOverlay').classList.remove('show');
}

async function loadAyah() {
  const suraid  = document.getElementById('selSura').value;
  const verseid = document.getElementById('verseInput').value || 1;
  const type    = document.getElementById('selType').value || 'الكل';
  const r = await fetch(`/api/idgham/ayah?suraid=${suraid}&verseid=${verseid}&type=${encodeURIComponent(type)}`);
  const d = await r.json();
  renderAyah(d);
}

async function loadRandom() {
  const type = document.getElementById('selType').value || 'الكل';
  const r = await fetch(`/api/idgham/ayah?random=1&type=${encodeURIComponent(type)}`);
  const d = await r.json();
  document.getElementById('selSura').value = d.suraid;
  document.getElementById('verseInput').value = d.verseid;
  renderAyah(d);
}

// يفتح نافذة الشرح + التلاوة الدقيقة لأي مجال كلمات محدَّد (كلمة واحدة
// عبر نقرة بسيطة، أو عدة كلمات عبر السحب)
let currentWordCtx = null;
function openSelectionExplain(lo, hi) {
  if (lo == null || hi == null || !currentAyah) { clearSelection(); return; }
  const phrase = currentWords.slice(lo, hi + 1).join(' ');
  const rulings = [];
  for (let i = lo; i <= hi; i++) if (currentCaseByIdx[i] && !rulings.includes(currentCaseByIdx[i])) rulings.push(currentCaseByIdx[i]);
  const color = rulings[0]?.color || '#D4A843';
  currentWordCtx = { suraid: currentAyah.suraid, verseid: currentAyah.verseid, suraname: currentAyah.suraname,
                      lo, hi, phrase, rulings };
  document.getElementById('wordTitle').textContent = phrase;
  document.getElementById('wordTitle').style.color = color;
  document.getElementById('wordContext').textContent =
    `سورة ${currentAyah.suraname} — الآية ${currentAyah.verseid}` +
    (rulings.length ? ' — ' + rulings.map(r => r.itype.trim() + (r.letter ? ` (حرف الإدغام: ${r.letter})` : '')).join('، ') : '');
  document.getElementById('wordResult').textContent =
    rulings.length ? rulings.map(r => r.definition).filter(Boolean).join(' / ')
                   : 'كلمات عادية بلا حكم إدغام موثّق هنا — يمكنك تشغيل نطقها أو سؤال الذكاء الاصطناعي.';
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
  clipPlayer.src = '/api/idgham/clip?' + p.toString();
  clipPlayer.play().then(() => { status.textContent = ''; })
    .catch(async () => {
      try {
        const r = await fetch('/api/idgham/clip?' + p.toString());
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
    const r = await fetch('/api/idgham/explain', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ word: phrase, sura: suraname, verse: verseid, question,
                              ruling: rulings.map(x => x.itype).join('، ') })
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
  await loadTypes();
  await loadAyah();
})();
</script>
</body>
</html>'''

# ══════════════════════════════════════════════════════════════
#  المسارات (Routes)
# ══════════════════════════════════════════════════════════════
@bp.route('/idgham')
def index():
    return HTML

@bp.route('/api/idgham/suras')
def api_suras():
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute('SELECT DISTINCT SURAID, SURANAME FROM mushafnew ORDER BY SURAID')
        rows = cur.fetchall()
    except Exception:
        rows = []
    conn.close()
    return jsonify([{'suraid': r[0], 'suraname': r[1]} for r in rows])

@bp.route('/api/idgham/types')
def api_types():
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute('SELECT DISTINCT itype FROM idghamdirect ORDER BY itype')
        types = [r[0] for r in cur.fetchall()]
    except Exception:
        types = []
    conn.close()
    return jsonify([{'itype': t, 'color': get_color(t), 'icon': get_icon(t)} for t in types])

@bp.route('/api/idgham/ayah')
def api_ayah():
    itype = request.args.get('type', 'الكل')
    if request.args.get('random'):
        suraid, verseid = _random_ayah(itype)
    else:
        suraid  = request.args.get('suraid', 1, type=int)
        verseid = request.args.get('verseid', 1, type=int)
    d = _load_ayah(suraid, verseid, itype)
    for c in d['cases']:
        c['definition'] = ITYPE_DEFINITIONS.get(c['itype'].strip(), '')
    return jsonify(d)

@bp.route('/api/idgham/clip')
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

@bp.route('/api/idgham/explain', methods=['POST'])
def api_explain():
    import http.client as _hc
    data     = request.get_json(force=True)
    word     = data.get('word', '')
    sura     = data.get('sura', '')
    verse    = data.get('verse', '')
    question = data.get('question', f'ما حكم إدغام كلمتي {word} في القرآن الكريم؟')
    ruling   = data.get('ruling', '')

    ruling_info = f'\nالحكم المؤكد من قاعدة البيانات: {ruling}' if ruling else ''
    API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

    try:
        system = ("You are an expert in Quran Tajweed specializing in Idgham (assimilation) rules. "
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


