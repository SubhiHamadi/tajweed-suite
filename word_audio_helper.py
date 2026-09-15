"""
word_audio_helper.py
══════════════════════════════════════════════════════════════════
وحدة مستقلة (لا تعتمد على أي ملف آخر من التطبيق) لتشغيل نطق كلمة
واحدة، أو عبارة من كلمتين متتاليتين معاً، من تسجيل أحد القرّاء
المدعومين، باقتطاعها لحظياً من ملف الآية الكاملة الموجود محلياً،
بالاعتماد على بيانات توقيت دقيقة (بالمللي ثانية) لكل كلمة —
مشروع مفتوح المصدر quran-align: https://github.com/cpfair/quran-align
(رخصة CC BY 4.0)

المتطلبات لكل قارئ مدعوم:
  - ملف التوقيت الخاص به (مثال: Alafasy_128kbps.json) — يوضع بجانب
    هذا الملف، أو بجانب quran.db، أو في D:\family
  - مجلد الصوت المحلي المطابق له (بنفس تسمية SSSVVV.mp3 المستخدمة
    في باقي التطبيق)
  - ffmpeg — لا حاجة لتثبيته يدوياً؛ إن توفرت حزمة imageio-ffmpeg
    (pip install imageio-ffmpeg) تُستخدم نسخة محمولة تلقائياً.

طريقة الاستخدام من أي تطبيق آخر:

    from word_audio_helper import (
        play_word_pronunciation, play_phrase_pronunciation,
        available_reciters,
    )

    # كلمة واحدة
    ok, msg = play_word_pronunciation(
        player, audio_out, base_dir=BASE, readers_dict=AUDIO_DIRS,
        suraid=suraid, verseid=verseid, aya_text=aya_text, word=word,
        reciter_key='alafasy')

    # عبارة من كلمتين متتاليتين معاً (بنفس ترتيب ورودهما في الآية)
    ok, msg = play_phrase_pronunciation(
        player, audio_out, base_dir=BASE, readers_dict=AUDIO_DIRS,
        suraid=suraid, verseid=verseid, aya_text=aya_text,
        words=[word1, word2], reciter_key='alafasy')

    if not ok:
        # msg تحتوي رسالة توضح سبب عدم التمكّن (تُعرض للمستخدم كما هي)
        ...
══════════════════════════════════════════════════════════════════
"""
import os, re, json, shutil, subprocess, hashlib, tempfile, unicodedata
# استيراد PyQt6 اختياري: يسمح باستخدام هذه الوحدة أيضاً من بيئات لا
# تحتوي PyQt6 إطلاقاً (كتطبيقات Flask/ويب) عبر الدوال "العارية"
# (prepare_*) التي تُعيد مسار الملف الصوتي فقط دون تشغيله؛ بينما دوال
# play_* (المخصّصة لتطبيقات PyQt6 سطح المكتب) تستورد QUrl عند استدعائها
# فقط لا عند استيراد الوحدة نفسها.
try:
    from PyQt6.QtCore import QUrl
    _PYQT_OK = True
except Exception:
    _PYQT_OK = False

# ══════════════════════════════════════════════════════════════
#  سجلّ القرّاء المدعومين
# ══════════════════════════════════════════════════════════════
# لكل قارئ: اسم ملف التوقيت، كلمات مفتاحية لتخمين مجلده من اسمه (لو كان
# اسم المجلد صريحاً في مشروع آخر)، وأسماء مجلدات معروفة يدوياً (لهذا
# المشروع تحديداً، حيث أسماء المجلدات رموز مثل Aya1Aya لا أسماء صريحة).
RECITERS = {
    'alafasy': {
        'label'       : 'الشيخ مشاري راشد العفاسي',
        'timing_file' : 'Alafasy_128kbps.json',
        'hints'       : ['مشاري', 'المعافس', 'العفاسي', 'alafasy', 'afasy',
                          'mishary', 'mishari'],
        # تم التأكد يدوياً: الشيخ مشاري العفاسي هو المجلد Aya1Aya
        'known_folders': ['Aya1Aya'],
    },
    'minshawy': {
        'label'       : 'الشيخ محمد صديق المنشاوي (مرتّل)',
        'timing_file' : 'Minshawy_Murattal_128kbps.json',
        'hints'       : ['منشاوي', 'المنشاوي', 'minshawy', 'menshawy',
                          'minshawi', 'mnshawi'],
        # تخمين أولي غير مؤكَّد بعد: بما أن مجلدات هذا المشروع تحديداً
        # مرقّمة بترتيب القرّاء في قائمة الاختيار الظاهرة في التطبيق
        # (1=مشاري ← Aya1Aya، وهذا تأكد فعلاً)، ومحمد صديق المنشاوي هو
        # المجلد الجديد الذي أنشأه المستخدم خصيصاً بتلاوة المنشاوي
        # المرتّلة (ليحل محل التخمين السابق Aya7Aya).
        'known_folders': ['mnshawi_moratl', 'Aya7Aya'],
    },
    'husary': {
        'label'       : 'الشيخ محمود خليل الحصري (مرتّل)',
        'timing_file' : 'Husary_64kbps.json',
        'hints'       : ['حصري', 'الحصري', 'husary', 'alhusary', 'husari'],
        # تم التأكد يدوياً: الشيخ الحصري هو المجلد "الحصري" (بالعربي)
        'known_folders': ['الحصري'],
    },
    'abdulbasit': {
        'label'       : 'الشيخ عبدالباسط عبدالصمد (مجوَّد)',
        'timing_file' : 'Abdul_Basit_Mujawwad_128kbps.json',
        'hints'       : ['عبدالباسط', 'عبد الباسط', 'abdulbasit', 'abdul_basit',
                          'abdel basit', 'abdelbasit'],
        # تم التأكد يدوياً: الشيخ عبدالباسط هو المجلد "عبدالباسط_مجود_آيات"
        'known_folders': ['عبدالباسط_مجود_آيات'],
    },
}
DEFAULT_RECITER = 'alafasy'

