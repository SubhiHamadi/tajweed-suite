"""
unified_app.py
══════════════════════════════════════════════════════════════════
التطبيق الموحَّد للسويطة — يجمع كل أحكام التجويد في تطبيق Flask واحد
على منفذ واحد، بدل عشرات التطبيقات المنفصلة. كل حكم مسجَّل كـ Blueprint
مستقل على مساره الخاص (/ikhfa, /idgham, /qlqlah...)، ويشترك الجميع في
نفس اتصال قاعدة البيانات ومسارَي القرّاء/الصوت المشتركين.

هذا أول إصدار يضم ثلاثة أحكام نموذجية (تمثّل الأنماط الثلاثة الموجودة
في السويطة) للتحقق من سلامة آلية الدمج قبل تعميمها على الباقي:
  • bp_ikhfa   — نمط "ملف مستقل واحد" (الأكثر شيوعاً في السويطة)
  • bp_alifat  — نمط "جدول بيانات مخصَّص" (نفس نمط bp_ikhfa هيكلياً)
  • qlqlah     — نمط "عبر وحدة مشتركة" (qlqhnlamat_common.build_app)

باقي الأحكام (٢٢+ حكماً) ستُضاف بنفس الطريقة تباعاً.
"""
import os, sys
from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__)

# ══════════════════════════════════════════════════════════════
#  إعداد مشترك (قاعدة البيانات، القرّاء) — نسخة واحدة يستخدمها الجميع
# ══════════════════════════════════════════════════════════════
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

READER_NAMES = {
    'Aya1Aya' : 'مشاري راشد العفاسي',
    'Aya9Aya' : 'محمد صديق المنشاوي — المعلم',
    'AyaEAya' : '🇬🇧 Ibrahim Walk (English)',
    'mnshawi_moratl' : 'المنشاوي',
}
SKIP = {'AyaAya', 'Husary', 'abdulstar', 'kolon', 'mnshawi'}

@app.route('/api/readers')
def api_readers():
    """مسار قرّاء مشترك واحد يخدم كل الأحكام — بدل تكراره في كل تطبيق
    على حدة. نفس المنطق الأغنى (يميّز قرّاء التلاوة بالآية عن قرّاء
    التلاوة بالسورة) المعتمد أصلاً في qlqhnlamat_common.py."""
    readers = []
    if os.path.isdir(BASE_DIR):
        for f in sorted(os.listdir(BASE_DIR)):
            if f in SKIP:
                continue
            fp = os.path.join(BASE_DIR, f)
            if not os.path.isdir(fp):
                continue
            files = os.listdir(fp)
            aya_mp3s  = [x for x in files if x.endswith('.mp3') and len(x) == 10]
            sura_mp3s = [x for x in files if x.endswith('.mp3') and 6 <= len(x) <= 8 and x.replace('.mp3', '').strip().isdigit()]
            if aya_mp3s:
                readers.append({'id': f, 'label': READER_NAMES.get(f, f), 'mode': 'aya'})
            elif sura_mp3s:
                readers.append({'id': f, 'label': READER_NAMES.get(f, f), 'mode': 'sura'})
    if not readers:
        readers.append({'id': 'Aya1Aya', 'label': 'مشاري راشد العفاسي', 'mode': 'aya'})
    return jsonify(readers)

@app.route('/audio/<reader>/<fname>')
def serve_audio(reader, fname):
    """مسار صوت مشترك واحد — كل الأحكام تستدعيه بنفس الشكل المطلق
    (/audio/...)، فلا حاجة لتعديل أي سطر JavaScript داخل أي تطبيق."""
    d = os.path.join(BASE_DIR, reader)
    if os.path.isdir(d):
        return send_from_directory(d, fname)
    return '', 404

# ══════════════════════════════════════════════════════════════
#  تسجيل الأحكام — كل حكم Blueprint مستقل على مساره الخاص
# ══════════════════════════════════════════════════════════════

# نمط ١: ملف مستقل واحد (bp = Blueprint(...) بداخله)
from bp_ikhfa import bp as bp_ikhfa
app.register_blueprint(bp_ikhfa)

from bp_idgham import bp as bp_idgham
app.register_blueprint(bp_idgham)

from bp_izhar import bp as bp_izhar
app.register_blueprint(bp_izhar)

from bp_iqlab import bp as bp_iqlab
app.register_blueprint(bp_iqlab)

