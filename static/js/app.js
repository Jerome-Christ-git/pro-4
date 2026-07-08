/* ═══════════════════════════════════════════════════════════════
   SubtitleAI — Main Application Logic
   ═══════════════════════════════════════════════════════════════ */

'use strict';

// ── State ──────────────────────────────────────────────────────────────────
let recognition      = null;
let isRecording      = false;
let finalTranscript  = '';
let translatedLive   = '';
let timerInterval    = null;
let startTime        = null;
let translateTimeout = null;
let uploadSid        = null;
let uploadText       = '';
let segmentsShown    = true;
let depsInfo         = null;

// ── DOM shortcut ───────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);

// ── Tab Switching ──────────────────────────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    $(`tab-${btn.dataset.tab}`).classList.add('active');
  });
});

// ── Check browser + deps on load ───────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  applySubtitleStyles();
  checkDepsFromServer();

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    showBrowserWarning('Live recording requires Chrome or Edge browser. Firefox does not support the Web Speech API.');
    const btn = $('record-btn');
    if (btn) btn.disabled = true;
  }
});

async function checkDepsFromServer() {
  try {
    const resp = await fetch('/api/check-deps');
    const data = await resp.json();
    depsInfo = data;

    const banner = $('deps-banner');
    if (!banner) return;

    if (data.active_backend === 'none') {
      banner.innerHTML = `
        <div class="deps-warning">
          <i class="fa-solid fa-triangle-exclamation"></i>
          <strong>No transcription engine installed.</strong>
          Run in your terminal: <code>pip install openai-whisper SpeechRecognition pydub</code>
          and install <a href="https://ffmpeg.org/download.html" target="_blank">ffmpeg</a>.
          Then restart <code>python app.py</code>.
        </div>`;
      banner.style.display = 'block';
    } else if (data.active_backend === 'speech_recognition_wav') {
      banner.innerHTML = `
        <div class="deps-info">
          <i class="fa-solid fa-circle-info"></i>
          Active: Google Speech API (WAV files only).
          For MP3/MP4 support: install <a href="https://ffmpeg.org/download.html" target="_blank">ffmpeg</a>.
          For offline AI: <code>pip install openai-whisper</code>
        </div>`;
      banner.style.display = 'block';
    } else {
      banner.style.display = 'none';
    }
  } catch (e) {
    console.warn('Could not check deps:', e);
  }
}

// ── Live Recording ─────────────────────────────────────────────────────────

function toggleRecording() {
  if (isRecording) stopRecording();
  else startRecording();
}

function startRecording() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    showError('Live recording requires Chrome or Edge. Firefox does not support Web Speech API.');
    return;
  }

  // Show "requesting permission" state immediately
  $('record-label').textContent = 'Requesting mic…';
  $('record-btn').style.opacity = '0.7';

  recognition = new SpeechRecognition();
  recognition.continuous      = $('continuous-mode').checked;
  recognition.interimResults  = $('interim-mode').checked;
  recognition.maxAlternatives = 1;

  const lang = $('live-lang').value;
  if (lang) recognition.lang = lang;

  recognition.onstart = () => {
    isRecording = true;
    $('record-btn').style.opacity = '1';
    $('record-btn').classList.add('recording');
    $('record-icon').className = 'fa-solid fa-stop';
    $('record-label').textContent = 'Stop Recording';
    $('live-status').classList.remove('hidden');
    $('status-text').textContent = 'Listening…';
    $('placeholder').style.display = 'none';
    startTimer();
    applySubtitleStyles();
    showToast('Recording started — speak now', 'success');
  };

  recognition.onresult = event => {
    let interim = '';

    for (let i = event.resultIndex; i < event.results.length; i++) {
      const transcript = event.results[i][0].transcript;
      const confidence = event.results[i][0].confidence;

      if (event.results[i].isFinal) {
        finalTranscript += transcript + ' ';
        $('final-text').textContent = finalTranscript.trim();
        updateWordCount();

        if (confidence) {
          $('confidence').textContent = `${Math.round(confidence * 100)}% confident`;
        }

        const targetLang = $('live-translate').value;
        if (targetLang) scheduleLiveTranslation(finalTranscript.trim(), targetLang);
      } else {
        interim += transcript;
      }
    }

    $('interim-text').textContent = $('interim-mode').checked ? interim : '';

    // Auto-scroll to bottom
    const area = $('subtitle-area');
    area.scrollTop = area.scrollHeight;

    if (finalTranscript.trim()) {
      $('live-save-section').style.display = 'block';
    }
  };

  recognition.onerror = event => {
    console.error('SpeechRecognition error:', event.error, event.message);

    const errorMessages = {
      'not-allowed':        '🎤 Microphone access denied.\n\nTo fix:\n1. Click the 🔒 lock icon in your browser address bar\n2. Set Microphone → Allow\n3. Reload the page and try again',
      'permission-denied':  '🎤 Microphone permission denied. Click the lock icon in the address bar → Allow Microphone → reload.',
      'no-speech':          null,  // ignore silently
      'audio-capture':      '🎤 No microphone found. Please connect a microphone and try again.',
      'network':            '⚠️ Network error during speech recognition. Check your internet connection.',
      'service-not-allowed': '🎤 Speech service not allowed. Make sure you are using http://localhost:5000 (not a file:// URL).',
      'aborted':             null,  // ignore
    };

    const msg = errorMessages[event.error];
    if (msg === null) return;  // ignore these errors
    if (msg) {
      showError(msg);
    } else {
      showError(`Speech recognition error: ${event.error}`);
    }

    resetRecordingUI();
  };

  recognition.onend = () => {
    if (isRecording && $('continuous-mode').checked) {
      // Brief pause then restart to avoid listener accumulation
      setTimeout(() => {
        if (isRecording) {
          recognition = null;
          startRecording();
        }
      }, 300);
    } else {
      if (isRecording) {
        // Ended unexpectedly — show message
        $('status-text').textContent = 'Stopped (no speech detected — click Start to retry)';
      }
      resetRecordingUI();
    }
  };

  try {
    recognition.start();
  } catch (e) {
    showError('Could not start microphone: ' + e.message);
    resetRecordingUI();
  }
}