# تعديل (مللي ثانية) لجعل بداية/نهاية المقطع المقتطع أكثر طبيعية عند
# الاستماع. حشو البداية أكبر نسبياً لأن حدود المحاذاة الآلية توضع أحياناً
# عند لحظة الصوت المسموع تماماً، فتقتطع بداية الحرف الخفيفة (كبعض
# الهمزات) إن لم يُعطَ هامش كافٍ قبلها. _extract_clip يمنع هذا الحشو من
# التعدي على نهاية الكلمة (أو العبارة) السابقة.
_PAD_START_MS = 130
_PAD_END_MS   = 70

_timing_cache = {}   # {timing_filename: {(surah,ayah): [segments...]}}
_ffmpeg_path  = None
_ffmpeg_checked = False


# ══════════════════════════════════════════════════════════════
#  تحديد مسار ffmpeg (محمول عبر imageio-ffmpeg إن توفرت، وإلا PATH)
# ══════════════════════════════════════════════════════════════
def _find_ffmpeg():
    global _ffmpeg_path, _ffmpeg_checked
    if _ffmpeg_checked:
        return _ffmpeg_path
    _ffmpeg_checked = True
    try:
        import imageio_ffmpeg
        _ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        _ffmpeg_path = shutil.which('ffmpeg')
    return _ffmpeg_path