from bp_mim import bp as bp_mim
app.register_blueprint(bp_mim)

from bp_sakt import bp as bp_sakt
app.register_blueprint(bp_sakt)

from bp_raa import bp as bp_raa
app.register_blueprint(bp_raa)

from bp_madfaraq import bp as bp_madfaraq
app.register_blueprint(bp_madfaraq)

from bp_madtmkeeng import bp as bp_madtmkeeng
app.register_blueprint(bp_madtmkeeng)

from bp_lazm import bp as bp_lazm
app.register_blueprint(bp_lazm)

from bp_arth import bp as bp_arth
app.register_blueprint(bp_arth)

from bp_leen import bp as bp_leen
app.register_blueprint(bp_leen)

from bp_mdcon import bp as bp_mdcon
app.register_blueprint(bp_mdcon)

from bp_mdmun import bp as bp_mdmun
app.register_blueprint(bp_mdmun)

from bp_mdsila import bp as bp_mdsila
app.register_blueprint(bp_mdsila)

from bp_mdsoghra import bp as bp_mdsoghra
app.register_blueprint(bp_mdsoghra)

from bp_mdawad import bp as bp_mdawad
app.register_blueprint(bp_mdawad)

from bp_mdbadl import bp as bp_mdbadl
app.register_blueprint(bp_mdbadl)

from bp_quiz import bp as bp_quiz
app.register_blueprint(bp_quiz)

# نمط ٢: جدول بيانات مخصَّص (نفس نمط ملف مستقل هيكلياً)
from bp_alifat import bp as bp_alifat
app.register_blueprint(bp_alifat)

# نمط ٣: عبر وحدة مشتركة (build_app بوضع Blueprint)
from qlqhnlamat_common import build_app as _qlqhn_build
bp_qlqlah = _qlqhn_build(
    ruletype='القلقلة',
    title='أحكام القلقلة في القرآن الكريم',
    subtitle='اضطراب الصوت عند النطق بحرف ساكن من حروف "قطب جد"',
    subtypes=['صغرى', 'كبرى'],
    colors={'صغرى': '#FF7043', 'كبرى': '#FF3D00'},
    help_text={
        'def': 'اضطراب الصوت عند النطق بالحرف الساكن (من حروف "قطب جد") حتى يُسمع له نبرة قوية، سواء أكان السكون أصلياً وسط الكلمة (صغرى) أم عارضاً بسبب الوقف (كبرى).',
        'letters': 'حروف القلقلة: ق ط ب ج د',
        'example': 'صغرى: ﴿يَقْطَعُونَ﴾ — كبرى: الوقوف على ﴿الْأَحَدُ﴾',
    },
    api_prefix='qlq', as_blueprint=True, home_path='/qlqlah',
)
app.register_blueprint(bp_qlqlah)

bp_ghunnah = _qlqhn_build(
    ruletype='الغنة',
    title='أحكام الغنة في القرآن الكريم',
    subtitle='صوت أغنّ من الخيشوم بمقدار حركتين — النون والميم المشددتان',
    subtypes=['نون مشددة', 'ميم مشددة'],
    colors={'نون مشددة': '#00E5FF', 'ميم مشددة': '#00ACC1'},
    help_text={
        'def': 'صوت أغنّ يخرج من الخيشوم (الأنف) بمقدار حركتين، يلازم كل نون أو ميم مشددة أينما وقعتا.',
        'letters': 'حرفا الغنة: ن‌ّ  م‌ّ (مشددتان)',
        'example': '﴿إِنَّ﴾ — ﴿ثُمَّ﴾',
    },
    api_prefix='ghn', as_blueprint=True, home_path='/ghunnah',
)
app.register_blueprint(bp_ghunnah)

bp_lamjalalah = _qlqhn_build(
    ruletype='لام الجلالة',
    title='أحكام لام لفظ الجلالة',
    subtitle='تفخيم/ترقيق لام "الله" و"لِلَّهِ" حسب الحركة السابقة لها',
    subtypes=['مفخمة', 'مرققة'],
    colors={'مفخمة': '#D4A843', 'مرققة': '#CE93D8'},
    help_text={
        'def': 'لام لفظ "الله" تُفخَّم (تُنطق سميكة) إذا سبقها فتح أو ضم، وتُرقَّق (تُنطق رقيقة) إذا سبقها كسر — سواء في "الله" أو في "لِلَّهِ".',
        'letters': 'مثال التفخيم: ﴿قَالَ اللَّهُ﴾ — مثال الترقيق: ﴿بِسْمِ اللَّهِ﴾',
        'example': '﴿لِلَّهِ الْأَمْرُ﴾ — اللام مرققة لأن قبلها كسرة',
    },
    api_prefix='lmj', as_blueprint=True, home_path='/lamjalalah',
)
app.register_blueprint(bp_lamjalalah)