function stopRecording() {
  isRecording = false;
  if (recognition) {
    try { recognition.stop(); } catch(e) {}
    recognition = null;
  }
  resetRecordingUI();
  if (finalTranscript.trim()) {
    showToast('Recording stopped. Use the save buttons below.', 'info');
  }
}

function resetRecordingUI() {
  isRecording = false;
  $('record-btn').style.opacity = '1';
  $('record-btn').classList.remove('recording');
  $('record-icon').className = 'fa-solid fa-microphone';
  $('record-label').textContent = 'Start Recording';
  $('live-status').classList.add('hidden');
  $('interim-text').textContent = '';
  stopTimer();
}

function clearTranscript() {
  if (isRecording) stopRecording();
  finalTranscript = '';
  translatedLive  = '';
  $('final-text').textContent   = '';
  $('interim-text').textContent = '';
  $('placeholder').style.display = '';
  $('live-translation-box').classList.add('hidden');
  $('live-translated-text').textContent = '';
  $('live-save-section').style.display  = 'none';
  $('word-count').textContent  = '0';
  $('confidence').textContent  = '—';
  $('duration').textContent    = '00:00';
}

// ── Timer ──────────────────────────────────────────────────────────────────
function startTimer() {
  startTime = Date.now();
  timerInterval = setInterval(() => {
    const s = Math.floor((Date.now() - startTime) / 1000);
    $('duration').textContent =
      `${Math.floor(s/60).toString().padStart(2,'0')}:${(s%60).toString().padStart(2,'0')}`;
  }, 1000);
}

function stopTimer() {
  clearInterval(timerInterval);
  timerInterval = null;
}

function updateWordCount() {
  const words = finalTranscript.trim().split(/\s+/).filter(Boolean);
  $('word-count').textContent = words.length;
}

// ── Live Translation ───────────────────────────────────────────────────────
function scheduleLiveTranslation(text, target) {
  clearTimeout(translateTimeout);
  translateTimeout = setTimeout(() => doLiveTranslation(text, target), 1500);
}

async function doLiveTranslation(text, target) {
  try {
    const resp = await fetch('/api/translate', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ text, source: 'auto', target })
    });
    const data = await resp.json();
    if (data.translated) {
      translatedLive = data.translated;
      $('live-translation-box').classList.remove('hidden');
      const sel = $('live-translate');
      $('live-translation-lang').textContent =
        `Translation → ${sel.options[sel.selectedIndex].text}`;
      $('live-translated-text').textContent = data.translated;
    }
  } catch (e) {
    console.warn('Translation error:', e);
  }
}

