"""
Translator — uses MyMemory free REST API (no API key required).
Free tier: ~5,000 words/day per IP.
Supports 50+ language pairs.
"""
import urllib.request
import urllib.parse
import json


LANGUAGES = {
    'auto':  'Auto Detect',
    'en':    'English',
    'hi':    'Hindi',
    'ta':    'Tamil',
    'te':    'Telugu',
    'ml':    'Malayalam',
    'kn':    'Kannada',
    'mr':    'Marathi',
    'bn':    'Bengali',
    'gu':    'Gujarati',
    'pa':    'Punjabi',
    'ur':    'Urdu',
    'zh-CN': 'Chinese (Simplified)',
    'zh-TW': 'Chinese (Traditional)',
    'ja':    'Japanese',
    'ko':    'Korean',
    'ar':    'Arabic',
    'fr':    'French',
    'de':    'German',
    'es':    'Spanish',
    'it':    'Italian',
    'pt':    'Portuguese',
    'ru':    'Russian',
    'nl':    'Dutch',
    'pl':    'Polish',
    'tr':    'Turkish',
    'sv':    'Swedish',
    'da':    'Danish',
    'fi':    'Finnish',
    'no':    'Norwegian',
    'cs':    'Czech',
    'ro':    'Romanian',
    'hu':    'Hungarian',
    'el':    'Greek',
    'he':    'Hebrew',
    'id':    'Indonesian',
    'ms':    'Malay',
    'th':    'Thai',
    'vi':    'Vietnamese',
    'uk':    'Ukrainian',
    'fa':    'Persian (Farsi)',
    'sw':    'Swahili',
    'af':    'Afrikaans',
}


def translate_text(text: str, source: str = 'auto', target: str = 'en') -> str:
    """Translate text using MyMemory free API."""
    if not text.strip():
        return text

    # MyMemory language pair format
    src = 'autodetect' if source in ('auto', 'unknown', '') else source
    langpair = f'{src}|{target}'

    # Split long texts into chunks (MyMemory has ~500 char limit per request)
    chunks = _split_text(text, max_len=450)
    translated_chunks = []

    for chunk in chunks:
        if not chunk.strip():
            translated_chunks.append(chunk)
            continue
        translated_chunks.append(_call_mymemory(chunk, langpair))

    return ' '.join(translated_chunks)


def _call_mymemory(text: str, langpair: str) -> str:
    params = urllib.parse.urlencode({'q': text, 'langpair': langpair})
    url = f'https://api.mymemory.translated.net/get?{params}'

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'SubtitleAssistant/1.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        translated = data.get('responseData', {}).get('translatedText', '')
        if not translated or 'MYMEMORY WARNING' in translated:
            return text  # Fallback to original
        return translated
    except Exception:
        return text  # Fallback silently


def detect_language_code(text: str) -> str:
    """Best-effort language detection via MyMemory (detects via translation)."""
    try:
        params = urllib.parse.urlencode({'q': text[:200], 'langpair': 'autodetect|en'})
        url = f'https://api.mymemory.translated.net/get?{params}'
        req = urllib.request.Request(url, headers={'User-Agent': 'SubtitleAssistant/1.0'})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        detected = data.get('responseData', {}).get('detectedLanguage', '')
        return detected.lower() if detected else 'unknown'
    except Exception:
        return 'unknown'


def _split_text(text: str, max_len: int = 450) -> list:
    """Split text into sentence-aware chunks that stay under max_len."""
    if len(text) <= max_len:
        return [text]

    # Try splitting by sentence boundaries first
    sentences = text.replace('\n', ' ').split('. ')
    chunks = []
    current = ''

    for sentence in sentences:
        part = sentence + '. '
        if len(current) + len(part) > max_len:
            if current:
                chunks.append(current.strip())
            # If a single sentence is still too long, split by words
            if len(part) > max_len:
                words = part.split()
                current = ''
                for word in words:
                    if len(current) + len(word) + 1 > max_len:
                        if current:
                            chunks.append(current.strip())
                        current = word + ' '
                    else:
                        current += word + ' '
            else:
                current = part
        else:
            current += part

    if current.strip():
        chunks.append(current.strip())

    return chunks if chunks else [text]
