"""
GUI Application Module
PyQt6-based graphical interface for Android Media Backup.
"""

import os
import sys
from typing import Optional

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTreeWidget, QTreeWidgetItem, QProgressBar,
    QTextEdit, QFileDialog, QMessageBox, QFrame, QSplitter, QHeaderView,
    QCheckBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QIcon

from core.adb import check_adb_available, get_connected_devices, get_single_device, ADBError
from core.scanner import scan_media_folders, MediaFolder, ScanResult
from core.backup import BackupManager, BackupProgress, BackupStatus


def format_size(size_bytes: int) -> str:
    """Format bytes to human readable string."""
    if size_bytes >= 1024 ** 3:
        return f"{size_bytes / (1024**3):.2f} GB"
    elif size_bytes >= 1024 ** 2:
        return f"{size_bytes / (1024**2):.2f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.2f} KB"
    return f"{size_bytes} B"


class ScanWorker(QThread):
    """Worker thread for scanning device."""
    finished = pyqtSignal(object)  # ScanResult or None
    progress = pyqtSignal(str)  # Current folder being scanned
    error = pyqtSignal(str)
    
    def run(self):
        try:
            def on_progress(path: str, index: int, total: int):
                self.progress.emit(f"Scansione: {path}")
            
            result = scan_media_folders(progress_callback=on_progress)
            self.finished.emit(result)
        except ADBError as e:
            self.error.emit(str(e))
            self.finished.emit(None)