# ══════════════════════════════════════════════════════════════
#  تحميل ملف توقيت قارئ معيّن (مرة واحدة فقط لكل قارئ، ثم يبقى بالذاكرة)
# ══════════════════════════════════════════════════════════════
def _find_timing_file(base_dir, timing_filename):
    candidates = [
        os.path.join(base_dir, timing_filename),
        os.path.join(os.path.dirname(base_dir), timing_filename),
        r'D:\family\%s' % timing_filename,
        r'E:\family\%s' % timing_filename,
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def _load_timing(base_dir, timing_filename):
    if timing_filename in _timing_cache:
        return _timing_cache[timing_filename]
    path = _find_timing_file(base_dir, timing_filename)
    if not path:
        _timing_cache[timing_filename] = None
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        index = {}
        for item in raw:
            index[(item['surah'], item['ayah'])] = {
                'segments': item['segments'],
                'stats'   : item.get('stats') or {},
            }
        _timing_cache[timing_filename] = index
        return index
    except Exception:
        _timing_cache[timing_filename] = None
        return None


# ══════════════════════════════════════════════════════════════
#  إيجاد مجلد قراءة القارئ المطلوب ضمن قوائم القرّاء الحالية للتطبيق
# ══════════════════════════════════════════════════════════════
def find_reader_dir(readers_dict, reciter_key=DEFAULT_RECITER):
    cfg = RECITERS.get(reciter_key)
    if not cfg or not readers_dict:
        return None
    # أولاً: مطابقة صريحة، بترتيب أولوية known_folders نفسه (الأحدث/الأدق
    # أولاً) — لا بترتيب ظهور المجلدات على القرص، حتى لا يُختار تخمين
    # قديم بالخطأ لمجرد أنه يسبق أبجدياً المجلد الصحيح الجديد.
    for known in cfg['known_folders']:
        if known in readers_dict:
            return readers_dict[known]
    # ثانياً: محاولة تخمين من الاسم (لمشاريع أخرى بأسماء مجلدات واضحة)
    for name, path in readers_dict.items():
        low = name.lower()
        if any(hint.lower() in low for hint in cfg['hints']):
            return path
    return None


def available_reciters():
    """يُرجع قائمة (المفتاح, الاسم المعروض) لكل القرّاء المسجَّلين."""
    return [(k, v['label']) for k, v in RECITERS.items()]


_DECORATIVE_MARKS = '\u06DE\u06E9\u06DD'  # ۞ ۩ ۝

def _strip_decorative_marks(text):
    for ch in _DECORATIVE_MARKS:
        text = text.replace(ch, ' ')
    return text


def _strip_all_diacritics(text):
    """يزيل كل علامات التشكيل (فتحة/ضمة/كسرة/سكون/شدة/تنوين وكل رموز
    القرآن الإضافية) بصرف النظر عن الرمز اليونيكودي الدقيق المستخدم —
    عبر إزالة أي محرف من فئة Unicode 'Mn' (علامة غير متصلة). يُستخدم
    فقط للمقارنة الداخلية (لا للعرض)، لأن اختلاف رمز تشكيل واحد بين
    مصدرين نصيين للقرآن قد يمنع أي مطابقة حرفية أو حتى جزئية."""
    return ''.join(ch for ch in text if unicodedata.category(ch) != 'Mn')


# حروف الرسم العثماني التي تُكتب كعلامة تشكيل صغيرة فوق السطر بدل حرف
# أساسي كامل (الألف الخنجرية، الواو/الياء الصغيرتان، ألف الوصل)، فتختفي
# تماماً عند تجريد التشكيل بدل أن تتحول لحرفها القياسي المقابل — ما يجعل
# "ثَلَٰثَةٞ" (رسم عثماني) و"ثَلَاثَةٌ" (إملاء قياسي) بهيكلين مختلفين
# تماماً رغم كونهما نفس الكلمة. تحويلها لمكافئها القياسي أولاً يحل هذا.
_QURANIC_ORTHOGRAPHY_MAP = {
    '\u0670': '\u0627',  # الألف الخنجرية (ٰ) → ألف قياسية (ا)
    '\u0671': '\u0627',  # ألف الوصل (ٱ) → ألف قياسية (ا)
    '\u06E5': '\u0648',  # واو صغيرة (ۥ) → واو قياسية (و)
    '\u06E6': '\u064A',  # ياء صغيرة (ۦ) → ياء قياسية (ي)
}

def _normalize_orthography(text):
    for special, standard in _QURANIC_ORTHOGRAPHY_MAP.items():
        text = text.replace(special, standard)
    return text


def _skeleton(text):
    """الهيكل النهائي للمقارنة: تطبيع حروف الرسم العثماني أولاً، ثم
    تجريد كل تشكيل — يعالج فروقات الحروف الحقيقية وفروقات التشكيل معاً."""
    return _strip_all_diacritics(_normalize_orthography(text))


def _token_matches(token, word):
    """يقارن كلمة مفردة بتوكن من النص، بنفس مستويات المرونة المستخدمة
    في word_index_in_text (تطابق حرفي، ثم جزئي، ثم هيكل ساكن)."""
    if not token or not word:
        return False
    if token == word:
        return True
    if word in token or token in word:
        return True
    wb, tb = _skeleton(word), _skeleton(token)
    return bool(wb) and wb == tb


def word_pair_indices_adjacent(aya_text, word1, word2):
    """يحدد فهرسي كلمتين متجاورتين (متتاليتين مباشرة) معاً داخل نص
    الآية — أدق بكثير من البحث المستقل عن كل كلمة على حدة عبر
    word_index_in_text، لأن الأخير يلتقط أول ظهور نصي للكلمة في كامل
    الآية بغضّ النظر عن موضعها الصحيح، فإن تكررت الكلمة (كلفظ "مِن"
    مثلاً) في موضع آخر غير مرتبط بالعبارة المقصودة، يبدأ الصوت من
    هناك خطأً. بما أن كلمتَي أي عبارة إخفاء/إدغام/إظهار/إقلاب متجاورتان
    دائماً في النص، البحث عن زوج متجاور يستبعد هذا الالتباس تماماً.
    يُرجع (idx1, idx2) عند النجاح، أو (None, None) إن تعذّر إيجاد زوج
    متجاور (نادر جداً، عندها يلجأ المستدعي للبحث المستقل كحل احتياطي)."""
    if not aya_text or not word1 or not word2:
        return None, None
    clean_text = _strip_decorative_marks(aya_text)
    tokens = [t for t in re.split(r'\s+', clean_text.strip()) if t]
    w1 = _strip_decorative_marks(word1).strip()
    w2 = _strip_decorative_marks(word2).strip()
    for i in range(len(tokens) - 1):
        if _token_matches(tokens[i], w1) and _token_matches(tokens[i + 1], w2):
            return i, i + 1
    return None, None


def get_aya_tokens(aya_text):
    """يُرجع قائمة كلمات الآية (بعد إزالة الرموز الزخرفية فقط، بلا أي
    تعديل آخر) — هذه القائمة تحدّد "فهرس الكلمة" القياسي المستخدم في كل
    دوال هذه الوحدة (0 = أول كلمة، وهكذا). مفيدة لأي واجهة تحتاج تحديد
    مجال كلمات بالفهرس مباشرة (كميزة التحديد بالسحب)."""
    if not aya_text:
        return []
    clean_text = _strip_decorative_marks(aya_text)
    return [t for t in re.split(r'\s+', clean_text.strip()) if t]


# ══════════════════════════════════════════════════════════════
#  حساب موضع الكلمة داخل نص الآية (بالعدّ من الصفر، بالفصل على المسافات)
# ══════════════════════════════════════════════════════════════
def word_index_in_text(aya_text, word):
    if not aya_text or not word:
        return None
    word = _strip_decorative_marks(word).strip()
    clean_text = _strip_decorative_marks(aya_text)
    tokens = [t for t in re.split(r'\s+', clean_text.strip()) if t]
    for i, t in enumerate(tokens):
        if t.strip() == word:
            return i
    for i, t in enumerate(tokens):
        if word in t or t in word:
            return i
    # محاولة أخيرة: مقارنة الهيكل الساكن للحروف بعد تطبيع حروف الرسم
    # العثماني وتجريد كل تشكيل — تعالج فروقات الحروف الحقيقية (كالألف
    # الخنجرية) وفروقات التشكيل الدقيقة معاً
    word_bare = _skeleton(word)
    if word_bare:
        for i, t in enumerate(tokens):
            if _skeleton(t) == word_bare:
                return i
    return None


# عتبة اعتبار مدة المقطع "شاذة" (مللي ثانية) — كلمة عادية نادراً ما
# تتجاوز 3-3.5 ثوانٍ حتى مع مدّ طويل؛ ما يفوق هذا غالباً خطأ محاذاة
# (دمج توقيت كلمة مجاورة خطأً) وليس نطقاً طبيعياً فعلياً لكلمة واحدة.
_SUSPICIOUS_DURATION_MS = 4000

def _get_segment_ms(base_dir, timing_filename, suraid, verseid, word_index):
    timing = _load_timing(base_dir, timing_filename)
    if timing is None:
        return None, f'ملف التوقيت ({timing_filename}) غير موجود بجانب التطبيق.'
    entry = timing.get((int(suraid), int(verseid)))
    if not entry:
        return None, 'لا توجد بيانات توقيت لهذه الآية لدى هذا القارئ.'
    segments = entry['segments']
    prev_end_ms = 0
    for seg in segments:
        idx_start, idx_end, start_ms, end_ms = seg
        if idx_start <= word_index < idx_end:
            warning = None
            if (end_ms - start_ms) > _SUSPICIOUS_DURATION_MS:
                warning = ('⚠ ملاحظة: بيانات توقيت هذه الكلمة لهذا القارئ تبدو غير دقيقة '
                            '(خطأ محاذاة معروف في مصدر البيانات لهذه الآية تحديداً) — '
                            'جرّب قارئاً آخر إن بدا الصوت غير صحيح.')
            return (start_ms, end_ms, prev_end_ms, warning), None
        prev_end_ms = end_ms
    return None, 'تعذّر تحديد توقيت هذه الكلمة بالذات ضمن الآية.'


# ══════════════════════════════════════════════════════════════
#  اقتطاع المقطع الصوتي عبر ffmpeg (مع تخزين مؤقت لتفادي إعادة القصّ)
# ══════════════════════════════════════════════════════════════
def _cache_dir():
    d = os.path.join(tempfile.gettempdir(), 'tajweed_word_clips')
    os.makedirs(d, exist_ok=True)
    return d


def _concat_clips(path1, path2):
    """يدمج مقطعين صوتيين متتاليين في ملف واحد (لعبارات عابرة لسورتين،
    كإقلاب آخر كلمة في سورة مع بداية بسملة السورة التالية)."""
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        return None, ('لم يتم العثور على ffmpeg. ثبّت الحزمة عبر:\n'
                       'pip install imageio-ffmpeg\nثم أعِد المحاولة.')
    key = f'concat_{path1}_{path2}'
    out_path = os.path.join(_cache_dir(), hashlib.md5(key.encode()).hexdigest() + '_merged.mp3')
    if os.path.exists(out_path):
        return out_path, None
    try:
        cmd = [
            ffmpeg, '-y', '-i', path1, '-i', path2,
            '-filter_complex', '[0:a][1:a]concat=n=2:v=0:a=1[out]',
            '-map', '[out]', '-acodec', 'libmp3lame', '-ar', '44100', '-q:a', '2',
            out_path,
        ]
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        if r.returncode != 0 or not os.path.exists(out_path):
            return None, f'فشل دمج المقطعين:\n{r.stderr.decode(errors="ignore")[:200]}'
        return out_path, None
    except Exception as e:
        return None, f'فشل دمج المقطعين:\n{e}'


def _extract_clip(source_mp3, start_ms, end_ms, prev_end_ms=0):
    """يُرجع (المسار, s0, المدة_بالمللي_ثانية, رسالة_خطأ). عند النجاح:
    رسالة_خطأ=None. s0 هو نقطة البداية الفعلية التي بدأ منها الاقتطاع
    من الملف الأصلي — لازمة لحساب مواضع الكلمات نسبياً داخل الناتج."""
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        return None, None, None, ('لم يتم العثور على ffmpeg. ثبّت الحزمة عبر:\n'
                                   'pip install imageio-ffmpeg\nثم أعِد المحاولة.')
    safe_floor = prev_end_ms + 5 if prev_end_ms else 0
    s0 = max(safe_floor, start_ms - _PAD_START_MS, 0)
    e0 = end_ms + _PAD_END_MS
    duration_ms = e0 - s0
    # المفتاح يعتمد على المسار الكامل (لا اسم الملف فقط)، لأن كل مجلدات
    # القرّاء تحتوي ملفات بنفس التسمية (008041.mp3 مثلاً) — الاعتماد على
    # اسم الملف فقط كان قد يُرجع مقطعاً مخزَّناً مسبقاً من قارئ مختلف.
    key = f'{source_mp3}_{s0}_{e0}'
    out_path = os.path.join(_cache_dir(), hashlib.md5(key.encode()).hexdigest() + '.mp3')
    if os.path.exists(out_path):
        return out_path, s0, duration_ms, None
    try:
        cmd = [
            ffmpeg, '-y', '-ss', f'{s0/1000:.3f}',
            '-i', source_mp3, '-t', f'{(e0-s0)/1000:.3f}',
            '-acodec', 'libmp3lame', '-ar', '44100', '-q:a', '2',
            out_path,
        ]
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=15)
        if r.returncode != 0 or not os.path.exists(out_path):
            return None, None, None, f'فشل اقتطاع المقطع الصوتي:\n{r.stderr.decode(errors="ignore")[:200]}'
        return out_path, s0, duration_ms, None
    except Exception as e:
        return None, None, None, f'فشل اقتطاع المقطع الصوتي:\n{e}'


