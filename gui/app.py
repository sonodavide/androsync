"""
GUI Application Module
PySide6-based graphical interface for Android Media Backup.
"""

import os
import sys
from typing import Optional

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTreeWidget, QTreeWidgetItem, QProgressBar,
    QTextEdit, QFileDialog, QMessageBox, QFrame, QSplitter, QHeaderView,
    QCheckBox, QDialog
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

from core.adb import check_adb_available, get_connected_devices, ADBError
from core.scanner import scan_media_folders, ScanResult, get_storage_roots
from core.categories import FILE_CATEGORIES
from core.models import MediaFolder
from core.utils import format_size
from core.backup import BackupProgress, BackupStatus

from .workers import ScanWorker, BackupWorker, AnalyzeWorker
from .dialogs import StorageSelectionDialog, CategorySelectionDialog
from .widgets import NumericTreeWidgetItem
from .styles import get_stylesheet


class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        self.scan_result: Optional[ScanResult] = None
        self.destination: Optional[str] = None
        self.backup_worker: Optional[BackupWorker] = None
        self.is_scanning = False
        self.scan_animation_timer: Optional[QTimer] = None
        self.scan_animation_dots = 0
        self.available_storage: dict[str, str] = {}  # path -> name
        self.selected_storage: dict[str, str] = {}   # path -> name
        self.selected_categories: list[str] = ['media']
        
        self.log_file = None # Initialize log file handle
        self.setup_logging() # Call setup_logging
        
        self.init_ui()
        self.check_device()
    
    def setup_logging(self):
        """Setup logging to file."""
        import datetime
        
        # Create logs directory
        log_dir = os.path.join(os.getcwd(), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        # Create log file with timestamp
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"gui_{timestamp}.log"
        log_path = os.path.join(log_dir, filename)
        
        try:
            self.log_file = open(log_path, 'a', encoding='utf-8')
            # Write header
            self.log_file.write(f"=== Android Media Backup GUI Log Started: {timestamp} ===\n")
            self.log_file.flush()
        except OSError as e:
            print(f"Failed to create log file: {e}")
            self.log_file = None # Ensure it's None if creation failed

    def init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle("Android Media Backup")
        self.setMinimumSize(800, 600)
        
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Header
        header = self.create_header()
        layout.addWidget(header)
        
        # Selection panel (Storage + Categories)
        selection_panel = self.create_selection_panel()
        layout.addWidget(selection_panel)
        
        # Splitter for main content
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Folder tree
        tree_container = self.create_folder_tree()
        splitter.addWidget(tree_container)
        
        # Statistics panel
        stats_panel = self.create_stats_panel()
        splitter.addWidget(stats_panel)
        
        # Log area
        log_container = self.create_log_area()
        splitter.addWidget(log_container)
        
        splitter.setSizes([400, 50, 200])
        layout.addWidget(splitter)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p% - %v/%m file")
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)
        
        # Bottom controls
        controls = self.create_controls()
        layout.addWidget(controls)
        
        # Apply dark theme
        self.apply_style()
    
    def create_header(self) -> QWidget:
        """Create header with device info."""
        frame = QFrame()
        frame.setObjectName("header")
        layout = QHBoxLayout(frame)
        
        # Title
        title = QLabel("Android Backup")
        title.setFont(QFont("", 16, QFont.Weight.Bold))
        layout.addWidget(title)
        
        layout.addStretch()
        
        # Device status
        self.device_label = QLabel("Ricerca dispositivo...")
        self.device_label.setFont(QFont("", 11))
        layout.addWidget(self.device_label)
        
        # Refresh button
        refresh_btn = QPushButton("Aggiorna")
        refresh_btn.clicked.connect(self.check_device)
        layout.addWidget(refresh_btn)
        
        return frame
    
    def create_selection_panel(self) -> QWidget:
        """Create selection panel for storage and categories."""
        frame = QFrame()
        frame.setObjectName("selection_panel")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        
        # Storage Selection
        storage_layout = QVBoxLayout()
        self.storage_btn = QPushButton("Seleziona Storage")
        self.storage_btn.clicked.connect(self.open_storage_dialog)
        self.storage_btn.setEnabled(False)
        storage_layout.addWidget(self.storage_btn)
        
        self.storage_label = QLabel("Nessuno")
        self.storage_label.setFont(QFont("", 10))
        self.storage_label.setStyleSheet("color: #888;")
        storage_layout.addWidget(self.storage_label)
        layout.addLayout(storage_layout)
        
        layout.addSpacing(20)
        
        # Category Selection
        cat_layout = QVBoxLayout()
        self.category_btn = QPushButton("Seleziona Categorie")
        self.category_btn.clicked.connect(self.open_category_dialog)
        cat_layout.addWidget(self.category_btn)
        
        self.category_label = QLabel("Media")
        self.category_label.setFont(QFont("", 10))
        self.category_label.setStyleSheet("color: #888;")
        cat_layout.addWidget(self.category_label)
        layout.addLayout(cat_layout)
        
        layout.addStretch()
        
        # Scan button
        self.scan_btn = QPushButton("Avvia Scansione")
        self.scan_btn.setMinimumHeight(40)
        self.scan_btn.clicked.connect(self.scan_device)
        self.scan_btn.setEnabled(False)
        layout.addWidget(self.scan_btn)
        
        return frame
    
    def open_category_dialog(self):
        """Open dialog to select categories."""
        dialog = CategorySelectionDialog(self, self.selected_categories)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.selected_categories = dialog.get_selected_categories()
            self.update_category_label()
    
    def update_category_label(self):
        """Update label with selected categories."""
        if not self.selected_categories:
            self.category_label.setText("Nessuna")
            return
            
        names = [FILE_CATEGORIES[cat]['name'] for cat in self.selected_categories]
        text = ", ".join(names)
        # Truncate if too long
        if len(text) > 30:
            text = text[:27] + "..."
        self.category_label.setText(text)
    
    def open_storage_dialog(self):
        """Open dialog to select storage."""
        if not self.available_storage:
            QMessageBox.warning(self, "Errore", "Nessuno storage disponibile")
            return
        
        dialog = StorageSelectionDialog(self.available_storage, self)
        
        # Pre-select previously selected items
        if self.selected_storage:
            for i in range(dialog.list_widget.count()):
                item = dialog.list_widget.item(i)
                path = item.data(Qt.ItemDataRole.UserRole)
                if path in self.selected_storage:
                    item.setCheckState(Qt.CheckState.Checked)
                else:
                    item.setCheckState(Qt.CheckState.Unchecked)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.selected_storage = dialog.get_selected_storage()
            self.update_storage_label()
            self.scan_btn.setEnabled(len(self.selected_storage) > 0)
    
    def update_storage_label(self):
        """Update the storage label with selected storage names."""
        if self.selected_storage:
            names = list(self.selected_storage.values())
            self.storage_label.setText(", ".join(names))
        else:
            self.storage_label.setText("Nessuno storage selezionato")
    
    def create_folder_tree(self) -> QWidget:
        """Create folder selection tree."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Header with label and select all checkbox
        header_layout = QHBoxLayout()
        
        label = QLabel("Cartelle Media")
        label.setFont(QFont("", 12, QFont.Weight.Bold))
        header_layout.addWidget(label)
        
        header_layout.addStretch()
        
        # Select all checkbox
        self.select_all_checkbox = QCheckBox("Seleziona tutto")
        self.select_all_checkbox.setChecked(True)
        self.select_all_checkbox.stateChanged.connect(self.on_select_all_changed)
        self.select_all_checkbox.setEnabled(False)
        header_layout.addWidget(self.select_all_checkbox)
        
        layout.addLayout(header_layout)
        
        # Tree widget
        self.folder_tree = QTreeWidget()
        self.folder_tree.setHeaderLabels(["Cartella", "Storage", "File", "Dimensione"])
        self.folder_tree.setRootIsDecorated(False)
        self.folder_tree.setAlternatingRowColors(False)
        self.folder_tree.itemChanged.connect(self.on_item_changed)
        self.folder_tree.setSortingEnabled(True)
        self.folder_tree.sortByColumn(4, Qt.SortOrder.DescendingOrder)  # Sort by total by default
        
        header = self.folder_tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSortIndicatorShown(True)
        header.setSectionsClickable(True)
        
        layout.addWidget(self.folder_tree)
        
        # Summary label
        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("color: #888; margin-top: 5px;")
        layout.addWidget(self.summary_label)
        
        return container
    
    def create_stats_panel(self) -> QWidget:
        """Create statistics panel for file type breakdown."""
        frame = QFrame()
        frame.setObjectName("stats_panel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 5, 10, 5)
        
        # Title
        title = QLabel("Statistiche")
        title.setFont(QFont("", 10, QFont.Weight.Bold))
        layout.addWidget(title)
        
        # Stats label (will be populated after scan)
        self.stats_label = QLabel("Nessuna scansione effettuata")
        self.stats_label.setFont(QFont("", 10))
        self.stats_label.setWordWrap(True)
        layout.addWidget(self.stats_label)
        
        return frame
    
    def update_stats_display(self, result):
        """Update statistics display based on scan result and selected categories."""
        if not result or not result.file_stats:
            self.stats_label.setText("Nessun file trovato")
            return
        
        # Map categories to relevant subcategories
        category_subcats = {
            'media': ['Foto', 'Video'],
            'documents': ['PDF', 'Word', 'Excel', 'PowerPoint', 'Testo', 'Dati'],
            'apk': ['APK'],
            'other': ['Altro']
        }
        
        # Collect relevant stats based on selected categories
        stats_parts = []
        for category in self.selected_categories:
            subcats = category_subcats.get(category, [])
            for subcat in subcats:
                if subcat in result.file_stats:
                    count = result.file_stats[subcat]
                    # Add emoji for visual appeal
                    emoji = {
                        'Foto': '📷',
                        'Video': '🎥',
                        'PDF': '📄',
                        'Word': '📝',
                        'Excel': '📊',
                        'PowerPoint': '📽️',
                        'Testo': '📃',
                        'APK': '📦',
                        'Dati': '💾',
                        'Altro': '📁'
                    }.get(subcat, '📄')
                    stats_parts.append(f"{emoji} {subcat}: {count:,}")
        
        if stats_parts:
            self.stats_label.setText("  |  ".join(stats_parts))
        else:
            self.stats_label.setText("Nessun file nelle categorie selezionate")
    
    def create_log_area(self) -> QWidget:
        """Create log text area."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        
        label = QLabel("Log")
        label.setFont(QFont("", 12, QFont.Weight.Bold))
        layout.addWidget(label)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Monospace", 10))
        layout.addWidget(self.log_text)
        
        return container
    
    def create_controls(self) -> QWidget:
        """Create bottom control buttons."""
        frame = QFrame()
        layout = QHBoxLayout(frame)
        
        # Destination button
        self.dest_btn = QPushButton("Seleziona Destinazione")
        self.dest_btn.clicked.connect(self.select_destination)
        layout.addWidget(self.dest_btn)
        
        # Destination label
        self.dest_label = QLabel("Nessuna destinazione selezionata")
        self.dest_label.setStyleSheet("color: #888;")
        layout.addWidget(self.dest_label)
        
        layout.addStretch()
        
        # Backup button
        self.backup_btn = QPushButton("Avvia Backup")
        self.backup_btn.clicked.connect(self.start_backup)
        self.backup_btn.setEnabled(False)
        self.backup_btn.setStyleSheet("background-color: #2196F3; font-weight: bold;")
        layout.addWidget(self.backup_btn)
        
        # Cancel button
        self.cancel_btn = QPushButton("Annulla")
        self.cancel_btn.clicked.connect(self.cancel_backup)
        self.cancel_btn.hide()
        layout.addWidget(self.cancel_btn)
        
        return frame
    
    def apply_style(self):
        """Apply application stylesheet."""
        self.setStyleSheet(get_stylesheet())
    
    def log(self, message: str):
        """Add message to log."""
        self.log_text.append(message)
        # Auto scroll to bottom
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        
        # Write to log file
        if self.log_file:
            try:
                self.log_file.write(message + '\n')
                self.log_file.flush()
            except OSError:
                pass
    
    def check_device(self):
        """Check for connected Android device and detect available storage."""
        self.device_label.setText("Ricerca dispositivo...")
        self.folder_tree.clear()
        self.summary_label.setText("")
        self.select_all_checkbox.setEnabled(False)
        self.scan_btn.setEnabled(False)
        self.storage_btn.setEnabled(False)
        self.available_storage = {}
        self.selected_storage = {}
        self.storage_label.setText("Nessuno storage selezionato")
        
        # Check ADB
        if not check_adb_available():
            self.device_label.setText("[ERRORE] ADB non trovato")
            self.log("ERRORE: ADB non disponibile. Installa Android SDK Platform Tools.")
            return
        
        # Check device
        try:
            devices = get_connected_devices()
            authorized = [d for d in devices if d.status == "device"]
            
            if len(authorized) == 0:
                self.device_label.setText("[ERRORE] Nessun dispositivo")
                self.log("ERRORE: Nessun dispositivo Android connesso.")
                self.log("   - Assicurati che il dispositivo sia collegato via USB")
                self.log("   - Attiva il debug USB nelle impostazioni sviluppatore")
                self.log("   - Autorizza il computer sul dispositivo")
                return
            
            if len(authorized) > 1:
                self.device_label.setText("[ATTENZIONE] Piu dispositivi connessi")
                self.log("ATTENZIONE: Collegare un solo dispositivo alla volta.")
                return
            
            device = authorized[0]
            self.device_label.setText(f"[OK] {device.model}")
            self.log(f"[OK] Dispositivo connesso: {device.model} ({device.serial})")
            
            # Detect available storage
            self.log("Rilevamento storage disponibili...")
            self.available_storage = get_storage_roots()
            
            if self.available_storage:
                storage_list = ", ".join(self.available_storage.values())
                self.log(f"[OK] Storage trovati: {storage_list}")
                self.storage_btn.setEnabled(True)
                self.log("Clicca 'Seleziona Storage' per scegliere cosa scansionare")
            else:
                self.log("ERRORE: Nessuno storage rilevato sul dispositivo")
            
        except ADBError as e:
            self.device_label.setText("[ERRORE] ADB")
            self.log(f"ERRORE ADB: {e}")
    
    def start_scan_animation(self):
        """Start the scanning animation in the tree."""
        self.is_scanning = True
        self.scan_animation_dots = 0
        
        # Add scanning placeholder item
        self.scanning_item = QTreeWidgetItem(["Scansione", "", "", "", "", ""])
        self.scanning_item.setFlags(self.scanning_item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
        self.folder_tree.addTopLevelItem(self.scanning_item)
        
        # Start animation timer
        self.scan_animation_timer = QTimer()
        self.scan_animation_timer.timeout.connect(self.update_scan_animation)
        self.scan_animation_timer.start(500)  # Update every 500ms
    
    def update_scan_animation(self):
        """Update the scanning animation."""
        if not self.is_scanning:
            return
        
        self.scan_animation_dots = (self.scan_animation_dots + 1) % 4
        dots = "." * self.scan_animation_dots
        self.scanning_item.setText(0, f"Scansione{dots}")
    
    def stop_scan_animation(self):
        """Stop the scanning animation."""
        self.is_scanning = False
        if self.scan_animation_timer:
            self.scan_animation_timer.stop()
            self.scan_animation_timer = None
    
    def scan_device(self):
        """Start device scan in background."""
        if not self.selected_storage:
            self.log("ERRORE: Seleziona almeno uno storage da scansionare")
            return
        
        if not self.selected_categories:
            self.log("ERRORE: Seleziona almeno una categoria")
            return
        
        storage_names = ", ".join(self.selected_storage.values())
        cat_names = ", ".join([FILE_CATEGORIES[c]['name'] for c in self.selected_categories])
        self.log(f"Scansione {storage_names} for {cat_names}...")
        
        self.folder_tree.clear()
        self.backup_btn.setEnabled(False)
        self.select_all_checkbox.setEnabled(False)
        self.scan_btn.setEnabled(False)
        self.storage_btn.setEnabled(False)
        
        # Show scanning animation
        self.start_scan_animation()
        
        self.scan_worker = ScanWorker(self.selected_storage, self.selected_categories)
        self.scan_worker.progress.connect(lambda msg: self.log(f"   {msg}"))
        self.scan_worker.finished.connect(self.on_scan_finished)
        self.scan_worker.error.connect(lambda e: self.log(f"ERRORE: {e}"))
        self.scan_worker.start()
    
    def on_scan_finished(self, result: Optional[ScanResult]):
        """Handle scan completion."""
        self.stop_scan_animation()
        self.folder_tree.clear()
        self.scan_result = result
        
        if not result or not result.folders:
            self.log("Nessun media trovato sul dispositivo.")
            return
        
        self.log(f"[OK] Scansione completata: {result.total_media:,} file trovati")
        
        # Block signals while populating
        self.folder_tree.blockSignals(True)
        
        # Populate tree
        for folder in result.folders:
            item = NumericTreeWidgetItem([
                folder.name,
                folder.storage_type,
                str(folder.file_count),
                folder.size_human()
            ])
            item.setCheckState(0, Qt.CheckState.Checked)
            item.setData(0, Qt.ItemDataRole.UserRole, folder)
            # Store numeric values for proper sorting
            item.setData(2, Qt.ItemDataRole.UserRole, folder.file_count)
            item.setData(3, Qt.ItemDataRole.UserRole, folder.total_size)
            self.folder_tree.addTopLevelItem(item)
        
        self.folder_tree.blockSignals(False)
        
        # Update summary
        self.summary_label.setText(
            f"Totale: {result.total_media:,} file ({result.size_human()})"
        )
        
        # Update statistics display
        self.update_stats_display(result)
        
        # Re-enable controls
        self.select_all_checkbox.setEnabled(True)
        self.select_all_checkbox.setChecked(True)
        self.scan_btn.setEnabled(True)
        self.storage_btn.setEnabled(True)
        self.update_backup_button()
    
    def on_select_all_changed(self, state: int):
        """Handle select all checkbox change."""
        self.folder_tree.blockSignals(True)
        
        new_state = Qt.CheckState.Checked if state == Qt.CheckState.Checked.value else Qt.CheckState.Unchecked
        for i in range(self.folder_tree.topLevelItemCount()):
            item = self.folder_tree.topLevelItem(i)
            item.setCheckState(0, new_state)
        
        self.folder_tree.blockSignals(False)
        self.update_backup_button()
    
    def on_item_changed(self, item: QTreeWidgetItem, column: int):
        """Handle tree item change to update select all checkbox state."""
        if column != 0:
            return
        
        # Check if all items are checked, unchecked, or mixed
        all_checked = True
        all_unchecked = True
        
        for i in range(self.folder_tree.topLevelItemCount()):
            item = self.folder_tree.topLevelItem(i)
            if item.checkState(0) == Qt.CheckState.Checked:
                all_unchecked = False
            else:
                all_checked = False
        
        # Update checkbox without triggering its signal
        self.select_all_checkbox.blockSignals(True)
        if all_checked:
            self.select_all_checkbox.setChecked(True)
        elif all_unchecked:
            self.select_all_checkbox.setChecked(False)
        else:
            self.select_all_checkbox.setTristate(True)
            self.select_all_checkbox.setCheckState(Qt.CheckState.PartiallyChecked)
        self.select_all_checkbox.blockSignals(False)
        
        # Reset tristate after setting
        if all_checked or all_unchecked:
            self.select_all_checkbox.setTristate(False)
        
        self.update_backup_button()
    
    def get_selected_folders(self) -> list[MediaFolder]:
        """Get list of selected folders."""
        folders = []
        for i in range(self.folder_tree.topLevelItemCount()):
            item = self.folder_tree.topLevelItem(i)
            if item.checkState(0) == Qt.CheckState.Checked:
                folder = item.data(0, Qt.ItemDataRole.UserRole)
                if folder:
                    folders.append(folder)
        return folders
    
    def update_backup_button(self):
        """Update backup button enabled state."""
        has_selection = len(self.get_selected_folders()) > 0
        has_destination = self.destination is not None
        self.backup_btn.setEnabled(has_selection and has_destination)
    
    def select_destination(self):
        """Open file dialog to select destination."""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Seleziona Cartella di Destinazione",
            os.path.expanduser("~"),
            QFileDialog.Option.ShowDirsOnly
        )
        
        if folder:
            self.destination = folder
            self.dest_label.setText(folder)
            self.dest_label.setStyleSheet("color: #4CAF50;")
            self.log(f"Destinazione selezionata: {folder}")
            self.update_backup_button()
    
    def start_backup(self):
        """Start backup process."""
        folders = self.get_selected_folders()
        
        if not folders:
            QMessageBox.warning(self, "Attenzione", "Seleziona almeno una cartella.")
            return
        
        if not self.destination:
            QMessageBox.warning(self, "Attenzione", "Seleziona una destinazione per il backup.")
            return
        
        # Disable backup button during analysis
        self.backup_btn.setEnabled(False)
        self.backup_btn.setText("Analisi...")
        
        # Analyze in background
        self.log("\nAnalisi file in corso...")
        self.analyze_worker = AnalyzeWorker(folders, self.selected_categories, self.destination)
        self.analyze_worker.finished.connect(self.on_analyze_finished)
        self.analyze_worker.error.connect(lambda e: self.log(f"ERRORE: {e}"))
        self.analyze_worker.start()
    
    def on_analyze_finished(self, to_sync: list, already_synced: list):
        """Handle analyze completion and show confirmation dialog."""
        # Re-enable backup button
        self.backup_btn.setEnabled(True)
        self.backup_btn.setText("Avvia Backup")
        
        sync_size = sum(f.size for f in already_synced)
        new_size = sum(f.size for f in to_sync)
        
        self.log(f"   [OK] Gia sincronizzati: {len(already_synced):,} file ({format_size(sync_size)})")
        self.log(f"   [>>] Da scaricare: {len(to_sync):,} file ({format_size(new_size)})")
        
        if not to_sync:
            self.log("\nTutto sincronizzato! Nessun nuovo file da scaricare.")
            QMessageBox.information(self, "Completato", "Tutti i file sono gia sincronizzati!")
            return
        
        # Confirm
        reply = QMessageBox.question(
            self,
            "Conferma Backup",
            f"Scaricare {len(to_sync):,} file ({format_size(new_size)})?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            self.log("Backup annullato.")
            return
        
        # Start backup
        self.log("\nAvvio backup...")
        
        # Update UI
        self.backup_btn.hide()
        self.cancel_btn.show()
        self.progress_bar.show()
        self.progress_bar.setMaximum(len(to_sync) + len(already_synced))
        self.progress_bar.setValue(len(already_synced))
        self.dest_btn.setEnabled(False)
        self.select_all_checkbox.setEnabled(False)
        
        # Start worker
        folders = self.get_selected_folders()
        self.backup_worker = BackupWorker(folders, self.selected_categories, self.destination)
        self.backup_worker.progress.connect(self.on_backup_progress)
        self.backup_worker.finished.connect(self.on_backup_finished)
        self.backup_worker.start()
    
    def on_backup_progress(self, progress: BackupProgress):
        """Handle backup progress update."""
        total_done = progress.completed_files + progress.skipped_files
        self.progress_bar.setValue(total_done)
        
        if progress.current_file:
            self.progress_bar.setFormat(f"%p% - {progress.current_file}")
            
        if progress.error_message:
            # Log the specific error
            self.log(f"[ERRORE] File: {progress.current_file}")
            self.log(f"   -> {progress.error_message}")
            self.log("   Continuo con il prossimo file...")
    
    def on_backup_finished(self, progress: BackupProgress, elapsed_time: float):
        """Handle backup completion."""
        self.backup_worker = None
        
        # Reset UI
        self.backup_btn.show()
        self.cancel_btn.hide()
        self.progress_bar.hide()
        self.dest_btn.setEnabled(True)
        self.select_all_checkbox.setEnabled(True)
        
        # Format elapsed time
        minutes, seconds = divmod(int(elapsed_time), 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            time_str = f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            time_str = f"{minutes}m {seconds}s"
        else:
            time_str = f"{seconds}s"
        
        if progress.status == BackupStatus.COMPLETED:
            self.log(f"\n[OK] Backup completato in {time_str}!")
            self.log(f"   Scaricati: {progress.completed_files:,} file")
            self.log(f"   Gia presenti: {progress.skipped_files:,} file")
            if progress.failed_files > 0:
                self.log(f"   Falliti: {progress.failed_files:,} file")
            
            QMessageBox.information(
                self,
                "Backup Completato",
                f"Backup completato con successo in {time_str}!\n\n"
                f"- Scaricati: {progress.completed_files:,} file\n"
                f"- Gia presenti: {progress.skipped_files:,} file\n"
                f"- Falliti: {progress.failed_files:,} file"
            )
        elif progress.status == BackupStatus.CANCELLED:
            self.log(f"\n[!] Backup interrotto dall'utente dopo {time_str}.")
            self.log("   I progressi sono stati salvati. Riavvia per riprendere.")
    
    def cancel_backup(self):
        """Cancel ongoing backup."""
        if self.backup_worker:
            self.log("\nAnnullamento in corso...")
            self.backup_worker.cancel()
    
    def closeEvent(self, event):
        """Handle window close."""
        if self.backup_worker and self.backup_worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Backup in Corso",
                "Un backup e in corso. Vuoi annullarlo e chiudere?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
            
            self.backup_worker.cancel()
            self.backup_worker.wait(3000)  # Wait max 3 seconds
        
        if self.log_file:
            try:
                self.log_file.write("=== Application Closed ===\n")
                self.log_file.close()
            except OSError:
                pass
        
        event.accept()


def run_gui():
    """Run the GUI application."""
    app = QApplication(sys.argv)
    app.setApplicationName("Android Media Backup")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())
