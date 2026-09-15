"""
convert_to_blueprint.py
══════════════════════════════════════════════════════════════════
يحوّل ملف تطبيق Flask مستقل (Flask(__name__) + منفذ خاص) إلى Blueprint
قابل للتركيب ضمن التطبيق الموحَّد — بأقل تعديل ممكن، وبلا لمس أي منطق
داخلي (استعلامات، JS، HTML) إطلاقاً. يُستخدَم مرة واحدة لكل تطبيق عند
الدمج، وليس جزءاً من السويطة النهائية نفسها.

خطوات التحويل:
  1. app = Flask(__name__)              → bp = Blueprint(name, __name__)
  2. كل @app.route(...)                 → @bp.route(...)
  3. @bp.route('/')  (الصفحة الرئيسية)  → @bp.route(home_path)
  4. حذف @bp.route('/api/readers') و @bp.route('/audio/<reader>/<fname>')
     بالكامل (يوفّرهما التطبيق الموحَّد مرة واحدة فقط، بنفس المسارين
     المطلقين، فتبقى كل استدعاءات JavaScript كما هي دون أي تعديل)
  5. حذف كتلة `if __name__ == '__main__': ... run/app.run(...)` بالكامل
     (يُشغَّل الخادم مرة واحدة فقط من التطبيق الموحَّد)
"""
import re


def convert(src, bp_name, home_path):
    # 1) الاستيراد: نضيف Blueprint إن لم يكن مستورداً
    if 'Blueprint' not in src.split('\n', 20)[0:20].__str__():
        src = re.sub(
            r'from flask import Flask(,\s*)',
            r'from flask import Flask, Blueprint\1',
            src, count=1,
        )

    # 2) app = Flask(__name__)  →  bp = Blueprint(name, __name__)
    src = re.sub(
        r'^app = Flask\(__name__\)\s*$',
        f"bp = Blueprint('{bp_name}', __name__)",
        src, count=1, flags=re.M,
    )

    # 3) كل @app.route → @bp.route  (وكل استخدام آخر لاسم app كمتغيّر الديكوريتر فقط)
    src = src.replace('@app.route(', '@bp.route(')

    # 4) الصفحة الرئيسية: '/' → المسار المميّز لهذا الحكم
    src = re.sub(
        r"@bp\.route\('/'\)\ndef index\(\):",
        f"@bp.route('{home_path}')\ndef index():",
        src, count=1,
    )

    # 5) حذف مسار القرّاء المكرَّر (يوفّره التطبيق الموحَّد مرة واحدة)
    src = re.sub(
        r"@bp\.route\('/api/readers'\)\ndef api_readers\(\):\n(?:.*\n)*?    return jsonify\(readers\)\n\n",
        '', src, count=1,
    )

    # 6) حذف مسار تشغيل الصوت المكرَّر (نفسه لكل التطبيقات)
    src = re.sub(
        r"@bp\.route\('/audio/<reader>/<fname>'\)\ndef serve_audio\(reader, fname\):\n(?:.*\n)*?    return '', 404\n\n",
        '', src, count=1,
    )

    # 7) حذف كتلة تشغيل الخادم المستقل (لم تعد لازمة داخل التطبيق الموحَّد)
    src = re.sub(
        r"\nif __name__ == '__main__':\n(?:.*\n)*$",
        '\n', src,
    )

    return src


if __name__ == '__main__':
    import sys
    src_path, out_path, bp_name, home_path = sys.argv[1:5]
    with open(src_path, encoding='utf-8') as f:
        src = f.read()
    out = convert(src, bp_name, home_path)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(out)
    print(f'✅ {src_path} → {out_path}  (blueprint: {bp_name}, path: {home_path})')
