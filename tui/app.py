"""
TUI Application Module
Modern Textual-based terminal interface for Android Media Backup.
LazyVim-inspired design with responsive panels and smooth animations.
"""

from typing import Optional
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.screen import ModalScreen
from textual.widgets import (
    Header, Footer, Static, Button, Label, 
    Tree, Input, ProgressBar, 
    SelectionList, Rule
)
from textual.widgets.tree import TreeNode
from textual.worker import get_current_worker
from textual.reactive import reactive

from rich.text import Text
from rich.console import RenderableType

from core.adb import check_adb_available, get_connected_devices, ADBError
from core.scanner import scan_media_folders, MediaFolder, ScanResult, get_storage_roots, FILE_CATEGORIES
from core.backup import BackupManager, BackupProgress, BackupStatus


def format_size(size_bytes: int) -> str:
    """Format bytes to human readable string."""
    if size_bytes >= 1024 ** 3:
        return f"{size_bytes / (1024**3):.1f} GB"
    elif size_bytes >= 1024 ** 2:
        return f"{size_bytes / (1024**2):.1f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"


# ═══════════════════════════════════════════════════════════════════════════════
# STYLED WIDGETS
# ═══════════════════════════════════════════════════════════════════════════════

class GradientHeader(Static):
    """Custom header with gradient-like styling."""
    
    def compose(self) -> ComposeResult:
        yield Static(
            "󰀲  [bold cyan]AndroSync[/bold cyan] [dim]│[/dim] Android Backup Tool",
            id="header-title"
        )


class StatusPanel(Static):
    """Status panel showing device and connection info."""
    
    device_status = reactive("Checking...")
    storage_info = reactive("No storage selected")
    category_info = reactive("Media")
    
    def render(self) -> RenderableType:
        # Categories might be long, show on new line if needed
        return Text.from_markup(
            f"[bold]󰄜 Device[/bold]\n   {self.device_status}\n"
            f"[bold]󰉋 Storage[/bold]\n   {self.storage_info}\n"
            f"[bold]󰈙 Categories[/bold]\n   {self.category_info}"
        )


class StatsPanel(Static):
    """Stats panel showing file counts - adapts to selected categories."""
    
    files_count = reactive(0)
    total_size = reactive("0 B")
    categories_label = reactive("files")
    
    def render(self) -> RenderableType:
        return Text.from_markup(
            f"[bold cyan]󰈙 [/bold cyan][cyan]{self.files_count:,}[/cyan] [dim]{self.categories_label}[/dim]  "
            f"[bold green]󰋊 [/bold green][green]{self.total_size}[/green] [dim]total[/dim]"
        )


class ClickableDestination(Static):
    """Clickable destination display."""
    
    class Clicked:
        """Event when destination is clicked."""
        pass
    
    def on_click(self) -> None:
        self.app.action_select_destination()


class ActionButton(Button):
    """Styled action button with icon."""
    
    def __init__(self, label: str, icon: str = "", *args, **kwargs):
        full_label = f"{icon} {label}" if icon else label
        super().__init__(full_label, *args, **kwargs)


# ═══════════════════════════════════════════════════════════════════════════════
# MODAL DIALOGS
# ═══════════════════════════════════════════════════════════════════════════════

class StorageModal(ModalScreen[dict[str, str]]):
    """Modal for selecting storage to scan."""
    
    BINDINGS = [Binding("escape", "cancel", "Cancel")]
    
    CSS = """
    StorageModal {
        align: center middle;
    }
    
    StorageModal > Vertical {
        width: 60;
        height: auto;
        max-height: 80%;
        background: $surface;
        border: round $primary;
        padding: 1 2;
    }
    
    StorageModal .modal-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        padding: 1;
        border-bottom: solid $primary-darken-2;
        margin-bottom: 1;
    }
    
    StorageModal SelectionList {
        height: auto;
        max-height: 12;
        margin: 1 0;
        border: round $primary-darken-2;
    }
    
    StorageModal .modal-buttons {
        height: 3;
        align: center middle;
        margin-top: 1;
    }
    
    StorageModal Button {
        margin: 0 1;
        min-width: 12;
    }
    """
    
    def __init__(self, available_storage: dict[str, str], selected: dict[str, str] = None):
        super().__init__()
        self.available_storage = available_storage
        self.selected = selected or {}
        
    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("󰉋  Select Storage", classes="modal-title")
            yield SelectionList[str](
                *[
                    (f"󰄫  {name}", path, path in self.selected)
                    for path, name in self.available_storage.items()
                ],
                id="storage-list"
            )
            with Horizontal(classes="modal-buttons"):
                yield Button("󰄬  Confirm", variant="primary", id="confirm")
                yield Button("󰜺  Cancel", variant="default", id="cancel")
    
    def action_cancel(self) -> None:
        self.dismiss({})
    
    @on(Button.Pressed, "#confirm")
    def on_confirm(self) -> None:
        selection_list = self.query_one("#storage-list", SelectionList)
        selected = {}
        for path in selection_list.selected:
            if path in self.available_storage:
                selected[path] = self.available_storage[path]
        self.dismiss(selected if selected else self.selected)
    
    @on(Button.Pressed, "#cancel")
    def on_cancel(self) -> None:
        self.dismiss({})