// ── Subtitle Styling ───────────────────────────────────────────────────────
function applySubtitleStyles() {
  const size    = ($('font-size-slider')?.value  || 22) + 'px';
  const textCol = $('text-color')?.value  || '#ffffff';
  const bgCol   = hexToRgba($('bg-color')?.value || '#000000',
                             parseInt($('bg-opacity')?.value || 60) / 100);

  const finalEl   = $('final-text');
  const interimEl = $('interim-text');
  const area      = $('subtitle-area');

  if (finalEl)   finalEl.style.fontSize   = size;
  if (interimEl) interimEl.style.fontSize = size;
  if (area) {
    area.style.color      = textCol;
    area.style.background = bgCol;
  }
}

$('font-size-slider')?.addEventListener('input', e => {
  $('font-size-val').textContent = e.target.value + 'px';
  applySubtitleStyles();
});
$('bg-opacity')?.addEventListener('input', e => {
  $('opacity-val').textContent = e.target.value + '%';
  applySubtitleStyles();
});
$('text-color')?.addEventListener('input', applySubtitleStyles);
$('bg-color')?.addEventListener('input',  applySubtitleStyles);

function hexToRgba(hex, alpha) {
  const r = parseInt(hex.slice(1,3),16);
  const g = parseInt(hex.slice(3,5),16);
  const b = parseInt(hex.slice(5,7),16);
  return `rgba(${r},${g},${b},${alpha})`;
}

// ── Save Live & Export ─────────────────────────────────────────────────────
async function saveLiveAndExport(fmt) {
  if (!finalTranscript.trim()) {
    showToast('Nothing recorded yet!', 'error');
    return;
  }
  try {
    const title = $('session-title').value.trim()
      || `Live Session ${new Date().toLocaleTimeString()}`;
    const resp = await fetch('/api/save-live', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({
        text:              finalTranscript.trim(),
        translated_text:   translatedLive,
        detected_language: $('live-lang').value || 'auto',
        target_language:   $('live-translate').value || '',
        title
      })
    });
    const data = await resp.json();
    if (data.sid) {
      window.location.href = `/download/${data.sid}/${fmt}`;
    } else {
      showToast(data.error || 'Save failed', 'error');
    }
  } catch(e) {
    showToast('Save failed: ' + e.message, 'error');
  }
}

function copyToClipboard() {
  if (!finalTranscript.trim()) { showToast('Nothing to copy!', 'error'); return; }
  navigator.clipboard.writeText(finalTranscript.trim())
    .then(() => showToast('Copied!', 'success'))
    .catch(() => {
      // Fallback for older browsers
      const ta = document.createElement('textarea');
      ta.value = finalTranscript.trim();
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      ta.remove();
      showToast('Copied!', 'success');
    });
}

// ── File Upload & Transcription ────────────────────────────────────────────
const fileInput = $('file-input');
const dropZone  = $('drop-zone');

fileInput?.addEventListener('change', e => {
  if (e.target.files[0]) setUploadFile(e.target.files[0]);
});

dropZone?.addEventListener('dragover', e => {
  e.preventDefault();
  dropZone.classList.add('drag-over');
});
dropZone?.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
dropZone?.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (file) {
    // Manually assign files to the input
    const dt = new DataTransfer();
    dt.items.add(file);
    fileInput.files = dt.files;
    setUploadFile(file);
  }
});

function setUploadFile(file) {
  $('file-info').innerHTML =
    `<i class="fa-solid fa-check-circle"></i> <strong>${escapeHtml(file.name)}</strong> (${formatBytes(file.size)})`;
  $('file-info').classList.remove('hidden');
  $('upload-btn').disabled = false;
}

function formatBytes(b) {
  if (b < 1024)    return b + ' B';
  if (b < 1048576) return (b/1024).toFixed(1) + ' KB';
  return (b/1048576).toFixed(1) + ' MB';
}

