"""
TUI Modals Module
Modal dialog screens for storage, category, and destination selection.
"""

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Static, Button, Input, SelectionList

from core.categories import FILE_CATEGORIES


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