def _resolve_source(base_dir, readers_dict, reciter_key, suraid, verseid):
    cfg = RECITERS.get(reciter_key)
    if not cfg:
        return None, f'قارئ غير معروف: {reciter_key}'
    reader_dir = find_reader_dir(readers_dict, reciter_key)
    if not reader_dir:
        names = '، '.join(readers_dict.keys()) if readers_dict else '(لا يوجد أي قارئ مكتشف إطلاقاً)'
        return None, (f'لم أجد مجلد قراءة {cfg["label"]} ضمن مجلدات القرّاء لديك.\n'
                       f'المجلدات المكتشفة فعلياً: {names}')
    source_mp3 = os.path.join(reader_dir, f'{int(suraid):03d}{int(verseid):03d}.mp3')
    if not os.path.exists(source_mp3):
        return None, f'ملف الآية الصوتي غير موجود لدى {cfg["label"]}:\n{os.path.basename(source_mp3)}'
    return (source_mp3, cfg['timing_file']), None


# ══════════════════════════════════════════════════════════════
#  الدوال الرئيسية المستخدَمة من التطبيقات الأخرى
# ══════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════
#  الدوال "العارية" (لا تعتمد PyQt6 إطلاقاً) — تُجهّز المقطع الصوتي
#  وتُرجع مساره فقط دون تشغيله. تصلح لأي بيئة: تطبيق PyQt6 سطح مكتب،
#  أو خادم Flask/ويب (يُرسل الملف عبر send_file ويشغّله المتصفح).
# ══════════════════════════════════════════════════════════════
def prepare_word_clip(base_dir, readers_dict, suraid, verseid, aya_text, word,
                       reciter_key=DEFAULT_RECITER):
    """يجهّز مقطع كلمة واحدة. عند النجاح: (مسار_الملف, تحذير_أو_فارغ).
    عند الفشل: (None, 'رسالة خطأ')."""
    resolved, err = _resolve_source(base_dir, readers_dict, reciter_key, suraid, verseid)
    if err:
        return None, err
    source_mp3, timing_filename = resolved

    idx = word_index_in_text(aya_text, word)
    if idx is None:
        return None, 'تعذّر إيجاد موضع هذه الكلمة داخل نص الآية.'

    times, err = _get_segment_ms(base_dir, timing_filename, suraid, verseid, idx)
    if err:
        return None, err
    start_ms, end_ms, prev_end_ms, warning = times

    clip_path, s0, dur_ms, err = _extract_clip(source_mp3, start_ms, end_ms, prev_end_ms)
    if err:
        return None, err
    return clip_path, (warning or '')


