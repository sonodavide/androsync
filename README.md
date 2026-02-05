# AndroSync

> 🤖 **DISCLAIMER**: This entire application was vibe-coded by Claude 4.5 Sonnet/Opus (Anthropic).

**AndroSync** is a powerful, incremental backup tool for Android devices that supports multiple file categories including media, documents, APKs, and more. Built with Python and PyQt6, it provides both CLI and GUI interfaces for seamless device backup workflows.

## ✨ Features

- 📱 **Multi-Category Support**: Backup Media (photos/videos), Documents (PDF, Office files), APKs, or any other files
- 🎯 **Smart Category Selection**: Choose exactly what to backup with an intuitive category picker
- 💾 **Multi-Storage Detection**: Automatically detects internal storage, SD cards, and other mounted volumes
- ⚡ **Incremental Sync**: Only transfers new or modified files (rsync-style)
- 🖥️ **Dual Interface**: Modern PyQt6 GUI or powerful CLI for automation
- 📊 **Detailed Statistics**: Real-time breakdown by file type (photos, videos, PDFs, etc.)
- 📝 **Progress Tracking**: Visual progress bars and detailed logging

## 🎯 Use Cases

- Backup all your photos and videos before a factory reset
- Extract APK files from your device for archival
- Sync documents and work files to your computer
- Create automated backup scripts via CLI
- Backup everything except system files ("Other" category)

## 📋 Requirements

- Python 3.10+
- Android Debug Bridge (ADB) installed and in PATH
- Android device with USB debugging enabled
- Linux, macOS, or Windows

## 🚀 Installation

```bash
# Clone the repository
git clone https://github.com/sonodavide/androsync.git
cd androsync

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## 💻 Usage

### GUI Mode (Recommended)

```bash
python main_gui.py
```

1. Connect your Android device via USB
2. Enable USB debugging in Developer Options
3. Click **"Seleziona Storage"** to choose which storage to scan
4. Click **"Seleziona Categorie"** to pick file types (Media, Documents, APK, Other)
5. Click **"Avvia Scansione"** to scan your device
6. Select folders to backup from the tree view
7. Choose destination folder and click **"Avvia Backup"**

### CLI Mode

```bash
python main_cli.py
```

Follow the interactive prompts to:
- Detect connected device
- Scan for files
- Select folders to backup
- Choose destination path
- Monitor backup progress

## 📂 File Categories

| Category | File Types |
|----------|------------|
| **Media** | Images (JPG, PNG, HEIC, RAW, etc.), Videos (MP4, MKV, AVI, MOV, etc.) |
| **Documents** | PDF, Office files (Word, Excel, PowerPoint), Text files, Data files (JSON, XML, CSV) |
| **APK** | Android application packages (.apk, .xapk, .apkm) |
| **Other** | Everything else not in the above categories |