class BackupWorker(QThread):
    """Worker thread for backup operation."""
    progress = pyqtSignal(object)  # BackupProgress
    finished = pyqtSignal(object)  # Final BackupProgress
    
    def __init__(self, folders: list[MediaFolder], destination: str):
        super().__init__()
        self.folders = folders
        self.destination = destination
        self.manager: Optional[BackupManager] = None
    
    def run(self):
        self.manager = BackupManager(self.destination)
        
        def on_progress(bp: BackupProgress):
            self.progress.emit(bp)
        
        result = self.manager.start_backup(self.folders, progress_callback=on_progress)
        self.finished.emit(result)
    
    def cancel(self):
        if self.manager:
            self.manager.cancel()


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
        
        self.init_ui()
        self.check_device()
    
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
        
        # Splitter for main content
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Folder tree
        tree_container = self.create_folder_tree()
        splitter.addWidget(tree_container)
        
        # Log area
        log_container = self.create_log_area()
        splitter.addWidget(log_container)
        
        splitter.setSizes([400, 200])
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
        title = QLabel("Android Media Backup")
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
        self.folder_tree.setHeaderLabels(["Cartella", "Foto", "Video", "Totale", "Dimensione"])
        self.folder_tree.setRootIsDecorated(False)
        self.folder_tree.setAlternatingRowColors(False)
        self.folder_tree.itemChanged.connect(self.on_item_changed)
        
        header = self.folder_tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        
        layout.addWidget(self.folder_tree)
        
        # Summary label
        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("color: #888; margin-top: 5px;")
        layout.addWidget(self.summary_label)
        
        return container
    
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
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
            }
            QWidget {
                color: #e0e0e0;
                font-family: 'Segoe UI', 'Ubuntu', sans-serif;
            }
            QFrame#header {
                background-color: #2d2d2d;
                border-radius: 8px;
                padding: 10px;
            }
            QTreeWidget {
                background-color: #2d2d2d;
                border: 1px solid #3d3d3d;
                border-radius: 4px;
            }
            QTreeWidget::item {
                padding: 5px;
            }
            QTreeWidget::item:selected {
                background-color: #3d3d3d;
            }
            QTextEdit {
                background-color: #1a1a1a;
                border: 1px solid #3d3d3d;
                border-radius: 4px;
            }
            QPushButton {
                background-color: #3d3d3d;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #4d4d4d;
            }
            QPushButton:pressed {
                background-color: #2d2d2d;
            }
            QPushButton:disabled {
                background-color: #2d2d2d;
                color: #666;
            }
            QProgressBar {
                border: 1px solid #3d3d3d;
                border-radius: 4px;
                text-align: center;
                background-color: #2d2d2d;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 3px;
            }
            QHeaderView::section {
                background-color: #2d2d2d;
                border: none;
                padding: 5px;
            }
            QCheckBox {
                spacing: 5px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
        """)
    
    def log(self, message: str):
        """Add message to log."""
        self.log_text.append(message)
        # Auto scroll to bottom
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def check_device(self):
        """Check for connected Android device."""
        self.device_label.setText("Ricerca dispositivo...")
        self.folder_tree.clear()
        self.summary_label.setText("")
        self.select_all_checkbox.setEnabled(False)
        
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
            
            # Start scanning
            self.scan_device()
            
        except ADBError as e:
            self.device_label.setText("[ERRORE] ADB")
            self.log(f"ERRORE ADB: {e}")
    
    def start_scan_animation(self):
        """Start the scanning animation in the tree."""
        self.is_scanning = True
        self.scan_animation_dots = 0
        
        # Add scanning placeholder item
        self.scanning_item = QTreeWidgetItem(["Scansione", "", "", "", ""])
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
        self.log("Scansione dispositivo in corso...")
        self.folder_tree.clear()
        self.backup_btn.setEnabled(False)
        self.select_all_checkbox.setEnabled(False)
        
        # Show scanning animation
        self.start_scan_animation()
        
        self.scan_worker = ScanWorker()
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
            item = QTreeWidgetItem([
                folder.name,
                str(folder.photo_count),
                str(folder.video_count),
                str(folder.total_count),
                folder.size_human()
            ])
            item.setCheckState(0, Qt.CheckState.Checked)
            item.setData(0, Qt.ItemDataRole.UserRole, folder)
            self.folder_tree.addTopLevelItem(item)
        
        self.folder_tree.blockSignals(False)
        
        # Update summary
        self.summary_label.setText(
            f"Totale: {result.total_photos:,} foto, {result.total_videos:,} video ({result.size_human()})"
        )
        
        # Enable select all checkbox
        self.select_all_checkbox.setEnabled(True)
        self.select_all_checkbox.setChecked(True)
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
        
        # Analyze first
        self.log("\nAnalisi file in corso...")
        manager = BackupManager(self.destination)
        to_sync, already_synced = manager.analyze_folders(folders)
        
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
        self.backup_worker = BackupWorker(folders, self.destination)
        self.backup_worker.progress.connect(self.on_backup_progress)
        self.backup_worker.finished.connect(self.on_backup_finished)
        self.backup_worker.start()
    
    def on_backup_progress(self, progress: BackupProgress):
        """Handle backup progress update."""
        total_done = progress.completed_files + progress.skipped_files
        self.progress_bar.setValue(total_done)
        
        if progress.current_file:
            self.progress_bar.setFormat(f"%p% - {progress.current_file}")
    
    def on_backup_finished(self, progress: BackupProgress):
        """Handle backup completion."""
        self.backup_worker = None
        
        # Reset UI
        self.backup_btn.show()
        self.cancel_btn.hide()
        self.progress_bar.hide()
        self.dest_btn.setEnabled(True)
        self.select_all_checkbox.setEnabled(True)
        
        if progress.status == BackupStatus.COMPLETED:
            self.log(f"\n[OK] Backup completato!")
            self.log(f"   Scaricati: {progress.completed_files:,} file")
            self.log(f"   Gia presenti: {progress.skipped_files:,} file")
            if progress.failed_files > 0:
                self.log(f"   Falliti: {progress.failed_files:,} file")
            
            QMessageBox.information(
                self,
                "Backup Completato",
                f"Backup completato con successo!\n\n"
                f"- Scaricati: {progress.completed_files:,} file\n"
                f"- Gia presenti: {progress.skipped_files:,} file\n"
                f"- Falliti: {progress.failed_files:,} file"
            )
        elif progress.status == BackupStatus.CANCELLED:
            self.log("\n[!] Backup interrotto dall'utente.")
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
        
        event.accept()


def run_gui():
    """Run the GUI application."""
    app = QApplication(sys.argv)
    app.setApplicationName("Android Media Backup")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())
