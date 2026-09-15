"""
tajweed_quiz_unified.py — التدريب والاختبار الشامل لكل أحكام التجويد
نسخة موسَّعة من tajweed_quiz_app.py (النون الساكنة والتنوين فقط)
تضيف: الراء، الإقلاب، المد اللازم، الميم الساكنة، البدل، اللين،
العارض للسكون — كأحكام تدريب إضافية عبر قائمة منسدلة جديدة.
يعمل على بورت 5002
"""
import os, sqlite3, json, random
from flask import Flask, Blueprint, jsonify, request

bp = Blueprint('quiz', __name__)
import sys
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# على Render (أو أي استضافة تستخدم قرصًا دائمًا منفصلاً)، يكون
# quran.db ومجلدات الصوت موجودة على /data بدل مجلد الكود نفسه —
# نُحوّل BASE_DIR إليه تلقائيًا عند توفره، فتستفيد كل عمليات البحث
# عن قاعدة البيانات ومجلدات القرّاء أدناه دون أي تعديل آخر.
if os.path.isdir('/var/data') and os.path.exists('/var/data/quran.db'):
    BASE_DIR = '/var/data'

DB_PATH = os.path.join(BASE_DIR, 'quran.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ── دعم القراء الأربعة (نطق دقيق للكلمة/العبارة عبر السحب + قائمة
# قراء لتشغيل الآية كاملة) — يعمل التطبيق طبيعياً بدونه، وفقط ميزتا
# التحديد بالسحب واختيار القارئ تُعطَّلان إن تعذّر الاستيراد ──
try:
    from word_audio_helper import prepare_word_clip, prepare_range_clip
    _WORD_AUDIO_OK = True
except Exception:
    _WORD_AUDIO_OK = False

READER_NAMES = {
    'Aya1Aya' : 'مشاري راشد العفاسي',
    'Aya9Aya' : 'محمد صديق المنشاوي — المعلم',
}
SKIP = {'AyaAya','Husary','abdulstar','kolon','mnshawi'}

def _get_readers_dict():
    """يفحص BASE_DIR ويُرجع {اسم_المجلد: مساره_الكامل} لكل مجلد يحتوي
    ملفات mp3 فعلياً بنمط SSSVVV (6 أرقام) — يُستخدم لكل من قائمة تشغيل
    الآية كاملة (استمع) ولـ word_audio_helper (النطق الدقيق بالسحب)."""
    d = {}
    if os.path.isdir(BASE_DIR):
        for f in os.listdir(BASE_DIR):
            if f in SKIP: continue
            fp = os.path.join(BASE_DIR, f)
            if not os.path.isdir(fp): continue
            files = os.listdir(fp)
            has_mp3 = any(x.endswith('.mp3') and len(x.replace('.mp3','')) == 6
                          and x.replace('.mp3','').isdigit() for x in files)
            if has_mp3:
                d[f] = fp
    return d

def get_color(itype):
    if 'إدغام' in (itype or ''): return '#66BB6A'
    if 'إظهار' in (itype or ''): return '#42A5F5'
    if 'إقلاب' in (itype or ''): return '#BA68C8'
    if 'إخفاء' in (itype or ''): return '#FF4081'
    return '#42A5F5'

def get_detail(itype, klma2):
    HARAKAT = set('\u064B\u064C\u064D\u064E\u064F\u0650\u0651\u0652\u06D6\u06E1\u0640')
    if 'رل' in (itype or ''):
        first = next((c for c in (klma2 or '') if '\u0621'<=c<='\u06FF' and c not in HARAKAT), '')
        if first == '\u0631': return 'إدغام بلا غنة — راء'
        if first == '\u0644': return 'إدغام بلا غنة — لام'
        return 'إدغام بلا غنة'
    if 'ينمو' in (itype or ''): return 'إدغام بغنة'
    if 'إظهار' in (itype or ''): return 'إظهار حلقي'
    if 'إقلاب' in (itype or ''): return 'إقلاب'
    if 'إخفاء' in (itype or ''): return 'إخفاء'
    return itype or ''


# ══════════════════════════════════════════════════════════════
#  أحكام التدريب الإضافية (8 أحكام) — كل دالة تُرجع نفس الشكل الموحَّد:
#  None (لا توجد حالة) أو dict فيه: klma1, klma2, suraid, verseid,
#  suraname, ayahtext, correct, choices, explanation, color
# ══════════════════════════════════════════════════════════════

EXTRA_RULES = {
    'الراء'              : {'icon':'🔴', 'label':'تدريب: أحكام الراء'},
    'الإقلاب'            : {'icon':'🟣', 'label':'تدريب: الإقلاب (مستقل)'},
    'المد اللازم'         : {'icon':'🟤', 'label':'تدريب: المد اللازم'},
    'الميم الساكنة'       : {'icon':'⚪', 'label':'تدريب: الميم الساكنة'},
    'مد البدل'           : {'icon':'🟠', 'label':'تدريب: مد البدل'},
    'مد اللين'           : {'icon':'🟢', 'label':'تدريب: مد اللين'},
    'المد العارض للسكون'  : {'icon':'🔵', 'label':'تدريب: المد العارض للسكون'},
}

def _norm_ar(s):
    """يطبّع النص العربي: يحذف التطويل والمسافات الزائدة بين الحروف"""
    if not s: return ''
    return s.replace('ـ', '').strip()


def fetch_raa(cur, suraid):
    """أحكام الراء — 3 اختيارات ثابتة: ترقيق / تفخيم / جواز الوجهين"""
    params, sql = [], '''SELECT klma, suraid, verseid, hokm
                          FROM raa_rules WHERE 1=1'''
    if suraid:
        sql += ' AND suraid=?'; params.append(suraid)
    sql += ' ORDER BY RANDOM() LIMIT 1'
    cur.execute(sql, params)
    row = cur.fetchone()
    if not row: return None
    klma, sid, vid, hokm = row
    hokm = _norm_ar(hokm)
    correct = hokm  # القيمة مطبَّعة بلا تطويل
    choices = ['ترقيق', 'تفخيم', 'جواز الوجهين']
    if correct not in choices:
        correct = choices[0]  # احتياط أمان لو وُجدت قيمة غير متوقعة
    cur.execute('SELECT SURANAME, ayahtext FROM mushafnew WHERE SURAID=? AND VERSEID=?', (sid, vid))
    info = cur.fetchone()
    suraname = info[0] if info else ''
    ayahtext = (info[1] or '') if info else ''
    return {
        'klma1': klma, 'klma2': '', 'suraid': sid, 'verseid': vid,
        'suraname': suraname, 'ayahtext': ayahtext,
        'correct': correct, 'choices': choices,
        'explanation': f'الكلمة «{klma}»: حكم الراء هنا = {correct}.',
        'color': '#EF5350',
    }


def fetch_iqlab(cur, suraid):
    """الإقلاب المستقل (iqlab_rules) — اختيارات: إقلاب مقابل 3 أحكام أخرى"""
    params, sql = [], '''SELECT klma, suraid, verseid
                          FROM iqlab_rules WHERE 1=1'''
    if suraid:
        sql += ' AND suraid=?'; params.append(suraid)
    sql += ' ORDER BY RANDOM() LIMIT 1'
    cur.execute(sql, params)
    row = cur.fetchone()
    if not row: return None
    klma, sid, vid = row
    correct = 'إقلاب'
    choices = ['إقلاب', 'إخفاء', 'إظهار حلقي', 'إدغام بغنة']
    cur.execute('SELECT SURANAME, ayahtext FROM mushafnew WHERE SURAID=? AND VERSEID=?', (sid, vid))
    info = cur.fetchone()
    suraname = info[0] if info else ''
    ayahtext = (info[1] or '') if info else ''
    return {
        'klma1': klma, 'klma2': '', 'suraid': sid, 'verseid': vid,
        'suraname': suraname, 'ayahtext': ayahtext,
        'correct': correct, 'choices': choices,
        'explanation': f'الكلمة «{klma}»: نون ساكنة/تنوين قبل الباء → تُقلب ميماً مخفاة مع الغنة.',
        'color': '#BA68C8',
    }


def fetch_madd(cur, suraid):
    """المد اللازم — 4 أنواع (كلمي/حرفي × مثقل/مخفف)"""
    params, sql = [], '''SELECT WORD, SURAID, VERSEID, SURANAME, AYAH_TEXT, MADD_TYPE
                          FROM MADD_RULES WHERE 1=1'''
    if suraid:
        sql += ' AND SURAID=?'; params.append(suraid)
    sql += ' ORDER BY RANDOM() LIMIT 1'
    cur.execute(sql, params)
    row = cur.fetchone()
    if not row: return None
    word, sid, vid, suraname, ayahtext, madd_type = row
    correct = _norm_ar(madd_type)
    pool = ['لازم كلمي مثقل', 'لازم حرفي مثقل', 'لازم كلمي مخفف', 'لازم حرفي مخفف']
    choices = [correct] + random.sample([c for c in pool if c != correct], 3)
    random.shuffle(choices)
    return {
        'klma1': word, 'klma2': '', 'suraid': sid, 'verseid': vid,
        'suraname': suraname, 'ayahtext': ayahtext or '',
        'correct': correct, 'choices': choices,
        'explanation': f'الكلمة «{word}»: نوع المد اللازم هنا = {correct}.',
        'color': '#A1887F',
    }


def fetch_mim(cur, suraid):
    """الميم الساكنة — 3 أنواع: إخفاء شفوي/إدغام شفوي/إظهار شفوي"""
    params, sql = [], '''SELECT klma1, klma2, suraid, verseid, suraname, aya_text, rule_type
                          FROM mim_rules WHERE 1=1'''
    if suraid:
        sql += ' AND suraid=?'; params.append(suraid)
    sql += ' ORDER BY RANDOM() LIMIT 1'
    cur.execute(sql, params)
    row = cur.fetchone()
    if not row: return None
    klma1, klma2, sid, vid, suraname, ayahtext, rule_type = row
    correct = _norm_ar(rule_type)
    pool = ['إخفاء شفوي', 'إدغام شفوي', 'إظهار شفوي']
    choices = pool[:]  # 3 فقط، لا حاجة لاختيار عشوائي إضافي
    random.shuffle(choices)
    klma2 = (klma2 or '').strip()
    desc = f'«{klma1}» ثم «{klma2}»' if klma2 else f'«{klma1}»'
    return {
        'klma1': klma1, 'klma2': klma2, 'suraid': sid, 'verseid': vid,
        'suraname': suraname, 'ayahtext': ayahtext or '',
        'correct': correct, 'choices': choices,
        'explanation': f'الكلمة {desc}: حكم الميم الساكنة هنا = {correct}.',
        'color': '#78909C',
    }


def fetch_simple_table(cur, suraid, table, hokm_label, color):
    """دالة عامة للجداول البسيطة بلا حقل نوع (md_badl / md_leen / lastword)
    كل صف فيها هو نفس الحكم بالتعريف، فلا حاجة لاختيارات متعددة حقيقية —
    نعرض السؤال كـ'صحيح/خطأ' (هل هذا حكم Y؟) ضد 3 أحكام أخرى عشوائية."""
    params, sql = [], f'SELECT klmahr, suraid, verseid, suraname FROM {table} WHERE 1=1'
    if suraid:
        sql += ' AND suraid=?'; params.append(suraid)
    sql += ' ORDER BY RANDOM() LIMIT 1'
    cur.execute(sql, params)
    row = cur.fetchone()
    if not row: return None
    klma, sid, vid, suraname = row
    cur.execute('SELECT ayahtext FROM mushafnew WHERE SURAID=? AND VERSEID=?', (sid, vid))
    info = cur.fetchone()
    ayahtext = (info[0] or '') if info else ''
    other_rules = ['مد بدل', 'مد لين', 'مد عارض للسكون', 'مد طبيعي']
    correct = hokm_label
    choices = [correct] + random.sample([c for c in other_rules if c != correct], 3)
    random.shuffle(choices)
    return {
        'klma1': klma, 'klma2': '', 'suraid': sid, 'verseid': vid,
        'suraname': suraname or '', 'ayahtext': ayahtext,
        'correct': correct, 'choices': choices,
        'explanation': f'الكلمة «{klma}»: حكمها هنا = {correct}.',
        'color': color,
    }


def fetch_badl(cur, suraid):
    return fetch_simple_table(cur, suraid, 'md_badl', 'مد بدل', '#FFB74D')

def fetch_leen(cur, suraid):
    return fetch_simple_table(cur, suraid, 'md_leen', 'مد لين', '#9CCC65')

def fetch_lastword(cur, suraid):
    return fetch_simple_table(cur, suraid, 'lastword', 'مد عارض للسكون', '#4FC3F7')


EXTRA_FETCHERS = {
    'الراء': fetch_raa,
    'الإقلاب': fetch_iqlab,
    'المد اللازم': fetch_madd,
    'الميم الساكنة': fetch_mim,
    'مد البدل': fetch_badl,
    'مد اللين': fetch_leen,
    'المد العارض للسكون': fetch_lastword,
}



HTML = '''<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>التدريب والاختبار — أحكام التجويد</title>
<style>
:root {
  --navy:#00BCD4; --navy2:rgba(0,188,212,0.15); --gold:#D4A843; --gold2:#F0C755;
  --green:#00C853; --green2:rgba(0,200,83,0.15); --red:#EF5350; --red2:rgba(239,83,80,0.15);
  --purple:#BA68C8; --bg:#020B18; --card:#0D2847; --border:#1A3A5C;
  --text:#F8F4EE; --muted:#B0BEC5;
}
* { box-sizing:border-box; margin:0; padding:0; }
html { color-scheme: dark; }
body { font-family:"Traditional Arabic","Noto Naskh Arabic",Arial,sans-serif;
       background:var(--bg); color:var(--text); direction:rtl; min-height:100vh; }

header { background:linear-gradient(135deg,#020B18 0%,#0A2848 50%,#020B18 100%);
         border-bottom:4px solid var(--gold); padding:14px 16px; text-align:center;
         box-shadow:0 2px 8px rgba(212,168,67,0.15); }
.header-title { font-size:clamp(16px,5vw,24px); font-weight:bold; color:#F0C755;
                text-shadow:0 0 12px rgba(212,168,67,0.5); margin-bottom:4px; }
.header-sub { font-size:13px; color:#00E5FF; }

/* ── شاشة الإدخال ── */
.entry-screen { max-width:480px; margin:40px auto; padding:0 16px; }
.entry-card { background:var(--card); border:3px solid var(--gold); border-radius:16px;
              padding:28px; text-align:center; box-shadow:0 4px 16px rgba(200,150,10,0.15); }
.entry-title { font-size:22px; font-weight:bold; color:var(--navy); margin-bottom:8px; }
.entry-sub { font-size:14px; color:var(--muted); margin-bottom:24px; }
.entry-label { font-size:14px; font-weight:bold; color:var(--text); margin-bottom:8px; display:block; text-align:right; }
.entry-input { width:100%; border:2px solid var(--border); border-radius:10px;
               padding:12px 14px; font-family:"Traditional Arabic",Arial;
               font-size:16px; direction:rtl; margin-bottom:16px;
               background:#0A2040; color:var(--text); }
.entry-input:focus { border-color:var(--navy); outline:none; }
.entry-select { width:100%; border:2px solid var(--border); border-radius:10px;
                padding:12px 14px; font-family:"Traditional Arabic",Arial;
                font-size:15px; direction:rtl; margin-bottom:20px;
                background:#0A2040; color:var(--text); appearance:none; cursor:pointer;
                color-scheme: dark; }
.entry-select option { background:#0A2040; color:var(--text); }
.btn-start { width:100%; padding:14px; background:var(--navy); color:#fff;
             border:none; border-radius:12px; font-size:18px; font-weight:bold;
             cursor:pointer; font-family:"Traditional Arabic",Arial; }
.btn-start:active { transform:scale(0.98); }

/* ── شريط أيقونات اختيار نوع الحكم ── */
.type-grid { display:flex; gap:8px; flex-wrap:wrap; justify-content:center; margin-bottom:20px; }
.type-icon { flex:1 1 auto; min-width:90px; padding:10px 6px; border-radius:12px;
             border:2px solid var(--border); background:#0A2040; cursor:pointer;
             text-align:center; transition:all .15s; user-select:none; }
.type-icon:hover { transform:translateY(-2px); }
.type-icon .ti-dot { font-size:20px; display:block; margin-bottom:2px; }
.type-icon .ti-label { font-size:11px; font-weight:bold; color:var(--text); }
.type-icon.selected { box-shadow:0 0 0 2px currentColor; }
.type-icon.t-all     { border-color:var(--purple); color:var(--purple); }
.type-icon.t-ikhfa   { border-color:#D4A843; color:#D4A843; }
.type-icon.t-iqlab   { border-color:#BA68C8; color:#BA68C8; }
.type-icon.t-izhar   { border-color:#42A5F5; color:#42A5F5; }
.type-icon.t-idgham1 { border-color:#66BB6A; color:#66BB6A; }
.type-icon.t-idgham2 { border-color:#81C784; color:#81C784; }

/* ── شريط النقاط ── */
.score-bar { display:flex; gap:10px; justify-content:center; padding:10px;
             background:var(--card); border-bottom:1px solid var(--border); flex-wrap:wrap; }
.score-item { text-align:center; padding:5px 14px; border-radius:10px; }
.score-num { font-size:20px; font-weight:bold; }
.score-label { font-size:11px; color:var(--muted); }
.s-correct { background:var(--green2); color:var(--green); border:1px solid var(--green); }
.s-wrong   { background:var(--red2);   color:var(--red);   border:1px solid var(--red); }
.s-total   { background:var(--navy2);  color:var(--navy);  border:1px solid var(--navy); }
.s-level   { background:rgba(212,168,67,0.15); color:var(--gold2); border:1px solid var(--border); }
.s-pct     { background:rgba(186,104,200,0.15); color:var(--purple); border:1px solid var(--purple); }

.quiz-wrap { max-width:640px; margin:14px auto; padding:0 12px 24px; }
.progress { height:6px; background:var(--border); border-radius:3px; margin-bottom:14px; overflow:hidden; }
.progress-bar { height:100%; background:var(--navy); border-radius:3px; transition:width .3s; }

.ayah-card { background:var(--card); border:3px solid var(--gold); border-radius:14px;
             padding:18px; margin-bottom:14px; box-shadow:0 2px 8px rgba(200,150,10,0.12); }
.ayah-label { font-size:12px; color:var(--muted); margin-bottom:10px; display:flex; align-items:center; gap:8px; }
.ayah-text  { font-family:"KFGQPC_HAFS_Uthmanic_Script_H","Traditional Arabic";
              font-size:clamp(20px,6vw,28px); line-height:270%; text-align:right; }
.question-text { font-size:16px; font-weight:bold; color:var(--navy); text-align:center; margin-bottom:14px; }

.choices { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:14px; }
.choice-btn { padding:12px 10px; border-radius:12px; border:2px solid var(--border);
              background:#0A2040; font-family:"Traditional Arabic",Arial;
              font-size:15px; font-weight:bold; cursor:pointer; transition:all .15s; color:var(--text); }
.choice-btn:hover:not(:disabled) { background:var(--navy2); border-color:var(--navy); }
.choice-btn.correct { background:var(--green2); border-color:var(--green); color:var(--green); }
.choice-btn.wrong   { background:var(--red2);   border-color:var(--red);   color:var(--red); }
.choice-btn:disabled { cursor:not-allowed; }

.feedback { background:var(--navy2); border:1px solid var(--navy); border-radius:12px;
            padding:14px; font-size:14px; line-height:185%; margin-bottom:12px; display:none; }
.feedback.show { display:block; }
.feedback.correct-fb { background:var(--green2); border-color:var(--green); }
.feedback.wrong-fb   { background:var(--red2);   border-color:var(--red); }

.btn-row { display:flex; gap:8px; }
.btn-next { flex:1; padding:12px; background:var(--navy); color:#fff; border:none;
            border-radius:12px; font-size:15px; font-weight:bold; cursor:pointer;
            font-family:"Traditional Arabic",Arial; display:none; }
.btn-next.show { display:block; }
.btn-finish { flex:1; padding:12px; background:var(--red); color:#fff; border:none;
              border-radius:12px; font-size:15px; font-weight:bold; cursor:pointer;
              font-family:"Traditional Arabic",Arial; display:none; }
.btn-finish.show { display:block; }
.btn-skip { width:100%; padding:9px; background:rgba(212,168,67,0.15); color:var(--gold2);
            border:2px solid var(--border); border-radius:12px; font-size:13px;
            font-weight:bold; cursor:pointer; font-family:"Traditional Arabic",Arial; margin-top:8px; }
.level-badge { display:inline-block; padding:2px 10px; border-radius:20px; font-size:11px; font-weight:bold; }
.level-1 { background:rgba(66,165,245,0.15); color:#42A5F5; border:1px solid #42A5F5; }
.level-2 { background:rgba(129,199,132,0.15); color:#81C784; border:1px solid #81C784; }
.level-3 { background:rgba(255,167,38,0.15); color:#FFA726; border:1px solid #FFA726; }
.quiz-word-tip { position:relative; cursor:help; }
.quiz-word-tip .tip-box {
  display:none; position:absolute; bottom:120%; right:50%; transform:translateX(50%);
  background:#0D2847; color:#F0C755; padding:12px 16px; border-radius:10px; border:1px solid var(--gold);
  font-size:14px; line-height:180%; z-index:100;
  font-family:"Traditional Arabic",Arial; min-width:240px; max-width:340px;
  white-space:normal; text-align:right; box-shadow:0 4px 12px rgba(0,0,0,0.3);
  border:1px solid var(--gold);
  /* منع اختفاء المربع عند التنقل للأزرار */
  padding-bottom:20px;
}
.quiz-word-tip .tip-box::after {
  content:''; position:absolute; top:100%; right:50%; transform:translateX(50%);
  border:8px solid transparent; border-top-color:#0D2847;
}
/* المربع يبقى ظاهراً عند hover على المحتوى الداخلي */
.quiz-word-tip:hover .tip-box,
.quiz-word-tip .tip-box:hover { display:block; }
.tip-lang-row { display:flex; gap:6px; margin-bottom:8px; }
.tip-lang-btn { padding:3px 12px; border-radius:20px; font-size:12px; cursor:pointer;
                border:1px solid var(--gold); background:transparent; color:#FFF8DC;
                font-family:"Traditional Arabic",Arial; }
.tip-lang-btn.active { background:var(--gold); color:#020B18; }
.tip-text { font-size:14px; line-height:185%; }
             margin-top:12px; padding-top:10px; border-top:1px solid var(--border); }
.btn-listen { background:var(--green2); color:var(--green); border:1.5px solid var(--green);
              border-radius:8px; padding:6px 14px; font-size:13px; font-weight:bold;
              cursor:pointer; font-family:"Traditional Arabic",Arial; }
.btn-stop-q { background:var(--red2); color:var(--red); border:1.5px solid var(--red);
              border-radius:8px; padding:6px 10px; font-size:13px; cursor:pointer; }
.speed-label-q { font-size:12px; color:var(--muted); font-weight:bold; }
.spd-btn { padding:4px 10px; border-radius:20px; font-size:12px; font-weight:bold;
           border:1.5px solid var(--border); background:#0A2040; color:var(--muted);
           cursor:pointer; transition:all .15s; }
.spd-btn.active { background:var(--navy); color:#020B18; border-color:var(--navy); }

/* ── قائمة اختيار القارئ (لتشغيل الآية كاملة) ── */
.reader-select { padding:5px 10px; border-radius:8px; font-size:12px;
                  border:1.5px solid var(--border); background:#0A2040; color:var(--text);
                  font-family:"Traditional Arabic",Arial; cursor:pointer; color-scheme: dark; }
.reader-select option { background:#0A2040; color:var(--text); }

/* ── التحديد بالسحب على نص الآية + نافذة النطق الدقيق ── */
.ayah-text .drag-word { cursor:pointer; border-radius:4px; padding:0 2px; }
.ayah-text .drag-word.dragging { background:rgba(212,168,67,0.4); }
.clip-overlay { position:fixed; inset:0; background:rgba(0,0,0,0.45); z-index:200;
                 display:none; align-items:center; justify-content:center; }
.clip-overlay.show { display:flex; }
.clip-popup { background:var(--card); border:2px solid var(--gold); border-radius:16px;
              padding:20px; max-width:340px; width:88%; text-align:center;
              box-shadow:0 8px 28px rgba(0,0,0,0.35); }
.clip-popup-phrase { font-family:"KFGQPC_HAFS_Uthmanic_Script_H","Traditional Arabic";
                       font-size:22px; color:var(--navy); margin-bottom:14px; line-height:180%; }
.clip-reciter-btn { display:block; width:100%; margin-bottom:8px; padding:10px;
                     border-radius:10px; border:1.5px solid var(--green); background:var(--green2);
                     color:var(--green); font-family:"Traditional Arabic",Arial; font-size:14px;
                     font-weight:bold; cursor:pointer; }
.clip-reciter-btn:hover { background:var(--green); color:#020B18; }
.clip-status { font-size:12px; color:var(--muted); min-height:18px; margin:6px 0; }
.clip-close-btn { width:100%; padding:9px; background:var(--red2); color:var(--red);
                   border:1.5px solid var(--red); border-radius:10px; font-size:13px;
                   font-weight:bold; cursor:pointer; font-family:"Traditional Arabic",Arial;
                   margin-top:6px; }

/* ── شاشة النتيجة ── */
.result-screen { max-width:640px; margin:20px auto; padding:0 12px 30px; display:none; }
.result-card { background:var(--card); border:3px solid var(--gold); border-radius:16px;
               padding:28px; text-align:center; box-shadow:0 4px 16px rgba(200,150,10,0.2);
               position:relative; overflow:hidden; }
.result-bg { position:absolute; top:0;left:0;right:0;bottom:0; opacity:0.35;
             background-image:url("data:image/jpeg;base64,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");
             background-size:50%; background-position:center center; background-repeat:no-repeat; z-index:0; }
.result-content { position:relative; z-index:1; }
.result-border { border:2px solid var(--gold); border-radius:12px; padding:20px;
                 background:rgba(255,253,245,0.65); }
.result-logo { font-size:40px; margin-bottom:8px; }
.result-univ { font-size:13px; color:var(--navy); font-weight:bold; margin-bottom:16px;
               border-bottom:2px solid var(--gold); padding-bottom:10px; }
.result-cert-title { font-size:28px; font-weight:bold; color:var(--navy);
                     margin-bottom:6px; letter-spacing:0.5px; }
.result-name { font-size:24px; font-weight:bold; color:var(--navy); margin-bottom:4px; }
.result-date { font-size:13px; color:var(--muted); margin-bottom:16px; }
.result-pct  { font-size:64px; font-weight:bold; margin:8px 0; }
.result-grade { font-size:22px; font-weight:bold; margin-bottom:16px; padding:8px 24px;
                border-radius:30px; display:inline-block; }
.grade-a { background:var(--green2); color:var(--green); border:2px solid var(--green); }
.grade-b { background:var(--navy2);  color:var(--navy);  border:2px solid var(--navy); }
.grade-c { background:rgba(212,168,67,0.15); color:var(--gold2); border:2px solid var(--border); }
.grade-d { background:var(--red2);   color:var(--red);   border:2px solid var(--red); }
.result-stats { display:flex; gap:12px; justify-content:center; flex-wrap:wrap; margin:14px 0; }
.result-stat { padding:8px 18px; border-radius:10px; text-align:center; }
.result-stat-num { font-size:24px; font-weight:bold; }
.result-stat-lbl { font-size:12px; color:var(--muted); }
.result-sig { margin-top:20px; padding-top:14px; border-top:2px solid var(--gold);
              display:flex; justify-content:space-around; flex-wrap:wrap; gap:16px; }
.sig-block { text-align:center; }
.sig-space { height:55px; width:180px; margin:0 auto 6px; }
.sig-name  { font-size:14px; font-weight:bold; color:var(--navy); }
.sig-info  { font-size:11px; color:var(--muted); }
.result-quran { font-size:20px; color:var(--navy); margin-top:14px;
                font-family:"KFGQPC_HAFS_Uthmanic_Script_H","Traditional Arabic";
                font-weight:bold; letter-spacing:1px; }
.btn-print  { width:100%; margin-top:14px; padding:12px; background:var(--navy); color:#fff;
              border:none; border-radius:12px; font-size:15px; font-weight:bold;
              cursor:pointer; font-family:"Traditional Arabic",Arial; }
.btn-retry  { width:100%; margin-top:8px; padding:12px; background:rgba(212,168,67,0.15); color:var(--gold2);
              border:2px solid var(--border); border-radius:12px; font-size:15px; font-weight:bold;
              cursor:pointer; font-family:"Traditional Arabic",Arial; }

@media print {
  header, .score-bar, .quiz-wrap, .btn-print, .btn-retry,
  #entryScreen, #quizScreen { display:none !important; }
  .result-screen { display:block !important; margin:0; padding:10px; }
  .result-card { border:2px solid #C8960A; box-shadow:none; }
  .result-bg { opacity:0.05 !important; -webkit-print-color-adjust:exact; print-color-adjust:exact; }
}
@media(max-width:480px) { .choices { grid-template-columns:1fr; } }
</style>
</head>
<body>

<header>
  <div class="header-title">📝 التدريب والاختبار</div>
  <div class="header-sub">أحكام النون الساكنة والتنوين</div>
</header>

<!-- شاشة الإدخال -->
<div class="entry-screen" id="entryScreen">
  <div class="entry-card">
    <div class="entry-title">📝 بيانات المتدرّب/المختبَر</div>
    <div class="entry-sub">أدخل بياناتك، ثم اختر تدريباً على حكم محدد أو اختباراً شاملاً</div>
    <label class="entry-label">الاسم الكامل:</label>
    <input class="entry-input" id="studentName" placeholder="أدخل اسمك الكامل هنا..." type="text">
    <label class="entry-label">الجنس:</label>
    <select class="entry-select" id="studentGender">
      <option value="ذكر">ذكر</option>
      <option value="أنثى">أنثى</option>
    </select>
    <label class="entry-label">تاريخ الميلاد:</label>
    <input class="entry-input" id="studentDob" placeholder="مثال: 1990/01/15" type="date">
    <label class="entry-label">البريد الإلكتروني أو رقم الهاتف:</label>
    <input class="entry-input" id="studentContact" placeholder="example@email.com أو 07xxxxxxxx" type="text">

    <label class="entry-label">اختر نوع الجلسة:</label>
    <div class="type-grid" id="typeGrid">
      <div class="type-icon t-all selected" data-type="شامل">
        <span class="ti-dot">📝</span><span class="ti-label">اختبار (شامل)</span>
      </div>
      <div class="type-icon t-ikhfa" data-type="إخفاء">
        <span class="ti-dot">🟡</span><span class="ti-label">تدريب: إخفاء</span>
      </div>
      <div class="type-icon t-iqlab" data-type="إقلاب">
        <span class="ti-dot">🟣</span><span class="ti-label">تدريب: إقلاب</span>
      </div>
      <div class="type-icon t-izhar" data-type="إظهار">
        <span class="ti-dot">🔵</span><span class="ti-label">تدريب: إظهار</span>
      </div>
      <div class="type-icon t-idgham1" data-type="إدغام ينمو">
        <span class="ti-dot">🟢</span><span class="ti-label">تدريب: إدغام بغنة</span>
      </div>
      <div class="type-icon t-idgham2" data-type="إدغام رل">
        <span class="ti-dot">🟩</span><span class="ti-label">تدريب: إدغام بلا غنة</span>
      </div>
    </div>

    <label class="entry-label">أو اختر حكماً إضافياً (تدريب مباشر):</label>
    <select class="entry-select" id="extraRuleSelect" onchange="onExtraRuleChange()">
      <option value="">— بلا حكم إضافي —</option>
    </select>

    <label class="entry-label">نطاق التدريب/الاختبار:</label>
    <select class="entry-select" id="scopeSelect" onchange="onScopeChange()">
      <option value="all" selected>📖 المصحف كامل</option>
      <option value="sura">📌 سورة محددة</option>
    </select>
    <div id="suraSelectWrap" style="display:none;">
      <label class="entry-label">اختر السورة:</label>
      <select class="entry-select" id="suraSelect">
        <option value="">جارٍ التحميل...</option>
      </select>
    </div>

    <label class="entry-label">عدد الأسئلة:</label>
    <select class="entry-select" id="totalQ">
      <option value="10">10 أسئلة</option>
      <option value="20" selected>20 سؤالاً</option>
      <option value="30">30 سؤالاً</option>
      <option value="50">50 سؤالاً</option>
    </select>
    <label class="entry-label" id="levelLabel">المستوى الابتدائي:</label>
    <select class="entry-select" id="startLevel">
      <option value="1">مبتدئ</option>
      <option value="2" selected>متوسط</option>
      <option value="3">متقدم</option>
    </select>
    <div style="display:flex; gap:8px;">
      <button class="btn-start" id="btnStart" onclick="startQuiz()" style="flex:1;">ابدأ الاختبار ◄</button>
      <button class="btn-start" id="btnShutdown" onclick="shutdownApp()" style="flex:0 0 auto; width:auto; padding:14px 18px; background:#EF5350;">🏠 العودة للرئيسية</button>
    </div>
  </div>
</div>

<!-- شاشة الاختبار -->
<div id="quizScreen" style="display:none">
  <div class="score-bar">
    <div class="score-item s-correct" id="cardCorrect"><div class="score-num" id="sCorrect">0</div><div class="score-label">✓ صحيح</div></div>
    <div class="score-item s-wrong" id="cardWrong">  <div class="score-num" id="sWrong">0</div>  <div class="score-label">✗ خطأ</div></div>
    <div class="score-item s-total">  <div class="score-num" id="sCurrent">0</div><div class="score-label" id="sTotalLbl">/ 20</div></div>
    <div class="score-item s-pct" id="cardPct">    <div class="score-num" id="sPct">0%</div>   <div class="score-label">النسبة</div></div>
    <div class="score-item s-level" id="cardLevel">  <div class="score-num" id="sLevel">1</div>  <div class="score-label">المستوى</div></div>
  </div>
  <div class="quiz-wrap">
    <div class="progress"><div class="progress-bar" id="progressBar" style="width:0%"></div></div>
    <div id="quizContent"><div class="loading">⏳ جارٍ تحميل السؤال...</div></div>
  </div>
</div>

<!-- نافذة النطق الدقيق (تظهر بعد تحديد كلمة/عبارة بالسحب) -->
<div class="clip-overlay" id="clipOverlay">
  <div class="clip-popup">
    <div class="clip-popup-phrase" id="clipPhrase"></div>
    <button class="clip-reciter-btn" onclick="playQuizClip('alafasy')">🔊 العفاسي</button>
    <button class="clip-reciter-btn" onclick="playQuizClip('minshawy')">🔊 المنشاوي</button>
    <button class="clip-reciter-btn" onclick="playQuizClip('husary')">🔊 الحصري</button>
    <button class="clip-reciter-btn" onclick="playQuizClip('abdulbasit')">🔊 عبدالباسط</button>
    <div class="clip-status" id="clipStatus"></div>
    <button class="clip-close-btn" onclick="closeClipPopup()">✕ إغلاق</button>
  </div>
</div>
<audio id="clipPlayer" style="display:none"></audio>

<!-- شاشة النتيجة -->
<div class="result-screen" id="resultScreen">
  <div class="result-card">
    <div class="result-bg"></div>
    <div class="result-content">
      <div class="result-border">
        <div class="result-cert-title" id="rCertTitle">شهادة اجتياز اختبار</div>
        <div style="font-size:18px;color:var(--navy);margin-bottom:10px;font-weight:bold;">أحكام تجويد النون الساكنة والتنوين</div>
        <div class="result-name" id="rName"></div>
        <div class="result-date" id="rDate"></div>
        <div id="rInfo" style="font-size:12px;color:var(--muted);margin-bottom:12px;"></div>

        <!-- رسالة من أقل من 50% -->
        <div id="rCertMsg" style="display:none; background:var(--red2); border:1px solid var(--red);
             border-radius:12px; padding:16px; margin:14px 0; font-size:16px; line-height:200%; color:var(--red);">
          تحتاج مراجعة أحد الشيوخ في المقرأة...<br>
          نتمنى لك حظاً أوفر في المرة القادمة 🌟
        </div>

        <div class="result-pct" id="rPct"></div>
        <div class="result-grade" id="rGrade"></div>
        <div class="result-stats" id="rCertStats">
          <div class="result-stat s-correct"><div class="result-stat-num" id="rCorrect"></div><div class="result-stat-lbl">إجابة صحيحة</div></div>
          <div class="result-stat s-wrong">  <div class="result-stat-num" id="rWrong"></div>  <div class="result-stat-lbl">إجابة خاطئة</div></div>
          <div class="result-stat s-total">  <div class="result-stat-num" id="rTotal"></div>  <div class="result-stat-lbl">مجموع الأسئلة</div></div>
        </div>
        <div class="result-sig">
          <div class="sig-block">
            <div class="sig-space"></div>
            <div class="sig-name">د. صبحي حمادي حمدون</div>
            <div class="sig-info">جامعة النور — الموصل</div>
          </div>
          <div class="sig-block">
            <div class="sig-space"></div>
            <div class="sig-name">د. محمد حميد الطائي</div>
            <div class="sig-info">جامعة التقنية والعلوم التطبيقية — صحار</div>
          </div>
        </div>
        <div class="result-quran">﴿ وَرَتِّلِ الْقُرْآنَ تَرْتِيلًا ﴾</div>
      </div>
    </div>
  </div>
  <button class="btn-print" onclick="window.print()">🖨 طباعة الشهادة</button>
  <button class="btn-retry" onclick="retryQuiz()">🔄 إعادة الاختبار</button>
</div>

<script>
let correct=0, wrong=0, level=1, streak=0, answered=false;
let totalQuestions=20, currentNum=0, studentName='', studentGender='', studentDob='', studentContact='';
function shutdownApp() {
  // في السويطة المدموجة، الاختبار جزء من تطبيق واحد يخدم كل الأحكام —
  // لذا "الإنهاء" هنا يعني الرجوع للوحة الرئيسية بدل إغلاق الخادم كله.
  if (!confirm('هل تريد الخروج من الاختبار والعودة للوحة الرئيسية؟')) return;
  window.location.href = '/';
}

let selectedSuraId = '';
let shownQuestionKeys = [];
let selectedExtraRule = '';

async function loadExtraRulesList() {
  try {
    const res = await fetch('/api/extra_rules');
    const rules = await res.json();
    const sel = document.getElementById('extraRuleSelect');
    sel.innerHTML = '<option value="">— بلا حكم إضافي —</option>' +
      rules.map(r => `<option value="${r.key}">${r.icon} ${r.label}</option>`).join('');
  } catch(e) {}
}
loadExtraRulesList();

function onExtraRuleChange() {
  selectedExtraRule = document.getElementById('extraRuleSelect').value;
  if (selectedExtraRule) {
    // إلغاء أي أيقونة مختارة من الشريط القديم، والانتقال لوضع التدريب
    document.querySelectorAll('.type-icon').forEach(e => e.classList.remove('selected'));
    selectedQuizType = 'شامل';  // نُبقيها كقيمة افتراضية غير مؤثرة
    document.getElementById('levelLabel').style.display = 'none';
    document.getElementById('startLevel').style.display  = 'none';
    document.getElementById('btnStart').textContent = 'ابدأ التدريب ◄';
  } else {
    document.getElementById('btnStart').textContent = 'ابدأ الاختبار ◄';
  }
}

function onScopeChange() {
  const scope = document.getElementById('scopeSelect').value;
  document.getElementById('suraSelectWrap').style.display = (scope === 'sura') ? 'block' : 'none';
}

async function loadSurasList() {
  try {
    const res = await fetch('/api/suras');
    const suras = await res.json();
    const sel = document.getElementById('suraSelect');
    sel.innerHTML = suras.map(s => `<option value="${s.suraid}">${s.suraid}. ${s.suraname}</option>`).join('');
  } catch(e) {
    document.getElementById('suraSelect').innerHTML = '<option value="">⚠️ تعذّر تحميل قائمة السور</option>';
  }
}
loadSurasList();

function switchLang(lang, btn) {
  const tip = btn.closest('.tip-box');
  if (!tip) return;
  const wrapper = tip.closest('.quiz-word-tip');
  const idx = wrapper ? wrapper.dataset.tipIdx : '0';
  tip.querySelectorAll('.tip-lang-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById(`tipTextAr-${idx}`).style.display = lang==='ar' ? 'block' : 'none';
  document.getElementById(`tipTextEn-${idx}`).style.display = lang==='en' ? 'block' : 'none';
}

let quizSpeed = 0.75;
const quizAudio = new Audio();
let selectedQuizType = 'شامل';
let quizReaderFolder = 'Aya9Aya';   // القارئ الافتراضي لتشغيل الآية كاملة
let quizReadersList  = [];

async function loadQuizReaders() {
  try {
    const r = await fetch('/api/readers');
    quizReadersList = await r.json();
    if (quizReadersList.length && !quizReadersList.some(x => x.id === quizReaderFolder)) {
      quizReaderFolder = quizReadersList[0].id;
    }
  } catch (e) { /* نُبقي الافتراضي إن تعذّر الجلب */ }
}
loadQuizReaders();

function onReaderChange(sel) { quizReaderFolder = sel.value; }

// ══════════════════════════════════════════════════════════════
//  التحديد بالسحب لكلمة/عبارة + النطق الدقيق بأحد القراء الأربعة
// ══════════════════════════════════════════════════════════════
let dragStart = null, dragCurrent = null, isDragging = false;
let clipCtx = null;

function _wordSpans() {
  return document.querySelectorAll('#ayahTextBox .drag-word');
}
function _highlightDragRange(lo, hi) {
  _wordSpans().forEach(el => {
    const idx = parseInt(el.dataset.idx, 10);
    el.classList.toggle('dragging', idx >= lo && idx <= hi);
  });
}
function _dragWordAt(x, y) {
  const el = document.elementFromPoint(x, y);
  return el ? el.closest('.drag-word') : null;
}

document.addEventListener('mousedown', (e) => {
  if (e.target.closest('.tip-box')) return;   // لا نبدأ سحباً من أزرار الشرح الداخلية
  const el = e.target.closest('.drag-word');
  if (!el) return;
  isDragging = true;
  dragStart = dragCurrent = parseInt(el.dataset.idx, 10);
  _highlightDragRange(dragStart, dragCurrent);
});
document.addEventListener('mouseover', (e) => {
  if (!isDragging) return;
  const el = e.target.closest('.drag-word');
  if (!el) return;
  dragCurrent = parseInt(el.dataset.idx, 10);
  _highlightDragRange(Math.min(dragStart,dragCurrent), Math.max(dragStart,dragCurrent));
});
document.addEventListener('mouseup', () => {
  if (!isDragging) return;
  isDragging = false;
  openClipPopup(Math.min(dragStart,dragCurrent), Math.max(dragStart,dragCurrent));
});

document.addEventListener('touchstart', (e) => {
  const t = e.touches[0];
  if (e.target.closest('.tip-box')) return;
  const el = _dragWordAt(t.clientX, t.clientY);
  if (!el) return;
  isDragging = true;
  dragStart = dragCurrent = parseInt(el.dataset.idx, 10);
  _highlightDragRange(dragStart, dragCurrent);
}, {passive:true});
document.addEventListener('touchmove', (e) => {
  if (!isDragging) return;
  const t = e.touches[0];
  const el = _dragWordAt(t.clientX, t.clientY);
  if (!el) return;
  dragCurrent = parseInt(el.dataset.idx, 10);
  _highlightDragRange(Math.min(dragStart,dragCurrent), Math.max(dragStart,dragCurrent));
}, {passive:true});
document.addEventListener('touchend', () => {
  if (!isDragging) return;
  isDragging = false;
  openClipPopup(Math.min(dragStart,dragCurrent), Math.max(dragStart,dragCurrent));
});

function openClipPopup(lo, hi) {
  const q = window._currentQ;
  if (!q || !q.aya_parts) return;
  const words = q.aya_parts.map(p => p.text);
  const phrase = words.slice(lo, hi + 1).join(' ');
  clipCtx = (lo === hi)
    ? {type:'word',  suraid:q.suraid, verseid:q.verseid, word: words[lo]}
    : {type:'range', suraid:q.suraid, verseid:q.verseid, lo, hi};
  document.getElementById('clipPhrase').textContent = phrase;
  document.getElementById('clipStatus').textContent = '';
  document.getElementById('clipOverlay').classList.add('show');
}

function closeClipPopup() {
  document.getElementById('clipOverlay').classList.remove('show');
  const player = document.getElementById('clipPlayer');
  player.pause();
  _wordSpans().forEach(el => el.classList.remove('dragging'));
}

function playQuizClip(reciter) {
  if (!clipCtx) return;
  const status = document.getElementById('clipStatus');
  const p = new URLSearchParams({suraid: clipCtx.suraid, verseid: clipCtx.verseid,
                                  reciter, type: clipCtx.type});
  if (clipCtx.type === 'range') { p.set('lo', clipCtx.lo); p.set('hi', clipCtx.hi); }
  else { p.set('word', clipCtx.word); }
  status.textContent = '⏳ جارٍ التحضير...';
  const player = document.getElementById('clipPlayer');
  player.src = '/api/quiz/clip?' + p.toString();
  player.play().then(() => { status.textContent = ''; }).catch(async () => {
    try {
      const r = await fetch('/api/quiz/clip?' + p.toString());
      const d = await r.json();
      status.textContent = '⚠ ' + (d.error || 'تعذّر تشغيل المقطع.');
    } catch(e) { status.textContent = '⚠ تعذّر تشغيل المقطع.'; }
  });
}

document.querySelectorAll('.type-icon').forEach(el => {
  el.addEventListener('click', () => {
    document.querySelectorAll('.type-icon').forEach(e => e.classList.remove('selected'));
    el.classList.add('selected');
    selectedQuizType = el.dataset.type;
    selectedExtraRule = '';
    document.getElementById('extraRuleSelect').value = '';

    const isComprehensive = (selectedQuizType === 'شامل');
    document.getElementById('levelLabel').style.display = isComprehensive ? '' : 'none';
    document.getElementById('startLevel').style.display  = isComprehensive ? '' : 'none';
    document.getElementById('btnStart').textContent =
      isComprehensive ? 'ابدأ الاختبار ◄' : 'ابدأ التدريب ◄';
  });
});

function playQuizAyah(suraid, verseid) {
  const s = String(suraid).padStart(3,'0');
  const v = String(verseid).padStart(3,'0');
  quizAudio.src = `/audio/${quizReaderFolder}/${s}${v}.mp3`;
  quizAudio.playbackRate = quizSpeed;
  quizAudio.play().then(()=>{ quizAudio.playbackRate = quizSpeed; }).catch(()=>{
    alert(`ملف الصوت غير موجود. تأكد من وجود مجلد ${quizReaderFolder} في نفس مجلد التطبيق.`);
  });
}

function stopQuizAudio() {
  quizAudio.pause();
  quizAudio.currentTime = 0;
}

function setQuizSpeed(s, btn) {
  quizSpeed = s;
  quizAudio.playbackRate = s;
  document.querySelectorAll('.spd-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
}

function startQuiz() {
  const name = document.getElementById('studentName').value.trim();
  if (!name) { alert('الرجاء إدخال اسمك أولاً'); return; }

  const scope = document.getElementById('scopeSelect').value;
  if (scope === 'sura') {
    selectedSuraId = document.getElementById('suraSelect').value;
    if (!selectedSuraId) { alert('الرجاء اختيار سورة من القائمة'); return; }
  } else {
    selectedSuraId = '';
  }

  studentName    = name;
  studentGender  = document.getElementById('studentGender').value;
  studentDob     = document.getElementById('studentDob').value;
  studentContact = document.getElementById('studentContact').value.trim();
  totalQuestions = parseInt(document.getElementById('totalQ').value);
  level          = parseInt(document.getElementById('startLevel').value);
  correct=0; wrong=0; streak=0; currentNum=0; shownQuestionKeys=[];
  document.getElementById('entryScreen').style.display  = 'none';
  document.getElementById('quizScreen').style.display   = 'block';
  document.getElementById('sTotalLbl').textContent = '/ '+totalQuestions;

  const isTraining = (selectedQuizType !== 'شامل');
  ['cardCorrect','cardWrong','cardPct','cardLevel'].forEach(id => {
    document.getElementById(id).style.display = isTraining ? 'none' : '';
  });

  loadQuestion();
}

async function loadQuestion() {
  if (currentNum >= totalQuestions) {
    if (selectedQuizType !== 'شامل' || selectedExtraRule) { goHome(); } else { showResult(); }
    return;
  }
  stopQuizAudio();
  answered = false;
  document.getElementById('quizContent').innerHTML = '<div class="loading">⏳ جارٍ تحميل السؤال...</div>';

  const suraParam = selectedSuraId ? `&suraid=${selectedSuraId}` : '';
  const excludeParam = shownQuestionKeys.length
      ? `&exclude=${encodeURIComponent(shownQuestionKeys.join(','))}` : '';

  let res, q;
  if (selectedExtraRule) {
    res = await fetch(`/api/quiz/extra_question?rule=${encodeURIComponent(selectedExtraRule)}${suraParam}${excludeParam}`);
    q = await res.json();
  } else {
    res = await fetch(`/api/quiz/question?level=${level}&type=${encodeURIComponent(selectedQuizType)}${suraParam}${excludeParam}`);
    q = await res.json();
  }
  if (q.error === 'no_data_in_sura' || q.error === 'no_more_questions') {
    const msg = q.error === 'no_more_questions'
      ? '✅ لقد استعرضت كل الحالات المتوفرة لهذا الحكم في السورة المختارة.'
      : '⚠️ لا توجد حالات لهذا الحكم في السورة المختارة. جرّب سورة أخرى أو نوعاً آخر.';
    document.getElementById('quizContent').innerHTML = `
      <div class="loading">${msg}</div>
      <div class="btn-row">
        <button class="btn-finish show" onclick="goHome()">🏠 القائمة الرئيسية</button>
      </div>`;
    return;
  }
  if (q.error) { document.getElementById('quizContent').innerHTML='<div class="loading">خطأ</div>'; return; }

  shownQuestionKeys.push(`${q.suraid}-${q.verseid}-${q.word}`);
  window._currentQ = q;
  const color = q.color;
  let ayahHtml = '';
  let tipIdx = 0;
  let wIdx = 0;
  for (const p of q.aya_parts) {
    const idxAttr = wIdx++;
    if (p.highlight) {
      const idx = tipIdx++;
      ayahHtml += `<span class="quiz-word-tip drag-word" data-idx="${idxAttr}" data-tip-idx="${idx}" style="color:${color};font-weight:bold;text-decoration:underline;text-decoration-color:${color}55;text-underline-offset:5px" data-word="${p.text}"><span class="tip-box"><div class="tip-lang-row"><button class="tip-lang-btn active" onclick="switchLang('ar',this)">عربي</button><button class="tip-lang-btn" onclick="switchLang('en',this)">English</button></div><div class="tip-text" id="tipTextAr-${idx}">⏳ جارٍ التحميل...</div><div class="tip-text" id="tipTextEn-${idx}" style="display:none;direction:ltr;text-align:left">⏳ Loading...</div></span>${p.text}</span> `;
    } else {
      ayahHtml += `<span class="drag-word" data-idx="${idxAttr}" style="color:var(--text)">${p.text}</span> `;
    }
  }
  ayahHtml += `<span style="color:var(--gold);font-size:0.8em"> ﴿${q.verseid}﴾</span>`;

  const levelLabel = ['','مبتدئ','متوسط','متقدم'][level]||'متقدم';
  const levelClass = `level-${Math.min(level,3)}`;
  const remaining  = totalQuestions - currentNum;
  const isTraining = (selectedQuizType !== 'شامل');

  const ayahCardHtml = `
    <div class="ayah-card">
      <div class="ayah-label">
        ${isTraining ? '' : `<span class="level-badge ${levelClass}">${levelLabel}</span>`}
        سورة ${q.suraname} — الآية ${q.next_verseid ? (q.verseid + '-' + q.next_verseid) : q.verseid}
        <span style="margin-right:auto;color:var(--muted)">متبقٍ: ${remaining}</span>
      </div>
      <div class="ayah-text" id="ayahTextBox">${ayahHtml}</div>
      <div class="audio-row">
        <button class="btn-listen" onclick="playQuizAyah(${q.suraid},${q.verseid})">▶ استمع</button>
        <button class="btn-stop-q" onclick="stopQuizAudio()">⏹</button>
        <select class="reader-select" onchange="onReaderChange(this)">
          ${quizReadersList.map(r => `<option value="${r.id}" ${r.id===quizReaderFolder?'selected':''}>${r.label}</option>`).join('')}
        </select>
        <span class="speed-label-q">السرعة:</span>
        <button class="spd-btn active" onclick="setQuizSpeed(0.75,this)">0.75x</button>
        <button class="spd-btn" onclick="setQuizSpeed(1.0,this)">1.0x</button>
        <button class="spd-btn" onclick="setQuizSpeed(1.25,this)">1.25x</button>
        <button class="spd-btn" onclick="setQuizSpeed(1.5,this)">1.5x</button>
      </div>
    </div>`;

  if (isTraining) {
    // ── وضع التدريب: عرض الحكم والشرح مباشرة، بلا اختيارات ──
    currentNum++;
    document.getElementById('quizContent').innerHTML = `
      ${ayahCardHtml}
      <div class="question-text">حكم الكلمة <span style="color:${color}">${q.word}</span>:</div>
      <div class="feedback show correct-fb" style="display:block">
        <b style="color:${color};font-size:1.1em">${q.correct}</b><br>${q.explanation}
      </div>
      <div class="btn-row">
        <button class="btn-next show" id="btnNext" onclick="nextQuestion()">التالي ◄</button>
        <button class="btn-finish show" id="btnFinish" onclick="goHome()">🏠 القائمة الرئيسية</button>
      </div>
    `;
    updateScore();

    document.querySelectorAll('.quiz-word-tip').forEach(tip => {
      const word = tip.dataset.word;
      const idx  = tip.dataset.tipIdx;
      fetchWordExplain(word, idx, q.suraid, q.verseid);
    });
    return;
  }

  document.getElementById('quizContent').innerHTML = `
    ${ayahCardHtml}
    <div class="question-text">ما حكم الكلمة الملوّنة <span style="color:${color}">${q.word}</span> ؟</div>
    <div class="choices" id="choicesDiv">
      ${q.choices.map(c=>`<button class="choice-btn" onclick="checkAnswer('${c.replace(/'/g,"\\'")}')">${c}</button>`).join('')}
    </div>
    <div class="feedback" id="feedbackDiv"></div>
    <div class="btn-row">
      <button class="btn-next" id="btnNext" onclick="nextQuestion()">التالي ◄</button>
      <button class="btn-finish show" id="btnFinish" onclick="showResult()">إنهاء الاختبار ✓</button>
    </div>
    <button class="btn-skip" onclick="skipQuestion()">⟩ تخطي السؤال</button>
  `;
  updateScore();

  // جلب معنى كل كلمة ملوّنة فوراً عند تحميل السؤال (لا ننتظر hover،
  // لأن الماوس قد يكون أصلاً واقفاً فوق العنصر فلا يُطلَق mouseenter)
  document.querySelectorAll('.quiz-word-tip').forEach(tip => {
    const word = tip.dataset.word;
    const idx  = tip.dataset.tipIdx;
    fetchWordExplain(word, idx, q.suraid, q.verseid);
  });
}

async function fetchWordExplain(word, idx, suraid, verseid) {
  const arEl = document.getElementById(`tipTextAr-${idx}`);
  const enEl = document.getElementById(`tipTextEn-${idx}`);
  const timeoutMs = 5000;
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const r = await fetch('/api/explain', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ word: word, suraid: suraid, verseid: verseid }),
      signal: controller.signal,
    });
    clearTimeout(timer);
    const d = await r.json();
    if (arEl) arEl.textContent = d.ar || word;
    if (enEl) enEl.textContent = d.en || word;
  } catch(e) {
    if (arEl) arEl.textContent = `⚠️ تعذّر التحميل (${word})`;
    if (enEl) enEl.textContent = `⚠️ Failed to load (${word})`;
  }
}

function checkAnswer(choice) {
  if (answered) return;
  answered = true;
  currentNum++;
  const q = window._currentQ;
  const isCorrect = choice === q.correct;

  document.querySelectorAll('.choice-btn').forEach(btn => {
    btn.disabled = true;
    if (btn.textContent === q.correct) btn.classList.add('correct');
    else if (btn.textContent === choice && !isCorrect) btn.classList.add('wrong');
  });

  const fb = document.getElementById('feedbackDiv');
  if (isCorrect) {
    correct++; streak++;
    if (streak >= 3 && level < 3) { level++; streak=0; }
    fb.className = 'feedback show correct-fb';
    fb.innerHTML = `✅ <b>إجابة صحيحة!</b><br>${q.explanation}`;
  } else {
    wrong++; streak=0;
    if (wrong > correct && level > 1) level = Math.max(1, level-1);
    fb.className = 'feedback show wrong-fb';
    fb.innerHTML = `❌ <b>الإجابة الصحيحة: ${q.correct}</b><br>${q.explanation}`;
  }

  document.getElementById('btnNext').classList.add('show');
  document.getElementById('btnFinish').classList.add('show');
  updateScore();

  if (currentNum >= totalQuestions) {
    setTimeout(showResult, 1500);
  }
}

function skipQuestion() {
  if (!answered) { currentNum++; loadQuestion(); }
}

function goHome() {
  document.getElementById('quizScreen').style.display  = 'none';
  document.getElementById('resultScreen').style.display = 'none';
  document.getElementById('entryScreen').style.display  = 'block';
  correct=0; wrong=0; streak=0; currentNum=0; shownQuestionKeys=[];
}

function nextQuestion() {
  loadQuestion();
}

function updateScore() {
  document.getElementById('sCorrect').textContent  = correct;
  document.getElementById('sWrong').textContent    = wrong;
  document.getElementById('sCurrent').textContent  = currentNum;
  document.getElementById('sLevel').textContent    = level;
  const pct = currentNum>0 ? Math.round(correct/currentNum*100) : 0;
  document.getElementById('sPct').textContent      = pct+'%';
  document.getElementById('progressBar').style.width = (currentNum/totalQuestions*100)+'%';
}

function showResult() {
  document.getElementById('quizScreen').style.display  = 'none';
  document.getElementById('resultScreen').style.display = 'block';

  const pct   = currentNum>0 ? Math.round(correct/currentNum*100) : 0;

  fetch('/api/save_result', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({
      name: studentName, gender: studentGender, contact: studentContact,
      quizType: selectedQuizType, total: currentNum,
      correct: correct, wrong: wrong, pct: pct
    })
  }).catch(()=>{});

  const now   = new Date();
  const dateStr = now.toLocaleDateString('ar-IQ', {year:'numeric',month:'long',day:'numeric'});

  let grade, gradeClass, gradeColor;
  if      (pct>=90) { grade='ممتاز';  gradeClass='grade-a'; gradeColor='#00C853'; }
  else if (pct>=75) { grade='جيد جداً'; gradeClass='grade-b'; gradeColor='#00BCD4'; }
  else if (pct>=60) { grade='جيد';    gradeClass='grade-c'; gradeColor='#F0C755'; }
  else              { grade='مقبول'; gradeClass='grade-d'; gradeColor='#EF5350'; }

  document.getElementById('rName').textContent    = studentName;
  document.getElementById('rDate').textContent    = dateStr;

  // عنوان الشهادة — يظهر "اجتياز" فقط لمن حصل على 50% فأكثر
  const certTitle = document.getElementById('rCertTitle');
  const certMsg   = document.getElementById('rCertMsg');
  const certStats = document.getElementById('rCertStats');
  const certGrade = document.getElementById('rGrade');
  const certPct   = document.getElementById('rPct');

  if (pct >= 50) {
    certTitle.textContent  = 'شهادة اجتياز اختبار';
    certTitle.style.color  = 'var(--green)';
    certMsg.style.display  = 'none';
    certStats.style.display= 'flex';
    certGrade.style.display= 'inline-block';
    certPct.style.display  = 'block';
  } else {
    certTitle.textContent  = 'نتيجة اختبار';
    certTitle.style.color  = 'var(--red)';
    certMsg.style.display  = 'block';
    certStats.style.display= 'none';
    certGrade.style.display= 'none';
    certPct.style.display  = 'none';
  }

  // بيانات المختبَر
  let infoHtml = '';
  if (studentGender)  infoHtml += `<span>الجنس: ${studentGender}</span>`;
  if (studentDob) {
    const dob = new Date(studentDob);
    const dobStr = dob.toLocaleDateString('ar-IQ',{year:'numeric',month:'long',day:'numeric'});
    infoHtml += `&nbsp;|&nbsp;<span>تاريخ الميلاد: ${dobStr}</span>`;
  }
  if (studentContact) infoHtml += `&nbsp;|&nbsp;<span>${studentContact}</span>`;
  document.getElementById('rInfo').innerHTML = infoHtml;
  document.getElementById('rPct').textContent     = pct+'%';
  document.getElementById('rPct').style.color     = gradeColor;
  document.getElementById('rGrade').textContent   = grade;
  document.getElementById('rGrade').className     = 'result-grade '+gradeClass;
  document.getElementById('rCorrect').textContent = correct;
  document.getElementById('rWrong').textContent   = wrong;
  document.getElementById('rTotal').textContent   = currentNum;
}

function retryQuiz() {
  document.getElementById('resultScreen').style.display = 'none';
  document.getElementById('entryScreen').style.display  = 'block';
  document.getElementById('studentName').value    = studentName;
  document.getElementById('studentContact').value = studentContact;
}
</script>
</body></html>'''


@bp.route('/quiz')
def index():
    return HTML


@bp.route('/api/save_result', methods=['POST'])
def api_save_result():
    data = request.get_json()
    conn = get_db(); cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS quiz_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_name TEXT, student_gender TEXT, student_contact TEXT,
        quiz_type TEXT, total_q INTEGER, correct INTEGER, wrong INTEGER,
        pct INTEGER, saved_at TEXT)''')
    cur.execute('''INSERT INTO quiz_results
        (student_name, student_gender, student_contact, quiz_type,
         total_q, correct, wrong, pct, saved_at)
        VALUES (?,?,?,?,?,?,?,?,datetime('now','localtime'))''',
        (data.get('name',''), data.get('gender',''), data.get('contact',''),
         data.get('quizType',''), data.get('total',0), data.get('correct',0),
         data.get('wrong',0), data.get('pct',0)))
    conn.commit(); conn.close()
    return jsonify({'ok': True})


@bp.route('/api/suras')
def api_suras():
    """يعتمد على mushafnew (المتوفر دائماً في كل نسخ quran.db المستخدمة
    عبر السويطة) بدل جدول asmasur الذي قد لا يكون موجوداً."""
    conn = get_db(); cur = conn.cursor()
    cur.execute('''SELECT DISTINCT SURAID, SURANAME FROM mushafnew
                   ORDER BY CAST(SURAID AS INTEGER)''')
    rows = cur.fetchall()
    conn.close()
    return jsonify([{'suraid': r[0], 'suraname': r[1]} for r in rows])


@bp.route('/api/extra_rules')
def api_extra_rules():
    return jsonify([{'key': k, 'icon': v['icon'], 'label': v['label']}
                     for k, v in EXTRA_RULES.items()])


@bp.route('/api/quiz/extra_question')
def api_quiz_extra_question():
    rule_name = request.args.get('rule', '').strip()
    suraid    = request.args.get('suraid', '').strip()
    exclude_raw = request.args.get('exclude', '').strip()

    fetcher = EXTRA_FETCHERS.get(rule_name)
    if not fetcher:
        return jsonify({'error': 'unknown_rule'})

    excluded = set()
    if exclude_raw:
        for key in exclude_raw.split(','):
            parts = key.split('-', 2)
            if len(parts) == 3:
                try:
                    excluded.add((int(parts[0]), int(parts[1]), parts[2]))
                except ValueError:
                    pass

    conn = get_db(); cur = conn.cursor()
    result = None
    for _ in range(25):  # نحاول حتى 25 مرة لتجنب الحالات المُستثناة
        candidate = fetcher(cur, suraid)
        if candidate is None:
            break
        key = (candidate['suraid'], candidate['verseid'], (candidate['klma1'] or '').strip())
        if key not in excluded:
            result = candidate
            break

    if result is None:
        conn.close()
        error_code = 'no_more_questions' if excluded else 'no_data_in_sura'
        return jsonify({'error': error_code})

    ayahtext = (result['ayahtext'] or '').replace('\r\n', ' ').replace('\n', ' ').strip()
    klma1 = (result['klma1'] or '').strip()
    klma2 = (result['klma2'] or '').strip()
    words = ayahtext.split()

    def find_idx(words_list, k1, k2):
        occ = [i for i, w in enumerate(words_list) if w.strip() == k1]
        if k2:
            exact = [i for i in occ if i+1 < len(words_list) and words_list[i+1].strip() == k2]
            if exact: return exact[0]
            if occ: return occ[-1]
            return -1
        return occ[0] if occ else -1

    colored_idx = find_idx(words, klma1, klma2)
    klma2_idx = colored_idx + 1 if colored_idx != -1 else -1
    klma2_found = (not klma2) or (klma2_idx != -1 and klma2_idx < len(words) and words[klma2_idx].strip() == klma2)

    aya_parts = []
    for i, w in enumerate(words):
        is_k1 = (i == colored_idx)
        is_k2 = (bool(klma2) and klma2_found and i == klma2_idx)
        aya_parts.append({'text': w, 'highlight': is_k1 or is_k2})

    conn.close()
    return jsonify({
        'word': klma1, 'word2': klma2, 'suraid': result['suraid'], 'verseid': result['verseid'],
        'next_verseid': None, 'suraname': result['suraname'],
        'correct': result['correct'], 'choices': result['choices'],
        'color': result['color'], 'explanation': result['explanation'],
        'aya_parts': aya_parts,
    })


@bp.route('/api/quiz/question')
def api_quiz_question():
    level     = int(request.args.get('level', 1))
    quiz_type = request.args.get('type', 'شامل')
    suraid    = request.args.get('suraid', '').strip()
    exclude_raw = request.args.get('exclude', '').strip()
    conn  = get_db(); cur = conn.cursor()

    # تحويل exclude إلى مجموعة من (suraid, verseid, klma1) لاستثنائها
    excluded = set()
    if exclude_raw:
        for key in exclude_raw.split(','):
            parts = key.split('-', 2)
            if len(parts) == 3:
                try:
                    excluded.add((int(parts[0]), int(parts[1]), parts[2]))
                except ValueError:
                    pass

    if quiz_type and quiz_type != 'شامل':
        itypes = [quiz_type]
    elif level == 1:
        itypes = ['إخفاء','إقلاب']
    elif level == 2:
        itypes = ['إخفاء','إقلاب','إظهار','إدغام ينمو']
    else:
        itypes = ['إخفاء','إقلاب','إظهار','إدغام ينمو','إدغام رل']

    itype_choice = random.choice(itypes)

    def fetch_candidates(itype_pattern, sura_filter):
        params = [f'%{itype_pattern}%']
        sql = '''SELECT n.klma1,n.klma2,n.suraid,n.verseid,n.kseq,n.itype,
                        m.SURANAME,m.ayahtext
                 FROM newtaj n
                 JOIN mushafnew m ON n.suraid=m.SURAID AND n.verseid=m.VERSEID
                 WHERE n.itype LIKE ?'''
        if sura_filter:
            sql += ' AND n.suraid=?'
            params.append(sura_filter)
        sql += ' ORDER BY RANDOM() LIMIT 30'  # نجلب دفعة، ثم نُصفّي المُستثنى محلياً
        cur.execute(sql, params)
        return cur.fetchall()

    def pick_unexcluded(rows):
        for r in rows:
            key = (r[2], r[3], (r[0] or '').strip())
            if key not in excluded:
                return r
        return None

    row = pick_unexcluded(fetch_candidates(itype_choice, suraid))

    if not row and suraid:
        # لا توجد حالات (غير مُستثناة) لهذا النوع تحديداً في هذه السورة؛
        # نحاول أي نوع آخر من نفس itypes المسموحة قبل الاستسلام نهائياً
        for alt_type in itypes:
            row = pick_unexcluded(fetch_candidates(alt_type, suraid))
            if row:
                break
        if not row:
            conn.close()
            error_code = 'no_more_questions' if excluded else 'no_data_in_sura'
            return jsonify({'error': error_code})

    if not row and not suraid:
        # نفس المنطق لحالة "المصحف كامل" (نادراً ما يحدث، لكن نتعامل معه)
        for alt_type in itypes:
            row = pick_unexcluded(fetch_candidates(alt_type, ''))
            if row:
                break
        if not row:
            conn.close()
            error_code = 'no_more_questions' if excluded else 'no data'
            return jsonify({'error': error_code})

    klma1,klma2 = (row[0] or '').strip(),(row[1] or '').strip()
    suraid,verseid,kseq,itype = row[2],row[3],row[4],row[5]
    suraname    = row[6]
    ayahtext    = (row[7] or '').replace('\\r\\n',' ').replace('\\n',' ').strip()
    detail      = get_detail(itype,klma2)
    color       = get_color(itype)

    HARAKAT = set('\u064B\u064C\u064D\u064E\u064F\u0650\u0651\u0652\u06D6\u06E1\u0640')
    if 'رل' in itype:
        first = next((c for c in klma2 if '\u0621'<=c<='\u06FF' and c not in HARAKAT),'')
        correct = 'إدغام بلا غنة — لام' if first=='\u0644' else 'إدغام بلا غنة — راء'
    elif 'ينمو' in itype: correct = 'إدغام بغنة'
    elif 'إظهار' in itype: correct = 'إظهار حلقي'
    elif 'إقلاب' in itype: correct = 'إقلاب'
    elif 'إخفاء' in itype: correct = 'إخفاء'
    else: correct = detail

    pool = ['إدغام بغنة','إدغام بلا غنة — لام','إدغام بلا غنة — راء','إظهار حلقي','إقلاب','إخفاء']
    choices = [correct] + random.sample([c for c in pool if c!=correct],3)
    random.shuffle(choices)

    def extract_letter_after_noon(word):
        """يستخرج الحرف الذي يلي مباشرة النون الساكنة/التنوين داخل الكلمة نفسها
        (لحالة 'في كلمة واحدة')، متجاوزاً علامات التشكيل."""
        HARAKAT_LOCAL = set('\u064B\u064C\u064D\u064E\u064F\u0650\u0651\u0652\u06D6\u06E1\u0670\u0640')
        chars = [c for c in word if c not in HARAKAT_LOCAL]
        for i, c in enumerate(chars):
            if c == 'ن' and i+1 < len(chars):
                return chars[i+1]
        return ''

    same_word_letter = extract_letter_after_noon(klma1) if not klma2 else ''

    if klma2:
        target_desc = f'النون/التنوين قبل «{klma2}»'
    else:
        target_desc = (f'النون داخل الكلمة نفسها، يليها حرف «{same_word_letter}»'
                        if same_word_letter else 'النون/التنوين داخل الكلمة نفسها')

    EXPL = {
        'إدغام بغنة'          : f'الكلمة «{klma1}»: {target_desc} (من حروف ينمو) → إدغام مع غنة.',
        'إدغام بلا غنة — لام' : f'الكلمة «{klma1}»: {target_desc} (اللام) → إدغام بلا غنة.',
        'إدغام بلا غنة — راء' : f'الكلمة «{klma1}»: {target_desc} (الراء) → إدغام بلا غنة.',
        'إظهار حلقي'          : f'الكلمة «{klma1}»: {target_desc} (من حروف الحلق) → إظهار واضح.',
        'إقلاب'               : f'الكلمة «{klma1}»: {target_desc} (الباء) → تُقلب ميماً مخفاة مع الغنة.',
        'إخفاء'               : f'الكلمة «{klma1}»: {target_desc} (من حروف الإخفاء الخمسة عشر) → إخفاء مع غنة.',
    }

    words = ayahtext.split()
    aya_parts = []
    colored_idx = -1
    next_verseid = None

    def find_colored_idx(words_list, k1, k2):
        """يبحث عن أفضل موضع لـ k1 في words_list، مفضّلاً الزوج k1+k2 معاً"""
        occ = [i for i, w in enumerate(words_list) if w.strip() == k1]
        if k2:
            exact = [i for i in occ if i+1 < len(words_list) and words_list[i+1].strip() == k2]
            if exact:
                return exact[0]
            if occ:
                return occ[-1]
            return -1
        return occ[0] if occ else -1

    # ملاحظة مهمة: kseq في جدول newtaj لا يشير دوماً لموضع klma1 نفسها،
    # بل أحياناً للكلمة المجاورة المرتبطة بنقطة الحكم. لذلك نعتمد فقط
    # على المطابقة النصية الذكية، مع تفضيل الزوج (klma1+klma2) معاً
    # لتجنب الخطأ عند تكرار klma1 أكثر من مرة في الآية.
    colored_idx = find_colored_idx(words, klma1, klma2)

    if colored_idx == -1:
        # خطأ بيانات معروف: بعض صفوف newtaj مُسجَّلة بـ verseid يخص
        # آخر آية قبل بداية كلمة klma1 الفعلية (التي تقع في الآية التالية).
        # نحاول الآية التالية كاحتياط.
        cur.execute('''SELECT VERSEID, ayahtext FROM mushafnew
                       WHERE SURAID=? AND VERSEID>? ORDER BY VERSEID LIMIT 1''',
                    (suraid, verseid))
        nxt = cur.fetchone()
        if nxt:
            next_words_try = (nxt[1] or '').replace('\\r\\n',' ').replace('\\n',' ').strip().split()
            idx_in_next = find_colored_idx(next_words_try, klma1, klma2)
            if idx_in_next != -1:
                # وُجدت الكلمة في الآية التالية فعلياً؛ نعرض تلك الآية كاملة
                next_verseid = nxt[0]
                ayahtext = (nxt[1] or '').replace('\\r\\n',' ').replace('\\n',' ').strip()
                words = next_words_try
                colored_idx = idx_in_next
                suraname_row = None  # نبقي suraname كما هو (نفس السورة عادة)

    klma2_idx_in_words = colored_idx + 1 if colored_idx != -1 else -1
    klma2_found_in_aya = (
        not klma2  # إن كانت klma2 فارغة أصلاً (حكم في كلمة واحدة)، لا حاجة للبحث عنها
        or (
            klma2_idx_in_words != -1
            and klma2_idx_in_words < len(words)
            and words[klma2_idx_in_words].strip() == klma2
        )
    )

    if klma2 and not klma2_found_in_aya and next_verseid is None:
        # حالة الوصل: الكلمة الثانية في الآية التالية (أو السورة التالية)
        # (لا نبحث إطلاقاً إن كانت klma2 فارغة من الأساس)
        cur.execute('''SELECT VERSEID, ayahtext FROM mushafnew
                       WHERE SURAID=? AND VERSEID>? ORDER BY VERSEID LIMIT 1''',
                    (suraid, verseid))
        nxt = cur.fetchone()
        if nxt:
            next_verseid = nxt[0]
            next_words = (nxt[1] or '').replace('\\r\\n',' ').replace('\\n',' ').strip().split()
            words = words + next_words
            klma2_idx_in_words = colored_idx + 1 if colored_idx != -1 else len(words)
            klma2_found_in_aya = (
                klma2_idx_in_words < len(words)
                and words[klma2_idx_in_words].strip() == klma2
            )

    for i, w in enumerate(words):
        is_klma1 = (i == colored_idx)
        is_klma2 = (bool(klma2) and klma2_found_in_aya and i == klma2_idx_in_words)
        aya_parts.append({'text': w, 'highlight': is_klma1 or is_klma2})

    conn.close()
    display_verseid = next_verseid if next_verseid is not None else verseid
    return jsonify({
        'word':klma1,'word2':klma2,'suraid':suraid,'verseid':display_verseid,
        'next_verseid':None if next_verseid == display_verseid else next_verseid,
        'suraname':suraname,'itype':itype,'correct':correct,'detail':detail,
        'color':color,'choices':choices,'explanation':EXPL.get(correct,detail),
        'aya_parts':aya_parts,
    })


@bp.route('/api/explain', methods=['POST'])
def api_explain():
    data    = request.get_json()
    word    = data.get('word','')
    suraid  = data.get('suraid')
    verseid = data.get('verseid')
    ar_text = f'الكلمة: {word}'
    en_text = f'Word: {word}'
    try:
        conn = get_db(); cur = conn.cursor()
        if suraid and verseid:
            try:
                cur.execute('SELECT text_en FROM quran_en WHERE suraid=? AND verseid=? LIMIT 1',
                            (suraid, verseid))
                en = cur.fetchone()
                if en:
                    t = en[0]
                    en_text = f'🇬🇧 {t[:160]}{"..." if len(t)>160 else ""}'
            except: pass
            try:
                cur.execute('SELECT tafseer FROM tafseer_jalalayn WHERE suraid=? AND verseid=? LIMIT 1',
                            (suraid, verseid))
                tf = cur.fetchone()
                if tf:
                    t = tf[0]
                    ar_text = f'📖 {t[:160]}{"..." if len(t)>160 else ""}'
            except: pass
        conn.close()
    except: pass
    return jsonify({'ar': ar_text, 'en': en_text})



@bp.route('/api/quiz/clip')
def api_quiz_clip():
    """يُرجع مقطعاً صوتياً دقيقاً (كلمة واحدة أو مجال كلمات متتالية
    محدَّد بالسحب) من تلاوة أحد القراء الأربعة، بالاعتماد على
    word_audio_helper — لنفس آلية النطق الدقيق المستخدمة في تطبيقات
    الأحكام الأخرى."""
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
    from flask import send_file
    return send_file(clip_path, mimetype='audio/mpeg')



@bp.route('/api/shutdown', methods=['POST'])
def api_shutdown():
    # في السويطة المدموجة يُنهي هذا الأمر كل الأحكام معاً وليس هذا الحكم
    # فقط — عطّلناه هنا، وحوّلنا الزر في الواجهة إلى رابط رجوع للوحة
    # الرئيسية بدل إنهاء الخادم فعلياً (انظر تعديل shutdownApp أدناه).
    return jsonify({'ok': False, 'error': 'غير متاح في النسخة المدموجة'}), 403


