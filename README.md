# Android Media Backup

Applicazione Python per backup incrementali di foto e video da dispositivi Android tramite ADB.

## Caratteristiche

- **Backup incrementale**: Scarica solo i file nuovi o modificati (comportamento simile a rsync)
- **Doppia interfaccia**: CLI interattiva e GUI con PyQt6
- **Ripresa automatica**: Se il backup viene interrotto, riprende da dove era rimasto
- **Scansione automatica**: Rileva automaticamente le cartelle con media sul dispositivo
- **Progress bar**: Visualizza lo stato di avanzamento in tempo reale

## Requisiti

- Python 3.10+
- ADB (Android Debug Bridge) installato e nel PATH
- Dispositivo Android con debug USB attivo

## Installazione

```bash
# Clona il repository
git clone <repo-url>
cd androidMediaBackup

# Crea virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Installa dipendenze
pip install -r requirements.txt
```

## Utilizzo

### GUI

```bash
python main_gui.py
```

### CLI

```bash
# Modalita interattiva
python main_cli.py

# Specifica destinazione
python main_cli.py -d ~/backup

# Backup solo di cartelle specifiche
python main_cli.py -d ~/backup -f DCIM Pictures
```

## Struttura Progetto

```
androidMediaBackup/
├── main_cli.py          # Entry point CLI
├── main_gui.py          # Entry point GUI
├── core/                # Logica core condivisa
│   ├── adb.py           # Wrapper ADB
│   ├── scanner.py       # Scansione media
│   ├── backup.py        # Gestione backup
│   └── manifest.py      # Tracking file sincronizzati
├── cli/                 # Interfaccia CLI
│   └── app.py
└── gui/                 # Interfaccia GUI
    └── app.py
```

## Come Funziona

1. L'app si connette al dispositivo tramite ADB
2. Scansiona le cartelle media comuni (DCIM, Pictures, Movies, ecc.)
3. Mostra le cartelle trovate con statistiche (numero file, dimensione)
4. L'utente seleziona quali cartelle sincronizzare
5. L'app confronta i file con il manifest locale per determinare cosa scaricare
6. Scarica solo i file nuovi/modificati
7. Aggiorna il manifest per le sessioni successive

## Manifest

Il file `.backup_manifest.json` nella cartella di destinazione tiene traccia dei file sincronizzati.
Questo permette di:
- Riprendere backup interrotti
- Evitare di riscaricare file gia presenti
- Rilevare file modificati sul dispositivo

## Licenza

MIT
