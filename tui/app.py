"""
TUI Application Module
Modern Textual-based terminal interface for Android Media Backup.
LazyVim-inspired design with responsive panels and smooth animations.
"""

import time
from typing import Optional

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import (
    Footer, Static, Button, ProgressBar, Tree, Rule
)
from textual.worker import get_current_worker

from core.adb import check_adb_available, get_connected_devices, ADBError
from core.scanner import scan_media_folders, ScanResult, get_storage_roots
from core.categories import FILE_CATEGORIES
from core.models import MediaFolder
from core.utils import format_size
from core.backup import BackupManager, BackupProgress, BackupStatus

from .widgets import GradientHeader, StatusPanel, StatsPanel, ClickableDestination, ActionButton
from .modals import StorageModal, CategoryModal, DestinationModal
from .folder_tree import FolderTree
from .log_panel import LogPanel


class AndroSyncTUI(App):
    """AndroSync TUI Application - LazyVim-inspired design."""
    
    TITLE = "AndroSync"
    
    CSS = """
    Screen {
        background: $surface;
    }
    
    /* ── Header ───────────────────────────────────────────────── */
    #app-header {
        height: 3;
        background: $primary-background;
        border-bottom: solid $primary;
        padding: 0 2;
    }
    
    #header-title {
        height: 100%;
        content-align: center middle;
    }
    
    /* ── Main Layout ──────────────────────────────────────────── */
    #main-container {
        height: 1fr;
        padding: 1;
    }
    
    #left-panel {
        width: 1fr;
        height: 100%;
        margin-right: 1;
    }
    
    #right-panel {
        width: 45;
        height: 100%;
    }
    
    /* ── Status Cards ─────────────────────────────────────────── */
    .card {
        background: $panel;
        border: round $primary-darken-2;
        padding: 1;
        margin-bottom: 1;
    }
    
    .card-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    
    #status-panel {
        height: auto;
    }
    
    #stats-panel {
        height: auto;
        text-align: center;
    }
    
    /* ── Folder Tree ──────────────────────────────────────────── */
    #folder-tree {
        height: 1fr;
        border: round $primary;
        background: $panel;
        padding: 0 1;
        scrollbar-gutter: stable;
    }
    
    #folder-tree:focus {
        border: round $secondary;
    }
    
    Tree {
        scrollbar-size: 1 1;
    }
    
    Tree > .tree--guides {
        color: $primary-darken-3;
    }
    
    Tree > .tree--guides-hover {
        color: $primary;
    }
    
    Tree > .tree--guides-selected {
        color: $secondary;
    }
    
    /* ── Action Buttons ───────────────────────────────────────── */
    #action-buttons {
        height: auto;
        align: center middle;
        padding: 1;
    }
    
    #action-buttons Button {
        margin: 0 0 1 0;
        width: 100%;
    }
    
    #btn-backup {
        margin-top: 1;
    }
    
    /* ── Progress Section ─────────────────────────────────────── */
    #progress-section {
        height: auto;
        display: none;
    }
    
    #progress-section.visible {
        display: block;
    }
    
    #progress-bar {
        margin: 1 0;
    }
    
    #log-panel {
        height: 10;
        border: round $primary-darken-2;
        background: $panel;
        padding: 0 1;
    }
    
    /* ── Destination ──────────────────────────────────────────── */
    #destination-display {
        height: 3;
        background: $panel;
        border: round $primary-darken-2;
        padding: 0 1;
        content-align: center middle;
    }
    
    #destination-display:hover {
        border: round $secondary;
        background: $primary-background;
    }
    
    /* ── Footer ───────────────────────────────────────────────── */
    Footer {
        background: $primary-background;
    }
    
    Footer > .footer--key {
        background: $secondary;
        color: $text;
    }
    """
    
    BINDINGS = [
        Binding("s", "select_storage", "Storage", priority=True),
        Binding("c", "select_categories", "Categories", priority=True),
        Binding("a", "scan", "Scan", priority=True),
        Binding("d", "select_destination", "Destination", priority=True),
        Binding("b", "backup", "Backup", priority=True),
        Binding("space", "toggle_folder", "Select", show=False),
        Binding("t", "toggle_all", "Toggle All"),
        Binding("r", "refresh", "Refresh"),
        Binding("q", "quit", "Quit"),
    ]
    
    def __init__(self):
        super().__init__()
        self.device_connected: bool = False
        self.device_info: Optional[str] = None
        self.available_storage: dict[str, str] = {}
        self.selected_storage: dict[str, str] = {}
        self.selected_categories: list[str] = ['media']
        self.scan_result: Optional[ScanResult] = None
        self.destination: str = "./backup"
        self.backup_manager: Optional[BackupManager] = None
        self._backup_cancelled = False
        
        # Setup logging
        self.log_file = None
        self.setup_logging()
    
    def setup_logging(self):
        """Setup logging to file."""
        import datetime
        import os
        
        # Create logs directory
        log_dir = os.path.join(os.getcwd(), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        # Create log file with timestamp
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"tui_{timestamp}.log"
        log_path = os.path.join(log_dir, filename)
        
        try:
            self.log_file = open(log_path, 'a', encoding='utf-8')
            # Write header
            self.log_file.write(f"=== AndroSync TUI Log Started: {timestamp} ===\n")
            self.log_file.flush()
        except OSError:
            pass
    
    def _log_to_file(self, message: str) -> None:
        """Internal helper to log to file (called by LogPanel)."""
        if self.log_file:
            try:
                import datetime
                timestamp = datetime.datetime.now().strftime("%H:%M:%S")
                self.log_file.write(f"[{timestamp}] {message}\n")
                self.log_file.flush()
            except OSError:
                pass
    
    def compose(self) -> ComposeResult:
        with Container(id="app-header"):
            yield GradientHeader()
        
        with Horizontal(id="main-container"):
            with Vertical(id="left-panel"):
                yield FolderTree("󰉋 Folders", id="folder-tree")
                yield ClickableDestination(
                    "󰉋  [dim]Destination:[/dim] ./backup  [dim italic](click to change)[/dim italic]",
                    id="destination-display"
                )
                
                with Container(id="progress-section"):
                    yield ProgressBar(id="progress-bar", total=100, show_eta=True)
                    yield LogPanel(id="log-panel")
            
            with Vertical(id="right-panel"):
                with Container(classes="card", id="status-panel"):
                    yield Static("󰋜  Status", classes="card-title")
                    yield StatusPanel(id="status-content")
                
                with Container(classes="card", id="stats-panel"):
                    yield Static("󰄪  Statistics", classes="card-title")
                    yield StatsPanel(id="stats-content")
                
                with Vertical(id="action-buttons"):
                    yield ActionButton("Scan Device", "󰑓", id="btn-scan", variant="primary")
                    yield Rule()
                    yield ActionButton("Start Backup", "󰁯", id="btn-backup", variant="success", disabled=True)
        
        yield Footer()
    
    def on_mount(self) -> None:
        """Initialize on mount."""
        self.check_device()
    
    @work(exclusive=True)
    async def check_device(self) -> None:
        """Check for connected device."""
        status_panel = self.query_one("#status-content", StatusPanel)
        
        if not check_adb_available():
            status_panel.device_status = "[red]󰜺 ADB not found[/red]"
            self.device_connected = False
            return
        
        try:
            devices = get_connected_devices()
            authorized = [d for d in devices if d.status == "device"]
            
            if len(authorized) == 0:
                status_panel.device_status = "[yellow]󰜺 No device connected[/yellow]"
                self.device_connected = False
            elif len(authorized) > 1:
                status_panel.device_status = "[yellow]󰀨 Multiple devices[/yellow]"
                self.device_connected = False
            else:
                device = authorized[0]
                self.device_info = f"{device.model}"
                status_panel.device_status = f"[green]󰄬 {self.device_info}[/green]"
                self.device_connected = True
                
                # Get available storage
                self.available_storage = get_storage_roots()
                if self.available_storage:
                    first_path = list(self.available_storage.keys())[0]
                    self.selected_storage = {first_path: self.available_storage[first_path]}
                    self._update_storage_display()
                    
        except ADBError as e:
            status_panel.device_status = f"[red]󰜺 Error: {e}[/red]"
            self.device_connected = False
    
    def _update_storage_display(self) -> None:
        """Update storage display in status panel."""
        status_panel = self.query_one("#status-content", StatusPanel)
        if self.selected_storage:
            names = list(self.selected_storage.values())
            status_panel.storage_info = f"[cyan]{', '.join(names)}[/cyan]"
        else:
            status_panel.storage_info = "[dim]None selected[/dim]"
    
    def _update_category_display(self) -> None:
        """Update category display in status panel."""
        status_panel = self.query_one("#status-content", StatusPanel)
        if self.selected_categories:
            names = [cat.capitalize() for cat in self.selected_categories]
            status_panel.category_info = f"[magenta]{', '.join(names)}[/magenta]"
        else:
            status_panel.category_info = "[dim]None[/dim]"
    
    def _update_stats_display(self) -> None:
        """Update stats panel - adapts to selected categories."""
        stats_panel = self.query_one("#stats-content", StatsPanel)
        if self.scan_result:
            stats_panel.files_count = self.scan_result.total_files
            stats_panel.total_size = self.scan_result.size_human()
            # Show category-aware label
            if self.selected_categories:
                stats_panel.categories_label = ", ".join(cat.capitalize() for cat in self.selected_categories)
            else:
                stats_panel.categories_label = "files"
        else:
            stats_panel.files_count = 0
            stats_panel.total_size = "0 B"
            stats_panel.categories_label = "files"
    
    def action_select_storage(self) -> None:
        """Open storage selection modal."""
        if not self.device_connected:
            self.notify("No device connected", severity="warning")
            return
        
        if not self.available_storage:
            self.notify("No storage available", severity="warning")
            return
        
        def on_dismiss(selected: dict[str, str]) -> None:
            if selected:
                self.selected_storage = selected
                self._update_storage_display()
        
        self.push_screen(StorageModal(self.available_storage, self.selected_storage), on_dismiss)
    
    def action_select_categories(self) -> None:
        """Open category selection modal."""
        def on_dismiss(selected: list[str]) -> None:
            # Modal always returns valid list (current or new selection)
            self.selected_categories = selected
            self._update_category_display()
        
        self.push_screen(CategoryModal(self.selected_categories), on_dismiss)
    
    def action_select_destination(self) -> None:
        """Open destination input modal."""
        def on_dismiss(destination: str) -> None:
            if destination:
                self.destination = destination
                dest_display = self.query_one("#destination-display", ClickableDestination)
                dest_display.update(f"󰉋  [dim]Destination:[/dim] {destination}  [dim italic](click to change)[/dim italic]")
        
        self.push_screen(DestinationModal(self.destination), on_dismiss)
    
    def action_scan(self) -> None:
        """Start scanning device."""
        if not self.device_connected:
            self.notify("No device connected", severity="error")
            return
        
        if not self.selected_storage:
            self.notify("Select storage first (press S)", severity="warning")
            return
        
        self.run_scan()
    
    def action_refresh(self) -> None:
        """Refresh device connection."""
        self.check_device()
        self.notify("Refreshing device connection...")
    
    @work(exclusive=True, thread=True)
    def run_scan(self) -> None:
        """Run device scan in background thread."""
        self.call_from_thread(self._show_progress, "󰑓  Scanning device...")
        
        try:
            result = scan_media_folders(
                storage_paths=self.selected_storage,
                categories=self.selected_categories,
                progress_callback=lambda path, idx, total: self.call_from_thread(
                    self._log_message, f"[dim]Scanning:[/dim] {path.split('/')[-1]}"
                )
            )
            
            self.scan_result = result
            self.call_from_thread(self._on_scan_complete, result)
            
        except ADBError as e:
            self.call_from_thread(self.notify, f"Scan error: {e}", severity="error")
        finally:
            self.call_from_thread(self._hide_progress)
    
    def _show_progress(self, message: str = "") -> None:
        """Show progress section."""
        section = self.query_one("#progress-section", Container)
        section.add_class("visible")
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.clear()
        if message:
            log_panel.write(message)
    
    def _hide_progress(self) -> None:
        """Hide progress section."""
        section = self.query_one("#progress-section", Container)
        section.remove_class("visible")
    
    def _log_message(self, message: str) -> None:
        """Log a message to the log panel."""
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.write(message)
    
    def _on_scan_complete(self, result: ScanResult) -> None:
        """Handle scan completion."""
        self._update_stats_display()
        
        # Populate tree
        tree = self.query_one("#folder-tree", FolderTree)
        tree.populate(result.folders)
        
        # Enable backup button
        btn_backup = self.query_one("#btn-backup", Button)
        btn_backup.disabled = len(result.folders) == 0
        
        self.notify(f"Found {len(result.folders)} folders with {result.total_files:,} files", timeout=3)
    
    def action_toggle_folder(self) -> None:
        """Toggle selection on current folder."""
        tree = self.query_one("#folder-tree", FolderTree)
        if tree.cursor_node:
            tree.toggle_selection(tree.cursor_node)
    
    def action_toggle_all(self) -> None:
        """Toggle all folders (select all if not all selected, else deselect all)."""
        tree = self.query_one("#folder-tree", FolderTree)
        
        if not tree.has_folders():
            self.notify("No folders to select", severity="warning")
            return
        
        if tree.all_selected():
            tree.deselect_all()
            self.notify("Deselected all folders")
        else:
            tree.select_all()
            self.notify("Selected all folders")
    
    def action_backup(self) -> None:
        """Start backup operation."""
        if not self.device_connected:
            self.notify("No device connected", severity="error")
            return
        
        tree = self.query_one("#folder-tree", FolderTree)
        selected = tree.get_selected_folders()
        
        if not selected:
            self.notify("Select at least one folder", severity="warning")
            return
        
        self._backup_cancelled = False
        self.run_backup(selected)
    
    @work(exclusive=True, thread=True)
    def run_backup(self, folders: list[MediaFolder]) -> None:
        """Run backup in background thread."""
        start_time = time.time()
        
        self.call_from_thread(self._show_progress, "󰋊  Analyzing files...")
        
        try:
            self.backup_manager = BackupManager(self.destination)
            
            # Analyze
            to_sync, already_synced = self.backup_manager.analyze_folders(
                folders, self.selected_categories
            )
            
            sync_size = sum(f.size for f in already_synced)
            new_size = sum(f.size for f in to_sync)
            
            self.call_from_thread(
                self._log_message,
                f"[green]󰄬[/green] Already synced: {len(already_synced):,} files ({format_size(sync_size)})"
            )
            self.call_from_thread(
                self._log_message,
                f"[cyan]󰁯[/cyan] To download: {len(to_sync):,} files ({format_size(new_size)})"
            )
            
            if not to_sync:
                self.call_from_thread(
                    self.notify,
                    "Everything synced! No new files.",
                    severity="information"
                )
                return
            
            # Setup progress bar
            self.call_from_thread(self._setup_backup_progress, len(to_sync))
            
            # Start backup
            def on_progress(bp: BackupProgress):
                if self._backup_cancelled:
                    return
                self.call_from_thread(self._update_backup_progress, bp)
            
            result = self.backup_manager.start_backup(
                folders,
                categories=self.selected_categories,
                progress_callback=on_progress
            )
            
            elapsed_time = time.time() - start_time
            self.call_from_thread(self._on_backup_complete, result, elapsed_time)
            
        except Exception as e:
            self.call_from_thread(self.notify, f"Backup error: {e}", severity="error")
    
    def _setup_backup_progress(self, total: int) -> None:
        """Setup progress bar for backup."""
        progress_bar = self.query_one("#progress-bar", ProgressBar)
        progress_bar.update(total=total, progress=0)
    
    def _update_backup_progress(self, bp: BackupProgress) -> None:
        """Update backup progress."""
        progress_bar = self.query_one("#progress-bar", ProgressBar)
        progress_bar.update(progress=bp.completed_files)
        
        if bp.error_message:
            self._log_message(f"[red]ERROR:[/red] {bp.current_file} -> {bp.error_message}")

        if bp.current_file:
            # Show only filename in UI, but log full path to file
            filename = bp.current_file.split('/')[-1] if '/' in bp.current_file else bp.current_file
            # Log full path (only when file count increases)
            if not hasattr(self, '_last_tui_completed'):
                self._last_tui_completed = 0
            if bp.completed_files > self._last_tui_completed:
                self._log_message(f"[green]󰄬[/green] {bp.current_file}")
                self._last_tui_completed = bp.completed_files
    
    def _on_backup_complete(self, result: BackupProgress, elapsed_time: float) -> None:
        """Handle backup completion."""
        # Format elapsed time
        minutes, seconds = divmod(int(elapsed_time), 60)
        hours, minutes = divmod(minutes, 60)
        if hours > 0:
            time_str = f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            time_str = f"{minutes}m {seconds}s"
        else:
            time_str = f"{seconds}s"
        
        if result.status == BackupStatus.COMPLETED:
            self.notify(
                f"Backup complete in {time_str}: {result.completed_files:,} files",
                severity="information",
                timeout=5
            )
            self._log_message("")
            self._log_message(f"[bold green]╔═══ Backup Complete ({time_str}) ═══╗[/bold green]")
            self._log_message(f"[green]󰄬 Completed:[/green] {result.completed_files:,}")
            self._log_message(f"[blue]󰒭 Skipped:[/blue] {result.skipped_files:,}")
            if result.failed_files > 0:
                self._log_message(f"[red]󰜺 Failed:[/red] {result.failed_files:,}")
        elif result.status == BackupStatus.CANCELLED:
            self.notify(f"Backup cancelled after {time_str}", severity="warning")
    
    @on(Button.Pressed, "#btn-scan")
    def on_scan_button(self) -> None:
        self.action_scan()
    
    @on(Button.Pressed, "#btn-backup")
    def on_backup_button(self) -> None:
        self.action_backup()
    
    @on(Tree.NodeSelected)
    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Handle tree node selection - toggle checkbox."""
        tree = self.query_one("#folder-tree", FolderTree)
        if event.node.data:
            tree.toggle_selection(event.node)

    def on_unmount(self) -> None:
        """Handle unmount."""
        if self.log_file:
            try:
                import datetime
                self.log_file.write(f"=== AndroSync TUI Log Ended: {datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')} ===\n")
                self.log_file.close()
            except OSError:
                pass