bp_lamat = _qlqhn_build(
    ruletype='اللامات',
    title='اللام الشمسية والقمرية',
    subtitle='لام "أل" التعريف: تُظهر قمرية أو تُدغم شمسية في الحرف التالي',
    subtypes=['شمسية', 'قمرية'],
    colors={'شمسية': '#EF5350', 'قمرية': '#66BB6A'},
    help_text={
        'def': 'لام "أل" التعريف: تُظهر (قمرية) قبل 14 حرفاً فتُنطق ساكنة واضحة، أو تُدغم (شمسية) في 14 حرفاً أخرى فلا تُنطق وتُشدَّد الحرف الذي بعدها.',
        'letters': 'الشمسية: ت ث د ذ ر ز س ش ص ض ط ظ ل ن — القمرية: ء ا ب ج ح خ ع غ ف ق ك م ه و ي',
        'example': 'قمرية: ﴿الْقَمَرِ﴾ — شمسية: ﴿الشَّمْسِ﴾',
    },
    api_prefix='lmt', as_blueprint=True, home_path='/lamat',
)
app.register_blueprint(bp_lamat)

# نمط ٤: إدغام المتماثلين/المتجانسين/المتقاربين (عبر idgham_special_common)
from idgham_special_common import build_app as _idghamsp_build
from idgham_mutajanisayn_web_app import CASES as _MJS_CASES
from idgham_mutaqaribayn_web_app import CASES as _MQR_CASES
from idgham_mutamathilayn_web_app import CASES as _MML_CASES

bp_mjs = _idghamsp_build(
    ruletype='إدغام المتجانسين', title='إدغام المتجانسين في القرآن الكريم',
    subtitle='حرفان اتفقا في المخرج واختلفا في الصفة', cases=_MJS_CASES,
    api_prefix='mjs', as_blueprint=True, home_path='/mutajanisayn',
)
app.register_blueprint(bp_mjs)

bp_mqr = _idghamsp_build(
    ruletype='إدغام المتقاربين', title='إدغام المتقاربين في القرآن الكريم',
    subtitle='حرفان تقاربا في المخرج أو الصفة', cases=_MQR_CASES,
    api_prefix='mqr', as_blueprint=True, home_path='/mutaqaribayn',
)
app.register_blueprint(bp_mqr)

bp_mml = _idghamsp_build(
    ruletype='إدغام المتماثلين', title='إدغام المتماثلين في القرآن الكريم',
    subtitle='حرفان اتفقا مخرجاً وصفة (نفس الحرف مكرراً)', cases=_MML_CASES,
    api_prefix='mml', as_blueprint=True, home_path='/mutamathilayn',
)
app.register_blueprint(bp_mml)