def prepare_phrase_clip(base_dir, readers_dict, suraid, verseid, aya_text, words,
                         reciter_key=DEFAULT_RECITER):
    """يجهّز مقطع عبارة من كلمتين (بترتيب ورودهما الفعلي في الآية).
    عند النجاح: (مسار_الملف, معلومات_قاموس {'first_word','second_word',
    'switch_at_ms','warning'}). عند الفشل: (None, 'رسالة خطأ')."""
    if not words or len(words) < 2:
        return None, 'هذه الحالة لا تحتوي كلمتين مرتبطتين.'

    resolved, err = _resolve_source(base_dir, readers_dict, reciter_key, suraid, verseid)
    if err:
        return None, err
    source_mp3, timing_filename = resolved

    # أولاً: نبحث عن الكلمتين متجاورتين معاً (الأدق — يستبعد التقاط
    # تكرار خاطئ لإحدى الكلمتين في موضع آخر غير مرتبط من نفس الآية،
    # كتكرار "مِن" مرتين في آية واحدة مثلاً)
    idx_a, idx_b = word_pair_indices_adjacent(aya_text, words[0], words[-1])
    if idx_a is not None:
        idx1, word1 = idx_a, words[0]
        idx2, word2 = idx_b, words[-1]
    else:
        # محاولة بالترتيب المعكوس (لو مرَّرها المستدعي بترتيب غير متوقَّع):
        # هنا words[-1] هو الأسبق فعلياً في النص، وwords[0] هو التالي له
        earlier_idx, later_idx = word_pair_indices_adjacent(aya_text, words[-1], words[0])
        if earlier_idx is not None:
            idx1, word1 = earlier_idx, words[-1]
            idx2, word2 = later_idx, words[0]
        else:
            # حل احتياطي (نادر الحدوث): بحث مستقل عن كل كلمة على حدة
            pairs = []  # [(index, word), ...]
            for w in words:
                idx = word_index_in_text(aya_text, w)
                if idx is None:
                    return None, f'تعذّر إيجاد موضع الكلمة "{w}" داخل نص الآية.'
                pairs.append((idx, w))
            pairs.sort(key=lambda p: p[0])  # ترتيب حسب الورود الفعلي في الآية
            (idx1, word1), (idx2, word2) = pairs[0], pairs[-1]

    times1, err = _get_segment_ms(base_dir, timing_filename, suraid, verseid, idx1)
    if err:
        return None, err
    times2, err = _get_segment_ms(base_dir, timing_filename, suraid, verseid, idx2)
    if err:
        return None, err

    start_ms      = times1[0]
    prev_end_ms   = times1[2]
    end_ms        = times2[1]

    clip_path, s0, dur_ms, err = _extract_clip(source_mp3, start_ms, end_ms, prev_end_ms)
    if err:
        return None, err

    switch_at_ms = max(0, times2[0] - s0)
    warning = times1[3] or times2[3]
    return clip_path, {
        'first_word'  : word1,
        'second_word' : word2,
        'switch_at_ms': switch_at_ms,
        'warning'     : warning,
    }