class CategoryModal(ModalScreen[list[str]]):
    """Modal for selecting file categories."""
    
    BINDINGS = [Binding("escape", "cancel", "Cancel")]
    
    CSS = """
    CategoryModal {
        align: center middle;
    }
    
    CategoryModal > Vertical {
        width: 65;
        height: auto;
        max-height: 80%;
        background: $surface;
        border: round $primary;
        padding: 1 2;
    }
    
    CategoryModal .modal-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        padding: 1;
        border-bottom: solid $primary-darken-2;
        margin-bottom: 1;
    }
    
    CategoryModal SelectionList {
        height: auto;
        max-height: 12;
        margin: 1 0;
        border: round $primary-darken-2;
    }
    
    CategoryModal .modal-buttons {
        height: 3;
        align: center middle;
        margin-top: 1;
    }
    
    CategoryModal Button {
        margin: 0 1;
        min-width: 12;
    }
    """
    
    CATEGORY_INFO = {
        'media': ('󰄀', 'Media', 'Photos, Videos, Images'),
        'documents': ('󰈙', 'Documents', 'PDF, Office, Text files'),
        'apk': ('󰀲', 'APK', 'Android applications'),
        'other': ('󰈔', 'Other', 'All other files'),
    }
    
    def __init__(self, selected_categories: list[str] = None):
        super().__init__()
        self.selected_categories = selected_categories or ['media']
        
    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("󰈙  Select Categories", classes="modal-title")
            yield SelectionList[str](
                *[
                    (f"{info[0]}  {info[1]} [dim]({info[2]})[/dim]", cat_id, cat_id in self.selected_categories)
                    for cat_id, info in self.CATEGORY_INFO.items()
                    if cat_id in FILE_CATEGORIES
                ],
                id="category-list"
            )
            with Horizontal(classes="modal-buttons"):
                yield Button("󰄬  Confirm", variant="primary", id="confirm")
                yield Button("󰜺  Cancel", variant="default", id="cancel")
    
    def action_cancel(self) -> None:
        # Return current selection when cancelled (no change)
        self.dismiss(self.selected_categories)
    
    @on(Button.Pressed, "#confirm")
    def on_confirm(self) -> None:
        selection_list = self.query_one("#category-list", SelectionList)
        result = list(selection_list.selected)
        # If nothing selected, keep current selection
        self.dismiss(result if result else self.selected_categories)
    
    @on(Button.Pressed, "#cancel")
    def on_cancel(self) -> None:
        # Return current selection when cancelled (no change)
        self.dismiss(self.selected_categories)


class DestinationModal(ModalScreen[str]):
    """Modal for entering backup destination path."""
    
    BINDINGS = [Binding("escape", "cancel", "Cancel")]
    
    CSS = """
    DestinationModal {
        align: center middle;
    }
    
    DestinationModal > Vertical {
        width: 70;
        height: auto;
        background: $surface;
        border: round $primary;
        padding: 1 2;
    }
    
    DestinationModal .modal-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        padding: 1;
        border-bottom: solid $primary-darken-2;
        margin-bottom: 1;
    }
    
    DestinationModal Input {
        margin: 1 0;
        border: round $primary-darken-2;
    }
    
    DestinationModal .modal-buttons {
        height: 3;
        align: center middle;
        margin-top: 1;
    }
    
    DestinationModal Button {
        margin: 0 1;
        min-width: 12;
    }
    """
    
    def __init__(self, current_destination: str = "./backup"):
        super().__init__()
        self.current_destination = current_destination
        
    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("󰉋  Backup Destination", classes="modal-title")
            yield Input(
                value=self.current_destination,
                placeholder="Enter path (e.g., ~/backup, /mnt/backup)",
                id="destination-input"
            )
            with Horizontal(classes="modal-buttons"):
                yield Button("󰄬  Confirm", variant="primary", id="confirm")
                yield Button("󰜺  Cancel", variant="default", id="cancel")
    
    def action_cancel(self) -> None:
        self.dismiss("")
    
    @on(Button.Pressed, "#confirm")
    def on_confirm(self) -> None:
        input_widget = self.query_one("#destination-input", Input)
        destination = input_widget.value.strip()
        if destination:
            destination = str(Path(destination).expanduser())
        self.dismiss(destination)
    
    @on(Button.Pressed, "#cancel")
    def on_cancel(self) -> None:
        self.dismiss("")
    
    @on(Input.Submitted)
    def on_input_submitted(self) -> None:
        self.on_confirm()


# ═══════════════════════════════════════════════════════════════════════════════
# FOLDER TREE
# ═══════════════════════════════════════════════════════════════════════════════

