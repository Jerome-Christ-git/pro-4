"""
Transcriber — Multi-backend audio/video transcription (all free).

Priority order:
  1. OpenAI Whisper  — best quality, runs locally, needs: pip install openai-whisper + ffmpeg
  2. SpeechRecognition + Google free API  — lightweight, needs: pip install SpeechRecognition pydub + ffmpeg
  3. SpeechRecognition WAV-only  — no ffmpeg needed if file is already .wav

Install the one that works for you:
  pip install openai-whisper        (recommended)
  pip install SpeechRecognition pydub  (fallback)
"""
import os
import shutil
import subprocess
import tempfile
import traceback

_whisper_model = None


# ── Public API ───────────────────────────────────────────────────────────────

def transcribe_file(file_path: str, model_size: str = 'base') -> dict:
    """
    Transcribe an audio/video file. Tries multiple backends in order.
    Always returns a dict; raises RuntimeError with a user-friendly message on failure.
    """
    errors = []

    # ── Backend 1: Whisper ──────────────────────────────────────────────────
    try:
        result = _transcribe_whisper(file_path, model_size)
        print(f"[Transcriber] Used Whisper ({model_size})")
        return result
    except ImportError:
        errors.append("Whisper not installed (run: pip install openai-whisper)")
    except Exception as e:
        msg = str(e)
        if 'ffmpeg' in msg.lower() or 'ffprobe' in msg.lower():
            errors.append("ffmpeg not found — Whisper needs ffmpeg. Install from https://ffmpeg.org/download.html")
        else:
            errors.append(f"Whisper error: {msg}")
        print(f"[Transcriber] Whisper failed: {e}")

    # ── Backend 2: SpeechRecognition + pydub (Google free API) ─────────────
    try:
        result = _transcribe_sr_pydub(file_path)
        print("[Transcriber] Used SpeechRecognition + pydub")
        return result
    except ImportError as e:
        errors.append(f"SpeechRecognition/pydub not installed (run: pip install SpeechRecognition pydub) — {e}")
    except Exception as e:
        msg = str(e)
        if 'ffmpeg' in msg.lower():
            errors.append("ffmpeg not found — needed to convert audio formats. Install from https://ffmpeg.org/download.html")
        else:
            errors.append(f"SpeechRecognition error: {msg}")
        print(f"[Transcriber] SpeechRecognition failed: {e}")

    # ── Backend 3: SpeechRecognition WAV only (no ffmpeg) ──────────────────
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.wav':
        try:
            result = _transcribe_sr_wav(file_path)
            print("[Transcriber] Used SpeechRecognition WAV mode")
            return result
        except ImportError:
            errors.append("SpeechRecognition not installed (run: pip install SpeechRecognition)")
        except Exception as e:
            errors.append(f"WAV recognition error: {e}")

    # ── All backends failed ─────────────────────────────────────────────────
    error_list = '\n'.join(f"  • {e}" for e in errors)
    raise RuntimeError(
        f"Could not transcribe file. Tried all available backends:\n{error_list}\n\n"
        "QUICKEST FIX: Run these commands in your terminal:\n"
        "  pip install openai-whisper SpeechRecognition pydub\n"
        "  Then install ffmpeg: https://ffmpeg.org/download.html"
    )


def check_dependencies() -> dict:
    """Check which transcription backends are available."""
    status = {
        'whisper': False,
        'speech_recognition': False,
        'pydub': False,
        'ffmpeg': False,
        'torch': False,
    }

    try:
        import whisper
        status['whisper'] = True
    except ImportError:
        pass

    try:
        import speech_recognition
        status['speech_recognition'] = True
    except ImportError:
        pass

    try:
        import pydub
        status['pydub'] = True
    except ImportError:
        pass

    try:
        import torch
        status['torch'] = True
    except ImportError:
        pass

    # Check ffmpeg in PATH
    status['ffmpeg'] = shutil.which('ffmpeg') is not None

    return status


# ── Backend implementations ───────────────────────────────────────────────────

