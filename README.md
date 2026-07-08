# 🎙 AI-Powered Real-Time Speech-to-Text Subtitle Assistant

A fully **free, local** web app that converts live speech and uploaded audio/video
files into synchronized subtitles using browser Web Speech API and OpenAI Whisper.

---

## ✨ Features

| Feature | Details |
|---|---|
| 🎤 Live transcription | Real-time subtitles via browser Web Speech API |
| 📁 File upload | MP3, MP4, WAV, M4A, OGG, WebM, FLAC, MKV, AVI, MOV |
| 🤖 Whisper AI | Open-source, runs 100% locally — no API key needed |
| 🌐 Auto language detect | Whisper detects language automatically from audio |
| 🔤 30+ live languages | Chrome/Edge Web Speech API language selector |
| 🌍 Translation | Free MyMemory API — 40+ languages |
| 📄 TXT export | Plain text with metadata |
| 📕 PDF export | Styled PDF with reportlab |
| 🎬 SRT export | Subtitle file with timestamps for video editors |
| 📝 DOCX export | Microsoft Word document |
| 📚 Session history | Browse and re-download past transcriptions |
| 🎨 Customizable UI | Font size, text color, background, opacity |
| ⌨️ Keyboard shortcut | Ctrl+Space to toggle recording |

---

## 🚀 Quick Start (VS Code / Terminal)

### Step 1 — Install Python dependencies

```bash
pip install -r requirements.txt
```

> **Note:** The first run will download the Whisper model (~74MB for `base`).
> This only happens once; it's cached for future runs.

### Step 2 — Copy the environment file

```bash
cp .env.example .env
```

Edit `.env` and change `SECRET_KEY` to any random string.

### Step 3 — Run the app

```bash
python app.py
```

### Step 4 — Open in browser

```
http://localhost:5000
```

---

## 🖥 System Requirements

| Item | Minimum |
|---|---|
| Python | 3.8 or higher |
| RAM | 2 GB (4 GB recommended for `small` model) |
| Disk | ~200 MB (for `base` Whisper model) |
| Browser | Chrome or Edge (for live recording) |
| Internet | Only needed for translation; Whisper works offline |

---

## 🤖 Whisper Model Sizes

| Model | Size | Speed | Accuracy |
|---|---|---|---|
| tiny | 39 MB | ⚡ Fastest | Basic |
| **base** | 74 MB | ✅ Fast | Good — **recommended** |
| small | 244 MB | Medium | Better |
| medium | 769 MB | Slow | High |
| large | 1.5 GB | Very slow | Best |

---

## 📂 Project Structure

```
subtitle_assistant/
├── app.py                    # Flask server & routes
├── requirements.txt
├── .env.example
├── utils/
│   ├── transcriber.py        # Whisper AI transcription
│   ├── translator.py         # MyMemory free translation API
│   └── exporter.py           # TXT / PDF / SRT / DOCX export
├── templates/
│   ├── index.html            # Main UI (live + upload tabs)
│   ├── history.html          # Session history
│   └── session.html          # Individual session view
├── static/
│   ├── css/style.css         # Dark futuristic UI
│   └── js/app.js             # Speech recognition & upload logic
├── uploads/                  # Temp upload folder (auto-created)
└── transcriptions/           # Saved sessions as JSON (auto-created)
```

---

## 🌐 Browser Support

| Browser | Live Recording | File Upload |
|---|---|---|
| Google Chrome | ✅ Full support | ✅ |
| Microsoft Edge | ✅ Full support | ✅ |
| Firefox | ❌ No Web Speech API | ✅ |
| Safari | ⚠️ Partial | ✅ |

> **Recommendation:** Use Chrome or Edge for the best experience.

---

## 🔒 Privacy

- All transcription happens **locally on your machine** (Whisper).
- Live recording uses the **browser's built-in speech API** — Google's servers process it.
- Translation uses the **MyMemory free API** (text is sent to their servers).
- No account required, no data stored in the cloud.

---

## 📋 Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl + Space` | Toggle live recording |

---

## 🛠 Troubleshooting

### "No module named whisper"
```bash
pip install openai-whisper
```

### "No module named reportlab" (PDF export fails)
```bash
pip install reportlab
```

### "No module named docx" (DOCX export fails)
```bash
pip install python-docx
```

### Microphone not working
- Make sure you're using Chrome or Edge
- Click the lock icon in the address bar → allow Microphone
- Reload the page

### Whisper taking too long
- Switch to the `tiny` model in the Settings panel
- For large files, `base` is the best balance of speed and accuracy

---

## 📜 License

Free to use, modify, and distribute. No attribution required.