# ══════════════════════════════════════════════════════════════
#  الصفحة الرئيسية — لوحة الأحكام مُصنَّفة في 8 فئات رئيسية (نفس تبويب
#  adriver_app.py الأصلي بالضبط) — كل فئة تحوي حكمًا واحدًا (رابط مباشر)
#  أو عدة أحكام (نافذة فرعية تظهر عند النقر بدل الانتقال فورًا)
# ══════════════════════════════════════════════════════════════
CATEGORIES = [
    {
        'title': 'أحكام النون الساكنة والتنوين', 'icon': '🟡', 'color': '#EF5350',
        'items': [
            {'path': '/ikhfa',  'title': 'الإخفاء الحقيقي'},
            {'path': '/idgham', 'title': 'الإدغام'},
            {'path': '/izhar',  'title': 'الإظهار الحلقي'},
            {'path': '/iqlab',  'title': 'الإقلاب'},
        ],
    },
    {
        'title': 'أحكام المدود القرآنية', 'icon': '🔵', 'color': '#42A5F5',
        'items': [
            {'path': '/lazm',       'title': 'مد اللازم'},
            {'path': '/arth',       'title': 'المد العارض للسكون'},
            {'path': '/leen',       'title': 'مد اللين'},
            {'path': '/mdcon',      'title': 'مد المتصل'},
            {'path': '/mdmun',      'title': 'مد المنفصل'},
            {'path': '/mdsila',     'title': 'مد الصلة الكبرى'},
            {'path': '/mdsoghra',   'title': 'مد الصلة الصغرى'},
            {'path': '/mdawad',     'title': 'مد العوض'},
            {'path': '/mdbadl',     'title': 'مد البدل'},
            {'path': '/madfaraq',   'title': 'مد الفرق'},
            {'path': '/madtmkeeng', 'title': 'مد التمكين'},
        ],
    },
    {
        'title': 'أحكام التفخيم والترقيق', 'icon': '🔴', 'color': '#78909C',
        'items': [{'path': '/raa', 'title': 'أحكام الراء'}],
    },
    {
        'title': 'أحكام الميم الساكنة', 'icon': '⚪', 'color': '#8BC34A',
        'items': [{'path': '/mim', 'title': 'أحكام الميم الساكنة'}],
    },
    {
        'title': 'إدغام المتماثلين والمتجانسين والمتقاربين', 'icon': '🟢', 'color': '#90A4AE',
        'items': [
            {'path': '/mutamathilayn', 'title': 'إدغام المتماثلين'},
            {'path': '/mutajanisayn',  'title': 'إدغام المتجانسين'},
            {'path': '/mutaqaribayn',  'title': 'إدغام المتقاربين'},
        ],
    },
    {
        'title': 'الألفات السبع والسكت', 'icon': '📜', 'color': '#81C784',
        'items': [
            {'path': '/alifat', 'title': 'الألفات السبع'},
            {'path': '/sakt',   'title': 'السكت'},
        ],
    },
    {
        'title': 'القلقلة والغنة واللامات', 'icon': '🟣', 'color': '#66BB6A',
        'items': [
            {'path': '/qlqlah',     'title': 'القلقلة'},
            {'path': '/ghunnah',    'title': 'الغنة'},
            {'path': '/lamjalalah', 'title': 'لام لفظ الجلالة'},
            {'path': '/lamat',      'title': 'اللام الشمسية والقمرية'},
        ],
    },
    {
        'title': 'الاختبار والتدريب', 'icon': '📝', 'color': '#90A4AE',
        'items': [{'path': '/quiz', 'title': 'اختبار شامل'}],
    },
]

import json as _json