def prepare_range_clip(base_dir, readers_dict, suraid, verseid, aya_text,
                        start_index, end_index, reciter_key=DEFAULT_RECITER):
    """يجهّز مقطعاً صوتياً لمجال كلمات متتالية محدَّد بفهرسَي البداية
    والنهاية (شاملَين، 0 = أول كلمة في الآية — استخدم get_aya_tokens
    لمعرفة الفهارس)، من كلمة واحدة فقط حتى الآية كاملة. مخصَّصة لميزة
    "التحديد بالسحب" (اختيار مجال حر بدل كلمة أو عبارة ثابتة).

    عند النجاح: (مسار_الملف, معلومات_قاموس):
        {'word_timings': [{'word':.., 'start_ms':.., 'end_ms':..}, ...],
         'warning': تحذير دقة إن وُجد}
    حيث start_ms/end_ms لكل كلمة نسبيّان لبداية المقطع الناتج نفسه
    (لا لبداية الآية الأصلية) — يستخدمها المستدعي للتتبّع اللحظي عبر
    عدة كلمات مهما طال المجال.
    عند الفشل: (None, 'رسالة خطأ')."""
    tokens = get_aya_tokens(aya_text)
    if not tokens:
        return None, 'تعذّر قراءة نص الآية.'
    if start_index is None or end_index is None or start_index > end_index:
        return None, 'مجال كلمات غير صالح.'
    start_index = max(0, start_index)
    end_index   = min(len(tokens) - 1, end_index)

    resolved, err = _resolve_source(base_dir, readers_dict, reciter_key, suraid, verseid)
    if err:
        return None, err
    source_mp3, timing_filename = resolved

    times_start, err = _get_segment_ms(base_dir, timing_filename, suraid, verseid, start_index)
    if err:
        return None, err
    times_end, err = _get_segment_ms(base_dir, timing_filename, suraid, verseid, end_index)
    if err:
        return None, err

    start_ms    = times_start[0]
    prev_end_ms = times_start[2]
    end_ms      = times_end[1]

    clip_path, s0, dur_ms, err = _extract_clip(source_mp3, start_ms, end_ms, prev_end_ms)
    if err:
        return None, err

    # توقيت كل كلمة على حدة نسبياً داخل المقطع الناتج (للتتبّع اللحظي)
    timing = _load_timing(base_dir, timing_filename)
    entry  = timing.get((int(suraid), int(verseid))) if timing else None
    segments = entry['segments'] if entry else []
    any_warning = times_start[3] or times_end[3]

    word_timings = []
    for idx in range(start_index, end_index + 1):
        seg = next((s for s in segments if s[0] <= idx < s[1]), None)
        w_text = tokens[idx] if idx < len(tokens) else ''
        if seg:
            rel_start = max(0, seg[2] - s0)
            rel_end   = max(0, seg[3] - s0)
            if (seg[3] - seg[2]) > _SUSPICIOUS_DURATION_MS:
                any_warning = any_warning or (
                    '⚠ ملاحظة: بيانات توقيت إحدى كلمات هذا المجال لهذا القارئ تبدو '
                    'غير دقيقة — جرّب قارئاً آخر إن بدا الصوت غير صحيح.')
        else:
            rel_start = rel_end = None
        word_timings.append({'word': w_text, 'start_ms': rel_start, 'end_ms': rel_end})

    return clip_path, {
        'word_timings': word_timings,
        'warning'     : any_warning,
        'duration_ms' : dur_ms,
    }


def play_range_pronunciation(player, audio_out, base_dir, readers_dict,
                              suraid, verseid, aya_text, start_index, end_index,
                              reciter_key=DEFAULT_RECITER):
    """غلاف PyQt6 حول prepare_range_clip — يشغّل المقطع فعلياً عبر
    QMediaPlayer. نفس قيم الإرجاع، إلا أن النجاح (True, معلومات) بدل
    (مسار_الملف, معلومات)."""
    if not _PYQT_OK:
        return False, 'PyQt6 غير متوفر في هذه البيئة.'
    clip_path, info = prepare_range_clip(base_dir, readers_dict, suraid, verseid,
                                          aya_text, start_index, end_index, reciter_key)
    if not clip_path:
        return False, info
    player.setSource(QUrl.fromLocalFile(clip_path))
    player.play()
    return True, info


def prepare_cross_verse_clip(base_dir, readers_dict,
                              suraid1, verseid1, aya_text1, word1,
                              suraid2, verseid2, aya_text2, word2_start, word2_end,
                              reciter_key=DEFAULT_RECITER):
    """يجهّز مقطعاً مدموجاً: كلمة من آية معيّنة متبوعة بكلمة/مدى كلمات من
    آية أخرى تماماً (حتى لو سورة مختلفة). عند النجاح: (مسار_الملف,
    معلومات_قاموس). عند الفشل: (None, 'رسالة خطأ')."""
    resolved1, err = _resolve_source(base_dir, readers_dict, reciter_key, suraid1, verseid1)
    if err:
        return None, err
    src1, timing_file1 = resolved1

    idx1 = word_index_in_text(aya_text1, word1)
    if idx1 is None:
        return None, f'تعذّر إيجاد موضع الكلمة "{word1}" داخل الآية الأولى.'
    t1, err = _get_segment_ms(base_dir, timing_file1, suraid1, verseid1, idx1)
    if err:
        return None, err
    clip1, s0_1, dur1_ms, err = _extract_clip(src1, t1[0], t1[1], t1[2])
    if err:
        return None, err

    resolved2, err = _resolve_source(base_dir, readers_dict, reciter_key, suraid2, verseid2)
    if err:
        return None, err
    src2, timing_file2 = resolved2

    idxA = word_index_in_text(aya_text2, word2_start)
    idxB = word_index_in_text(aya_text2, word2_end)
    if idxA is None or idxB is None:
        return None, 'تعذّر إيجاد موضع الكلمة الثانية داخل آيتها.'
    lo, hi = min(idxA, idxB), max(idxA, idxB)
    tA, err = _get_segment_ms(base_dir, timing_file2, suraid2, verseid2, lo)
    if err:
        return None, err
    tB, err = _get_segment_ms(base_dir, timing_file2, suraid2, verseid2, hi)
    if err:
        return None, err
    clip2, s0_2, dur2_ms, err = _extract_clip(src2, tA[0], tB[1], tA[2])
    if err:
        return None, err

    merged, err = _concat_clips(clip1, clip2)
    if err:
        return None, err

    return merged, {
        'first_word'  : word1,
        'second_word' : (word2_start if word2_start == word2_end
                          else f'{word2_start} … {word2_end}'),
        'switch_at_ms': dur1_ms,
        'warning'     : t1[3] or tA[3] or tB[3],
    }


