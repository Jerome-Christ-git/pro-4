import os
import json
import uuid
import datetime
import traceback
from flask import Flask, render_template, request, jsonify, make_response
from werkzeug.utils import secure_filename
from utils.transcriber import transcribe_file, check_dependencies
from utils.exporter import export_txt, export_pdf, export_srt, export_docx
from utils.translator import translate_text

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500 MB
app.config['UPLOAD_FOLDER']        = 'uploads'
app.config['TRANSCRIPTIONS_FOLDER'] = 'transcriptions'
app.secret_key = os.environ.get('SECRET_KEY', 'subtitle-assistant-secret-2024')

ALLOWED_EXTENSIONS = {
    'mp3','mp4','wav','m4a','ogg','webm','flac',
    'mpeg','mpga','mkv','avi','mov'
}

os.makedirs(app.config['UPLOAD_FOLDER'],        exist_ok=True)
os.makedirs(app.config['TRANSCRIPTIONS_FOLDER'], exist_ok=True)


# ── Global error handler — ALWAYS returns JSON ───────────────────────────────
@app.errorhandler(Exception)
def handle_exception(e):
    """Catch-all: prevents Flask from returning an HTML error page."""
    tb = traceback.format_exc()
    print(f"[ERROR] Unhandled exception:\n{tb}")
    return jsonify({'error': str(e)}), 500

@app.errorhandler(413)
def too_large(e):
    return jsonify({'error': 'File too large (max 500 MB)'}), 413


# ── Helpers ───────────────────────────────────────────────────────────────────

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def save_session(sid, data):
    path = os.path.join(app.config['TRANSCRIPTIONS_FOLDER'], f'{sid}.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_session(sid):
    path = os.path.join(app.config['TRANSCRIPTIONS_FOLDER'], f'{sid}.json')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def list_sessions():
    sessions = []
    folder = app.config['TRANSCRIPTIONS_FOLDER']
    for fname in sorted(os.listdir(folder), reverse=True):
        if fname.endswith('.json'):
            sid = fname[:-5]
            try:
                with open(os.path.join(folder, fname), 'r', encoding='utf-8') as f:
                    data = json.load(f)
                sessions.append({
                    'id':         sid,
                    'title':      data.get('title', 'Untitled'),
                    'date':       data.get('date', ''),
                    'mode':       data.get('mode', 'live'),
                    'language':   data.get('detected_language', 'Unknown'),
                    'word_count': len(data.get('text', '').split()),
                    'backend':    data.get('backend', '')
                })
            except Exception:
                pass
    return sessions


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/history')
def history():
    sessions = list_sessions()
    return render_template('history.html', sessions=sessions)


@app.route('/session/<sid>')
def view_session(sid):
    session = load_session(sid)
    if not session:
        return 'Session not found', 404
    return render_template('session.html', session=session)


# ── Dependency check ──────────────────────────────────────────────────────────

@app.route('/api/check-deps')
def check_deps():
    """Check which transcription backends are available."""
    deps = check_dependencies()

    # Determine which backend will be used
    if deps['whisper'] and deps['torch']:
        active = 'whisper'
        msg = 'Whisper AI ready ✓'
    elif deps['speech_recognition'] and deps['pydub'] and deps['ffmpeg']:
        active = 'speech_recognition'
        msg = 'SpeechRecognition + Google API ready ✓'
    elif deps['speech_recognition']:
        active = 'speech_recognition_wav'
        msg = 'SpeechRecognition ready (WAV files only — install ffmpeg for other formats)'
    else:
        active = 'none'
        msg = 'No transcription backend available! Run: pip install openai-whisper'

    return jsonify({'deps': deps, 'active_backend': active, 'message': msg})


# ── File transcription ────────────────────────────────────────────────────────

@app.route('/api/transcribe-file', methods=['POST'])
def transcribe_file_route():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not allowed_file(file.filename):
        exts = ', '.join(sorted(ALLOWED_EXTENSIONS))
        return jsonify({'error': f'Unsupported format. Allowed: {exts}'}), 400

    model_size  = request.form.get('model', 'base')
    target_lang = request.form.get('target_lang', '')

    filename  = secure_filename(file.filename)
    uid       = uuid.uuid4().hex[:8]
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], f'{uid}_{filename}')
    file.save(save_path)

    try:
        result = transcribe_file(save_path, model_size=model_size)
    except RuntimeError as e:
        # User-friendly error from transcriber
        _safe_remove(save_path)
        return jsonify({'error': str(e)}), 422
    except Exception as e:
        _safe_remove(save_path)
        tb = traceback.format_exc()
        print(f"[transcribe_file_route] Unexpected error:\n{tb}")
        return jsonify({'error': f'Unexpected error: {e}'}), 500

    _safe_remove(save_path)

    original_text   = result.get('text', '').strip()
    segments        = result.get('segments', [])
    detected_lang   = result.get('language', 'unknown')
    backend_used    = result.get('backend', '')

    if not original_text:
        return jsonify({
            'error': 'No speech detected in the file. '
                     'Make sure the file contains clear audio speech.'
        }), 422

    # Optional translation
    translated_text = ''
    if target_lang and target_lang not in ('original', detected_lang, ''):
        try:
            translated_text = translate_text(original_text, source=detected_lang, target=target_lang)
        except Exception as e:
            translated_text = f'[Translation error: {e}]'

    display_text = translated_text if (target_lang and translated_text and target_lang != 'original') \
                   else original_text

    sid = uuid.uuid4().hex
    session_data = {
        'id':                sid,
        'title':             filename,
        'date':              datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
        'mode':              'file',
        'text':              display_text,
        'original_text':     original_text,
        'translated_text':   translated_text,
        'detected_language': detected_lang,
        'target_language':   target_lang,
        'segments':          segments,
        'filename':          filename,
        'backend':           backend_used,
    }
    save_session(sid, session_data)

    return jsonify({
        'success':           True,
        'sid':               sid,
        'text':              display_text,
        'original_text':     original_text,
        'translated_text':   translated_text,
        'detected_language': detected_lang,
        'segments':          segments,
        'backend':           backend_used,
    })