HOME_HTML = r'''<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>لوحة أحكام التجويد في القرآن الكريم</title>
<style>
:root { --bg:#020B18; --card:#0D2847; --gold:#D4A843; --gold2:#F0C755; --border:#1A3A5C; --text:#F8F4EE; --muted:#B0BEC5; }
* { box-sizing:border-box; margin:0; padding:0; }
body { font-family:"Traditional Arabic","Noto Naskh Arabic",Arial,sans-serif;
       background:var(--bg); color:var(--text); direction:rtl; min-height:100vh; }
header { background:linear-gradient(135deg,#020B18 0%,#0A2848 50%,#020B18 100%);
         border-bottom:4px solid var(--gold); padding:20px 16px; text-align:center; }
h1 { color:#F0C755; font-size:clamp(18px,5vw,26px); }
.sub { color:#00E5FF; font-size:13px; margin-top:6px; }
.authors { display:flex; gap:10px; justify-content:center; flex-wrap:wrap; margin-top:16px; }
.author-card { display:flex; align-items:center; gap:12px; background:rgba(212,168,67,0.08);
  border:1px solid rgba(212,168,67,0.25); border-radius:10px; padding:8px 18px; font-size:13px; }
.author-logo { width:56px; height:56px; object-fit:contain; border-radius:6px; }
.author-name { color:#F0C755; font-weight:bold; }
.author-info { color:#00E5FF; }
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr));
        gap:18px; padding:30px 20px; max-width:1000px; margin:0 auto; }
.cat-card { display:flex; flex-direction:column; align-items:center; gap:10px;
         background:var(--card); border:2px solid var(--border); border-radius:16px;
         padding:20px 14px; cursor:pointer; transition:border-color .15s, transform .1s; }
.cat-card:hover { transform:translateY(-2px); }
.icon-circle { width:70px; height:70px; border-radius:50%; display:flex; align-items:center;
               justify-content:center; font-size:32px; border:2px solid; }
.cat-title { font-weight:bold; font-size:15px; text-align:center; padding:5px 14px; border-radius:20px; border:1.5px solid; }
.cat-count { font-size:12px; padding:2px 12px; border-radius:20px; background:rgba(0,188,212,0.15); color:#00BCD4; }
.note { text-align:center; color:var(--muted); font-size:12px; padding:0 20px 24px; }

#subOverlay { display:none; position:fixed; inset:0; background:rgba(0,0,0,0.65);
              z-index:2000; align-items:center; justify-content:center; padding:16px; }
#subOverlay.show { display:flex; }
#subModal { background:var(--card); border-radius:16px; padding:20px; max-width:420px; width:100%;
            max-height:80vh; overflow-y:auto; border:2px solid rgba(212,168,67,0.55); }
#subTitle { font-size:17px; font-weight:bold; color:#F0C755; text-align:center; margin-bottom:16px;
            border-bottom:2px solid var(--gold); padding-bottom:10px; }
.sub-link { display:block; background:#0A2040; border:1.5px solid var(--border); border-radius:10px;
            padding:12px 16px; margin-bottom:8px; color:var(--text); text-decoration:none;
            font-weight:bold; transition:border-color .15s; }
.sub-link:hover { border-color:var(--gold); color:#F0C755; }
#subClose { width:100%; margin-top:6px; padding:9px; border:1.5px solid #EF5350; border-radius:10px;
            background:rgba(239,83,80,0.1); cursor:pointer; font-size:14px; color:#EF5350;
            font-family:"Traditional Arabic",Arial; }
</style>
</head>
<body>
<header>
  <h1>📖 لوحة أحكام التجويد في القرآن الكريم</h1>
  <div class="sub">اختر الحكم الذي تريد تعلّمه أو مراجعته</div>
  <div class="authors">
    <div class="author-card"><img class="author-logo" src="/static/logo_alnoor.png" onerror="this.style.display='none'"><span class="author-name">د. صبحي حمادي حمدون</span> — <span class="author-info">جامعة النور، الموصل</span></div>
    <div class="author-card"><img class="author-logo" src="/static/logo_utas.png" onerror="this.style.display='none'"><span class="author-name">د. محمد حميد أحمد</span> — <span class="author-info">جامعة التقنية والعلوم التطبيقية، صحار</span></div>
  </div>
</header>

<div class="grid" id="grid"></div>

<div class="note">✅ الدمج مكتمل — 26 حكمًا تجويديًا بالإضافة إلى الاختبار الشامل، كلها تعمل معًا على هذا الخادم الواحد.</div>

<div id="subOverlay" onclick="closeSub(event)">
  <div id="subModal">
    <div id="subTitle"></div>
    <div id="subLinks"></div>
    <button id="subClose" onclick="closeSub()">✕ إغلاق</button>
  </div>
</div>

<script>
const CATEGORIES = ''' + _json.dumps(CATEGORIES, ensure_ascii=False) + r''';

function buildGrid() {
  document.getElementById('grid').innerHTML = CATEGORIES.map((cat, idx) => `
    <div class="cat-card" style="border-color:${cat.color};" onclick="onCatClick(${idx})">
      <div class="icon-circle" style="border-color:${cat.color};background:${cat.color}22;">${cat.icon}</div>
      <div class="cat-title" style="border-color:${cat.color};color:${cat.color};">${cat.title}</div>
      ${cat.items.length > 1 ? `<div class="cat-count">${cat.items.length} أحكام</div>` : ''}
    </div>`).join('');
}

function onCatClick(idx) {
  const cat = CATEGORIES[idx];
  if (cat.items.length === 1) {
    window.location.href = cat.items[0].path;
    return;
  }
  document.getElementById('subTitle').textContent = cat.title;
  document.getElementById('subLinks').innerHTML = cat.items.map(it =>
    `<a class="sub-link" href="${it.path}">${it.title}</a>`).join('');
  document.getElementById('subOverlay').classList.add('show');
}
function closeSub(e) {
  if (e && e.target.id !== 'subOverlay') return;
  document.getElementById('subOverlay').classList.remove('show');
}

buildGrid();
</script>
</body>
</html>'''

@app.route('/')
def home():
    return HOME_HTML


if __name__ == '__main__':
    import threading, webbrowser
    port = 5000
    url = f'http://localhost:{port}'
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    print(f'التطبيق الموحَّد يعمل على: {url}')
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