async function startTranscription() {
  const file = fileInput?.files[0];
  if (!file) { showToast('Please select a file first', 'error'); return; }

  // Reset UI
  $('upload-btn').disabled = true;
  $('upload-progress').classList.remove('hidden');
  $('upload-save-section').classList.add('hidden');
  $('segments-panel').classList.add('hidden');
  $('upload-stats').style.display = 'none';
  $('upload-translation-box').classList.add('hidden');
  $('upload-output').innerHTML = `
    <div class="placeholder-msg">
      <i class="fa-solid fa-spinner fa-spin"></i>
      <p>Transcribing with AI…</p>
      <p class="hint">Large files may take a minute. Please wait.</p>
    </div>`;

  // Animate progress bar (indeterminate)
  const fill     = $('progress-fill');
  const statusEl = $('progress-status');
  let pct = 0;
  const progInterval = setInterval(() => {
    if (pct < 85) {
      pct += Math.random() * 3;
      fill.style.width = Math.min(pct, 85) + '%';
      if      (pct < 20) statusEl.textContent = 'Uploading…';
      else if (pct < 45) statusEl.textContent = 'Processing audio…';
      else if (pct < 70) statusEl.textContent = 'Running AI transcription…';
      else               statusEl.textContent = 'Finalizing…';
    }
  }, 400);

  const formData = new FormData();
  formData.append('file',        file);
  formData.append('model',       $('whisper-model').value);
  formData.append('target_lang', $('upload-translate').value);

  let data;
  try {
    const resp = await fetch('/api/transcribe-file', { method: 'POST', body: formData });

    clearInterval(progInterval);
    fill.style.width   = '100%';
    statusEl.textContent = 'Done!';

    // Always try to parse JSON
    let raw;
    try {
      raw = await resp.json();
    } catch (parseErr) {
      // Server returned non-JSON (HTML error page)
      throw new Error('Server returned an unexpected response. Check the terminal for errors.');
    }

    data = raw;
  } catch (networkErr) {
    clearInterval(progInterval);
    $('upload-output').innerHTML = `
      <div class="placeholder-msg">
        <i class="fa-solid fa-triangle-exclamation" style="color:var(--red)"></i>
        <p style="color:var(--red);font-weight:600">Connection Error</p>
        <p class="hint" style="color:var(--text-muted)">${escapeHtml(networkErr.message)}</p>
        <p class="hint" style="margin-top:.5rem">
          Check the terminal where <code>python app.py</code> is running for the full error.
        </p>
      </div>`;
    $('upload-progress').classList.add('hidden');
    $('upload-btn').disabled = false;
    return;
  }

  // ── Handle server error response ─────────────────────────────────────────
  if (data.error) {
    $('upload-output').innerHTML = `
      <div class="placeholder-msg error-msg">
        <i class="fa-solid fa-triangle-exclamation" style="color:var(--red)"></i>
        <p style="color:var(--red);font-weight:600">Transcription Failed</p>
        <pre class="error-pre">${escapeHtml(data.error)}</pre>
        ${data.error.includes('pip install') || data.error.includes('ffmpeg') ? `
        <div class="install-guide">
          <p><strong>Quick fix — run these in your terminal:</strong></p>
          <code>pip install openai-whisper SpeechRecognition pydub</code><br/>
          <p style="margin-top:.4rem">For ffmpeg (needed for MP3/MP4):</p>
          <code>winget install ffmpeg</code>
          <span style="color:var(--text-muted)"> (Windows)</span><br/>
          <code>brew install ffmpeg</code>
          <span style="color:var(--text-muted)"> (Mac)</span><br/>
          <code>sudo apt install ffmpeg</code>
          <span style="color:var(--text-muted)"> (Linux)</span>
        </div>` : ''}
      </div>`;
    setTimeout(() => {
      $('upload-progress').classList.add('hidden');
      fill.style.width = '0%';
    }, 800);
    $('upload-btn').disabled = false;
    return;
  }

  // ── Success ───────────────────────────────────────────────────────────────
  uploadSid  = data.sid;
  uploadText = data.text;

  // Show backend badge
  const backendLabel = {
    whisper:               '🤖 Whisper AI',
    speech_recognition:    '🌐 Google Speech API',
    speech_recognition_wav:'🌐 Google Speech API',
  }[data.backend] || '✓ Transcribed';

  $('upload-output').innerHTML =
    `<div class="backend-badge">${backendLabel}</div>` +
    `<div class="final-text">${escapeHtml(data.text)}</div>`;

  // Translation
  if (data.translated_text) {
    $('upload-translation-box').classList.remove('hidden');
    const sel = $('upload-translate');
    $('upload-translation-lang').textContent =
      `Translation → ${sel.options[sel.selectedIndex].text}`;
    $('upload-translated-text').textContent = data.translated_text;
  }

  // Segments timeline
  if (data.segments?.length > 0) {
    $('segments-panel').classList.remove('hidden');
    $('segments-list').innerHTML = data.segments.map(seg => `
      <div class="segment-item">
        <span class="seg-time">${formatSRT(seg.start)} → ${formatSRT(seg.end)}</span>
        <span class="seg-text">${escapeHtml(seg.text)}</span>
      </div>`).join('');
  }

  // Stats
  $('upload-stats').style.display = 'flex';
  $('upload-words').textContent = data.text.split(/\s+/).filter(Boolean).length;
  $('upload-lang').textContent  = (data.detected_language || 'auto').toUpperCase();
  $('upload-segs').textContent  = (data.segments || []).length;

  $('upload-save-section').classList.remove('hidden');
  showToast('Transcription complete!', 'success');

  setTimeout(() => {
    $('upload-progress').classList.add('hidden');
    fill.style.width = '0%';
  }, 1200);
  $('upload-btn').disabled = false;
}