class FolderTree(Tree):
    """Tree widget for folder selection with styled checkboxes."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.selected_folders: set[str] = set()
        self.folder_data: dict[str, MediaFolder] = {}
        self.show_root = False
        self.guide_depth = 3
    
    def populate(self, folders: list[MediaFolder]) -> None:
        """Populate tree with folder data."""
        self.clear()
        self.selected_folders.clear()
        self.folder_data.clear()
        
        # Group by storage
        by_storage: dict[str, list[MediaFolder]] = {}
        for folder in folders:
            storage = folder.storage_type or "Storage"
            if storage not in by_storage:
                by_storage[storage] = []
            by_storage[storage].append(folder)
        
        for storage_name, storage_folders in by_storage.items():
            storage_node = self.root.add(f"[bold cyan]󰄫 {storage_name}[/bold cyan]", expand=True)
            
            for folder in sorted(storage_folders, key=lambda f: f.name.lower()):
                self.folder_data[folder.path] = folder
                label = self._format_folder_label(folder, selected=False)
                storage_node.add_leaf(label, data=folder.path)
    
    def _format_folder_label(self, folder: MediaFolder, selected: bool) -> str:
        """Format folder label with stats and checkbox."""
        checkbox = "[bold green]󰄬[/bold green]" if selected else "[dim]󰄰[/dim]"
        size_str = folder.size_human()
        count_str = f"{folder.total_count:,}"
        
        return f"{checkbox}  [bold]{folder.name:<24}[/bold] [cyan]{count_str:>8}[/cyan] files  [green]{size_str:>10}[/green]"
    
    def toggle_selection(self, node: TreeNode) -> None:
        """Toggle folder selection."""
        if node.data is None:
            return
        
        folder_path = node.data
        if folder_path in self.folder_data:
            folder = self.folder_data[folder_path]
            
            if folder_path in self.selected_folders:
                self.selected_folders.discard(folder_path)
                selected = False
            else:
                self.selected_folders.add(folder_path)
                selected = True
            
            node.set_label(self._format_folder_label(folder, selected))
    
    def get_selected_folders(self) -> list[MediaFolder]:
        """Get list of selected MediaFolder objects."""
        return [
            self.folder_data[path] 
            for path in self.selected_folders 
            if path in self.folder_data
        ]
    
    def has_folders(self) -> bool:
        """Check if tree has any folders."""
        return len(self.folder_data) > 0
    
    def all_selected(self) -> bool:
        """Check if all folders are selected."""
        return len(self.selected_folders) == len(self.folder_data) and len(self.folder_data) > 0
    
    def select_all(self) -> None:
        """Select all folders."""
        for node in self.root.children:
            for child in node.children:
                if child.data and child.data not in self.selected_folders:
                    self.toggle_selection(child)
    
    def deselect_all(self) -> None:
        """Deselect all folders."""
        for node in self.root.children:
            for child in node.children:
                if child.data and child.data in self.selected_folders:
                    self.toggle_selection(child)


# ═══════════════════════════════════════════════════════════════════════════════
# LOG PANEL
# ═══════════════════════════════════════════════════════════════════════════════

class LogPanel(ScrollableContainer):
    """Scrollable log panel for backup progress."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.messages: list[str] = []
    
    def compose(self) -> ComposeResult:
        yield Static("", id="log-content")
    
    def write(self, message: str) -> None:
        """Add a log message."""
        self.messages.append(message)
        if len(self.messages) > 100:
            self.messages = self.messages[-100:]
        self._update_content()
        self.scroll_end(animate=False)
    
    def clear(self) -> None:
        """Clear all messages."""
        self.messages.clear()
        self._update_content()
    
    def _update_content(self) -> None:
        """Update the displayed content."""
        content = self.query_one("#log-content", Static)
        content.update("\n".join(self.messages))


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════════════════

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
            
            self.call_from_thread(self._on_backup_complete, result)
            
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
        
        if bp.current_file:
            filename = bp.current_file.split('/')[-1] if '/' in bp.current_file else bp.current_file
            self._log_message(f"[green]󰄬[/green] {filename}")
    
    def _on_backup_complete(self, result: BackupProgress) -> None:
        """Handle backup completion."""
        if result.status == BackupStatus.COMPLETED:
            self.notify(
                f"Backup complete: {result.completed_files:,} files",
                severity="information",
                timeout=5
            )
            self._log_message("")
            self._log_message(f"[bold green]╔═══ Backup Complete ═══╗[/bold green]")
            self._log_message(f"[green]󰄬 Completed:[/green] {result.completed_files:,}")
            self._log_message(f"[blue]󰒭 Skipped:[/blue] {result.skipped_files:,}")
            if result.failed_files > 0:
                self._log_message(f"[red]󰜺 Failed:[/red] {result.failed_files:,}")
        elif result.status == BackupStatus.CANCELLED:
            self.notify("Backup cancelled", severity="warning")
    
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
