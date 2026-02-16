"""
TUI Log Panel Module
Scrollable log panel for displaying backup progress messages.
"""

from textual.app import ComposeResult
from textual.containers import ScrollableContainer
from textual.widgets import Static


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
        
        # Write to app log file if available
        if hasattr(self.app, '_log_to_file'):
            self.app._log_to_file(message)
    
    def clear(self) -> None:
        """Clear all messages."""
        self.messages.clear()
        self._update_content()
    
    def _update_content(self) -> None:
        """Update the displayed content."""
        content = self.query_one("#log-content", Static)
        content.update("\n".join(self.messages))