def prepare_cross_verse_range_clip(base_dir, readers_dict,
                                    suraid1, verseid1, aya_text1, idx1_start, idx1_end,
                                    suraid2, verseid2, aya_text2, idx2_start, idx2_end,
                                    reciter_key=DEFAULT_RECITER):
    """توسيع لـ prepare_cross_verse_clip: بدل كلمة واحدة ثابتة من كل
    جانب، يقبل مدى كلمات (بالفهرس) من الآية الأولى ومدى كلمات من
    الآية الثانية معاً، ويدمجهما في مقطع صوتي واحد متصل. مخصَّصة لميزة
    "التحديد بالسحب" حين يمتد التحديد من داخل الآية الحالية إلى داخل
    الآية التالية (حالات 'بين آيتين').

    عند النجاح: (مسار_الملف, معلومات_قاموس):
        {'word_timings': [...],  # نفس صيغة prepare_range_clip، مدمَجة
                                  # من الجزأين بترتيب متتالٍ
         'switch_at_ms': نقطة الانتقال بين الآيتين داخل المقطع الناتج,
         'warning': تحذير دقة إن وُجد}
    عند الفشل: (None, 'رسالة خطأ')."""
    clip1, info1 = prepare_range_clip(base_dir, readers_dict, suraid1, verseid1,
                                       aya_text1, idx1_start, idx1_end, reciter_key)
    if not clip1:
        return None, info1  # info1 هنا رسالة خطأ

    clip2, info2 = prepare_range_clip(base_dir, readers_dict, suraid2, verseid2,
                                       aya_text2, idx2_start, idx2_end, reciter_key)
    if not clip2:
        return None, info2

    merged, err = _concat_clips(clip1, clip2)
    if err:
        return None, err

    switch_at_ms = info1.get('duration_ms') or 0
    word_timings = list(info1['word_timings'])
    for wt in info2['word_timings']:
        shifted = dict(wt)
        if shifted['start_ms'] is not None:
            shifted['start_ms'] = shifted['start_ms'] + switch_at_ms
        if shifted['end_ms'] is not None:
            shifted['end_ms'] = shifted['end_ms'] + switch_at_ms
        word_timings.append(shifted)

    return merged, {
        'word_timings': word_timings,
        'switch_at_ms': switch_at_ms,
        'warning'     : info1.get('warning') or info2.get('warning'),
    }


# ══════════════════════════════════════════════════════════════
#  أغلفة PyQt6 (تطبيقات سطح المكتب) — تستدعي الدوال العارية أعلاه ثم
#  تُشغِّل الناتج فعلياً عبر QMediaPlayer. هذه هي الدوال التي تستخدمها
#  تطبيقات PyQt6 الحالية؛ سلوكها لم يتغيّر إطلاقاً عن ذي قبل.
# ══════════════════════════════════════════════════════════════
def play_word_pronunciation(player, audio_out, base_dir, readers_dict,
                             suraid, verseid, aya_text, word,
                             reciter_key=DEFAULT_RECITER):
    """يشغّل نطق كلمة واحدة فقط. يُرجع (True, '') عند النجاح، أو
    (False, 'رسالة توضيحية') عند الفشل."""
    if not _PYQT_OK:
        return False, 'PyQt6 غير متوفر في هذه البيئة.'
    clip_path, info = prepare_word_clip(base_dir, readers_dict, suraid, verseid,
                                         aya_text, word, reciter_key)
    if not clip_path:
        return False, info
    player.setSource(QUrl.fromLocalFile(clip_path))
    player.play()
    return True, (info or '')


def play_phrase_pronunciation(player, audio_out, base_dir, readers_dict,
                               suraid, verseid, aya_text, words,
                               reciter_key=DEFAULT_RECITER):
    """يشغّل عبارة من كلمتين متتاليتين معاً كمقطع صوتي واحد متواصل.
    عند النجاح يُرجع (True, معلومات) حيث "معلومات" قاموس:
        {'first_word': ..., 'second_word': ...,
         'switch_at_ms': نقطة الانتقال بالمللي ثانية داخل المقطع الناتج}
    يستخدمها المستدعي لتظليل الكلمة الجاري نطقها (تتبّع لحظي) عبر ربطها
    بإشارة QMediaPlayer.positionChanged.
    عند الفشل يُرجع (False, 'رسالة توضيحية')."""
    if not _PYQT_OK:
        return False, 'PyQt6 غير متوفر في هذه البيئة.'
    clip_path, info = prepare_phrase_clip(base_dir, readers_dict, suraid, verseid,
                                           aya_text, words, reciter_key)
    if not clip_path:
        return False, info
    player.setSource(QUrl.fromLocalFile(clip_path))
    player.play()
    return True, info