def _transcribe_whisper(file_path: str, model_size: str = 'base') -> dict:
    global _whisper_model
    import whisper  # noqa — raises ImportError if not installed

    if _whisper_model is None or getattr(_whisper_model, '_model_size', '') != model_size:
        print(f"[Transcriber] Loading Whisper model '{model_size}'…")
        _whisper_model = whisper.load_model(model_size)
        _whisper_model._model_size = model_size

    result = _whisper_model.transcribe(
        file_path,
        verbose=False,
        word_timestamps=False,
        condition_on_previous_text=True,
        fp16=False,  # Prevents crash on CPU-only systems
    )

    segments = [
        {
            'start': round(seg['start'], 2),
            'end':   round(seg['end'],   2),
            'text':  seg['text'].strip()
        }
        for seg in result.get('segments', [])
    ]

    return {
        'text':     result.get('text', '').strip(),
        'language': result.get('language', 'unknown'),
        'segments': segments,
        'backend':  'whisper',
    }


def _transcribe_sr_pydub(file_path: str) -> dict:
    """SpeechRecognition with pydub (handles all audio formats via ffmpeg)."""
    import speech_recognition as sr  # noqa
    from pydub import AudioSegment    # noqa

    ext = os.path.splitext(file_path)[1].lower().lstrip('.')
    fmt_map = {'mp3': 'mp3', 'mp4': 'mp4', 'm4a': 'mp4', 'ogg': 'ogg',
               'webm': 'webm', 'flac': 'flac', 'wav': 'wav', 'mpeg': 'mp3',
               'mpga': 'mp3', 'mkv': 'mkv', 'avi': 'avi', 'mov': 'mov'}
    audio_fmt = fmt_map.get(ext, ext)

    print(f"[Transcriber] Converting {ext} → WAV with pydub…")
    audio = AudioSegment.from_file(file_path, format=audio_fmt)

    # Chunk into 55-second pieces (Google free API limit is ~60s)
    chunk_ms    = 55_000
    chunks      = _chunk_audio(audio, chunk_ms)
    recognizer  = sr.Recognizer()
    full_text   = []
    segments    = []
    offset      = 0

    for i, chunk in enumerate(chunks):
        tmp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        try:
            chunk.export(tmp.name, format='wav')
            with sr.AudioFile(tmp.name) as source:
                audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data)
            full_text.append(text)
            start = offset / 1000.0
            end   = (offset + len(chunk)) / 1000.0
            segments.append({'start': round(start, 2), 'end': round(end, 2), 'text': text})
        except sr.UnknownValueError:
            pass  # Silence / unintelligible chunk
        except sr.RequestError as e:
            raise RuntimeError(f"Google Speech API error (check internet): {e}")
        finally:
            tmp.close()
            try:
                os.unlink(tmp.name)
            except Exception:
                pass
        offset += len(chunk)

    return {
        'text':     ' '.join(full_text),
        'language': 'auto',
        'segments': segments,
        'backend':  'speech_recognition',
    }


def _transcribe_sr_wav(file_path: str) -> dict:
    """SpeechRecognition direct WAV — no ffmpeg needed."""
    import speech_recognition as sr  # noqa

    recognizer = sr.Recognizer()
    with sr.AudioFile(file_path) as source:
        audio_data = recognizer.record(source)

    text = recognizer.recognize_google(audio_data)
    return {
        'text':     text,
        'language': 'auto',
        'segments': [{'start': 0.0, 'end': 0.0, 'text': text}],
        'backend':  'speech_recognition_wav',
    }


def _chunk_audio(audio, chunk_ms: int):
    """Split AudioSegment into chunks of chunk_ms milliseconds."""
    chunks = []
    start  = 0
    while start < len(audio):
        end = min(start + chunk_ms, len(audio))
        chunks.append(audio[start:end])
        start = end
    return chunks


def get_available_models():
    return [
        {'id': 'tiny',   'label': 'Tiny (39MB) — Fastest, lower accuracy'},
        {'id': 'base',   'label': 'Base (74MB) — Good balance ✓ Recommended'},
        {'id': 'small',  'label': 'Small (244MB) — Better accuracy, slower'},
        {'id': 'medium', 'label': 'Medium (769MB) — High accuracy'},
        {'id': 'large',  'label': 'Large (1.5GB) — Best accuracy, very slow'},
    ]