function downloadUpload(fmt) {
  if (!uploadSid) { showToast('No transcription to download', 'error'); return; }
  window.location.href = `/download/${uploadSid}/${fmt}`;
}

function copyUploadText() {
  if (!uploadText) { showToast('Nothing to copy!', 'error'); return; }
  navigator.clipboard.writeText(uploadText)
    .then(() => showToast('Copied!', 'success'))
    .catch(() => showToast('Copy failed', 'error'));
}

function clearUploadResult() {
  uploadSid  = null;
  uploadText = '';
  $('upload-output').innerHTML = `
    <div class="placeholder-msg" id="upload-placeholder">
      <i class="fa-solid fa-file-audio"></i>
      <p>Upload an audio or video file to transcribe</p>
      <p class="hint">Language is detected automatically by AI</p>
    </div>`;
  $('upload-translation-box').classList.add('hidden');
  $('segments-panel').classList.add('hidden');
  $('upload-save-section').classList.add('hidden');
  $('upload-stats').style.display = 'none';
  $('file-info').classList.add('hidden');
  $('upload-btn').disabled = true;
  if (fileInput) fileInput.value = '';
}

function toggleSegments() {
  segmentsShown = !segmentsShown;
  $('segments-list').style.display = segmentsShown ? 'block' : 'none';
}

// ── Helpers ────────────────────────────────────────────────────────────────
function formatSRT(sec) {
  if (!sec && sec !== 0) return '00:00';
  const m = Math.floor(sec/60).toString().padStart(2,'0');
  const s = Math.floor(sec%60).toString().padStart(2,'0');
  return `${m}:${s}`;
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#039;').replace(/\n/g,'<br>');
}

function showToast(msg, type = 'info') {
  const t = $('toast');
  if (!t) return;
  t.textContent = msg;
  t.className = `toast ${type}`;
  clearTimeout(t._timeout);
  t._timeout = setTimeout(() => t.classList.add('hidden'), 4500);
}

function showError(msg) {
  // Show error in a modal-style overlay
  const existing = $('error-overlay');
  if (existing) existing.remove();

  const overlay = document.createElement('div');
  overlay.id = 'error-overlay';
  overlay.className = 'error-overlay';
  overlay.innerHTML = `
    <div class="error-dialog glass-card">
      <div class="error-dialog-header">
        <i class="fa-solid fa-triangle-exclamation" style="color:var(--red)"></i>
        <span>Error</span>
        <button onclick="document.getElementById('error-overlay').remove()" class="clear-btn">
          <i class="fa-solid fa-xmark"></i>
        </button>
      </div>
      <div class="error-dialog-body">
        <pre class="error-pre">${escapeHtml(msg)}</pre>
      </div>
    </div>`;
  document.body.appendChild(overlay);

  // Auto-dismiss after 15s
  setTimeout(() => overlay.remove(), 15000);
}

function showBrowserWarning(msg) {
  const banner = $('browser-warning');
  if (banner) {
    banner.textContent = msg;
    banner.style.display = 'block';
  }
}

// ── Keyboard Shortcuts ─────────────────────────────────────────────────────
document.addEventListener('keydown', e => {
  if (e.ctrlKey && e.code === 'Space') {
    e.preventDefault();
    const liveTabActive = document.querySelector('.tab-btn[data-tab="live"]')?.classList.contains('active');
    if (liveTabActive) toggleRecording();
  }
});