def play_cross_verse_phrase(player, audio_out, base_dir, readers_dict,
                             suraid1, verseid1, aya_text1, word1,
                             suraid2, verseid2, aya_text2, word2_start, word2_end,
                             reciter_key=DEFAULT_RECITER):
    """يشغّل كلمة واحدة من آية معيّنة، متبوعة مباشرة (كمقطع واحد مدموج)
    بكلمة أو مدى كلمات من آية أخرى تماماً — حتى لو من سورة مختلفة كلياً.
    مخصّصة لحالات مثل: آخر كلمة إقلاب في سورة + بداية بسملة السورة
    التالية (سورة الفاتحة، الآية ١)، أو + أول كلمة من سورة التوبة.

    word2_start/word2_end: نفس الكلمة إن كان المطلوب كلمة واحدة فقط من
    الآية الثانية، أو أول/آخر كلمة من مدى إن كان المطلوب عدة كلمات
    متتالية (كامل آية البسملة مثلاً).

    عند النجاح يُرجع (True, معلومات) بنفس صيغة play_phrase_pronunciation.
    عند الفشل يُرجع (False, 'رسالة توضيحية')."""
    if not _PYQT_OK:
        return False, 'PyQt6 غير متوفر في هذه البيئة.'
    clip_path, info = prepare_cross_verse_clip(
        base_dir, readers_dict, suraid1, verseid1, aya_text1, word1,
        suraid2, verseid2, aya_text2, word2_start, word2_end, reciter_key)
    if not clip_path:
        return False, info
    player.setSource(QUrl.fromLocalFile(clip_path))
    player.play()
    return True, info


def play_cross_verse_range(player, audio_out, base_dir, readers_dict,
                            suraid1, verseid1, aya_text1, idx1_start, idx1_end,
                            suraid2, verseid2, aya_text2, idx2_start, idx2_end,
                            reciter_key=DEFAULT_RECITER):
    """يشغّل مدى كلمات من آية معيّنة متبوعاً مباشرة بمدى كلمات من آية
    تالية تماماً (كمقطع واحد مدموج) — نسخة عامة من play_cross_verse_phrase
    تدعم أكثر من كلمة واحدة من كل جانب، لميزة التحديد بالسحب حين يمتد
    المجال المُحدَّد عبر حدود الآية.
    عند النجاح يُرجع (True, معلومات) بنفس صيغة play_range_pronunciation
    (تحتوي أيضاً 'switch_at_ms'). عند الفشل: (False, 'رسالة توضيحية')."""
    if not _PYQT_OK:
        return False, 'PyQt6 غير متوفر في هذه البيئة.'
    clip_path, info = prepare_cross_verse_range_clip(
        base_dir, readers_dict, suraid1, verseid1, aya_text1, idx1_start, idx1_end,
        suraid2, verseid2, aya_text2, idx2_start, idx2_end, reciter_key)
    if not clip_path:
        return False, info
    player.setSource(QUrl.fromLocalFile(clip_path))
    player.play()
    return True, info


# ══════════════════════════════════════════════════════════════
#  تشخيص مباشر: شغّل هذا الملف وحده لمعرفة أسماء مجلدات القرّاء
#  المكتشفة فعلياً، ومكان ملفات التوقيت، دون الحاجة لتشغيل أي تطبيق.
#  الاستخدام:  python word_audio_helper.py
# ══════════════════════════════════════════════════════════════
def _self_test():
    print('=' * 60)
    print('تشخيص word_audio_helper.py')
    print('=' * 60)

    here = os.path.dirname(os.path.abspath(__file__))
    search_roots = list(dict.fromkeys([here, r'D:\family', r'E:\family']))

    print('\n[1] البحث عن مجلدات تحتوي ملفات mp3 (مجلدات القرّاء):')
    found = {}
    for root in search_roots:
        if not os.path.exists(root):
            print(f'    - {root}  → غير موجود')
            continue
        print(f'    - {root}  → موجود، جارٍ الفحص...')
        try:
            for name in sorted(os.listdir(root)):
                full = os.path.join(root, name)
                if os.path.isdir(full):
                    mp3s = [f for f in os.listdir(full) if f.lower().endswith('.mp3')]
                    if mp3s and name not in found:
                        found[name] = full
                        print(f'        ✓ وجدت مجلداً: "{name}"   ({len(mp3s)} ملف mp3)   [{full}]')
        except Exception as e:
            print(f'        ⚠ خطأ أثناء القراءة: {e}')

    if not found:
        print('\n    ⚠ لم يُعثر على أي مجلد قراءة يحتوي ملفات mp3.')
        print('      تأكد أنك تشغّل هذا الملف من نفس مجلد باقي التطبيق،')
        print('      أو أن D:\\family موجود فعلياً على هذا الجهاز.')

    print('\n[2] مطابقة القرّاء المدعومين:')
    for key, cfg in RECITERS.items():
        match = find_reader_dir(found, key)
        if match:
            print(f'    ✓ {cfg["label"]}  →  "{match}"')
        else:
            print(f'    ✗ {cfg["label"]}  →  لم يُعثر على مطابقة')

    print('\n[3] ملفات التوقيت:')
    for key, cfg in RECITERS.items():
        tpath = _find_timing_file(here, cfg['timing_file'])
        if tpath:
            print(f'    ✓ {cfg["timing_file"]}  →  موجود في: {tpath}')
        else:
            print(f'    ✗ {cfg["timing_file"]}  →  غير موجود')

    print('\n[4] برنامج ffmpeg (للاقتطاع):')
    fpath = _find_ffmpeg()
    if fpath:
        print(f'    ✓ متوفر عبر: {fpath}')
    else:
        print('    ✗ غير متوفر. شغّل: pip install imageio-ffmpeg')

    print('\n' + '=' * 60)


if __name__ == '__main__':
    _self_test()