# ── Live session save ─────────────────────────────────────────────────────────

@app.route('/api/save-live', methods=['POST'])
def save_live():
    data = request.get_json(silent=True) or {}
    text = data.get('text', '').strip()
    if not text:
        return jsonify({'error': 'No text to save'}), 400

    sid = uuid.uuid4().hex
    session_data = {
        'id':                sid,
        'title':             data.get('title', f'Live Session {datetime.datetime.now().strftime("%H:%M")}'),
        'date':              datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
        'mode':              'live',
        'text':              text,
        'original_text':     text,
        'translated_text':   data.get('translated_text', ''),
        'detected_language': data.get('detected_language', 'unknown'),
        'target_language':   data.get('target_language', ''),
        'segments':          [],
        'backend':           'web_speech_api',
    }
    save_session(sid, session_data)
    return jsonify({'success': True, 'sid': sid})


# ── Translation ───────────────────────────────────────────────────────────────

@app.route('/api/translate', methods=['POST'])
def translate_route():
    data   = request.get_json(silent=True) or {}
    text   = data.get('text', '').strip()
    source = data.get('source', 'auto')
    target = data.get('target', 'en')

    if not text:
        return jsonify({'error': 'No text provided'}), 400

    try:
        translated = translate_text(text, source=source, target=target)
        return jsonify({'success': True, 'translated': translated})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Delete session ────────────────────────────────────────────────────────────

@app.route('/api/delete/<sid>', methods=['DELETE'])
def delete_session(sid):
    path = os.path.join(app.config['TRANSCRIPTIONS_FOLDER'], f'{sid}.json')
    if os.path.exists(path):
        os.remove(path)
        return jsonify({'success': True})
    return jsonify({'error': 'Session not found'}), 404


# ── Download ──────────────────────────────────────────────────────────────────

@app.route('/download/<sid>/<fmt>')
def download(sid, fmt):
    session = load_session(sid)
    if not session:
        return 'Session not found', 404

    text      = session.get('text', '')
    title     = session.get('title', 'transcription')
    segments  = session.get('segments', [])
    safe_name = secure_filename(title.rsplit('.', 1)[0] if '.' in title else title) or 'transcription'

    try:
        if fmt == 'txt':
            content = export_txt(text, session)
            resp = make_response(content)
            resp.headers['Content-Type']        = 'text/plain; charset=utf-8'
            resp.headers['Content-Disposition'] = f'attachment; filename="{safe_name}.txt"'
            return resp

        elif fmt == 'pdf':
            pdf_bytes = export_pdf(text, session)
            resp = make_response(pdf_bytes)
            resp.headers['Content-Type']        = 'application/pdf'
            resp.headers['Content-Disposition'] = f'attachment; filename="{safe_name}.pdf"'
            return resp

        elif fmt == 'srt':
            content = export_srt(segments, text)
            resp = make_response(content)
            resp.headers['Content-Type']        = 'text/plain; charset=utf-8'
            resp.headers['Content-Disposition'] = f'attachment; filename="{safe_name}.srt"'
            return resp

        elif fmt == 'docx':
            docx_bytes = export_docx(text, session)
            resp = make_response(docx_bytes)
            resp.headers['Content-Type']        = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            resp.headers['Content-Disposition'] = f'attachment; filename="{safe_name}.docx"'
            return resp

    except Exception as e:
        return f'Export failed: {e}', 500

    return 'Unknown format', 400


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_remove(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


if __name__ == '__main__':
    print("\n" + "="*55)
    print("  SubtitleAI — starting…")
    deps = check_dependencies()
    print(f"  Whisper:            {'✓' if deps['whisper'] else '✗ (pip install openai-whisper)'}")
    print(f"  PyTorch:            {'✓' if deps['torch'] else '✗ (needed for Whisper)'}")
    print(f"  SpeechRecognition:  {'✓' if deps['speech_recognition'] else '✗ (pip install SpeechRecognition)'}")
    print(f"  pydub:              {'✓' if deps['pydub'] else '✗ (pip install pydub)'}")
    print(f"  ffmpeg:             {'✓' if deps['ffmpeg'] else '✗ (install from ffmpeg.org)'}")
    print("="*55 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5000)
