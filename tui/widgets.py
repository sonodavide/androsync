"""
TUI Widgets Module
Custom styled widgets for the TUI interface.
"""

from textual.widgets import Static, Button
from textual.reactive import reactive
from textual.app import ComposeResult

from rich.text import Text
from rich.console import RenderableType


class GradientHeader(Static):
    """Custom header with gradient-like styling."""
    
    def compose(self) -> ComposeResult:
        yield Static(
            "󰀲  [bold cyan]AndroSync[/bold cyan] [dim]│[/dim] Media Backup Tool",
            id="header-title"
        )


class StatusPanel(Static):
    """Status panel showing device and connection info."""
    
    device_status = reactive("Checking...")
    storage_info = reactive("No storage selected")
    category_info = reactive("Media")
    
    def render(self) -> RenderableType:
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
