"""
GUI Dialogs Module
Dialog windows for storage and category selection.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QListWidget, QListWidgetItem, QDialogButtonBox
)
from PySide6.QtCore import Qt

from core.categories import FILE_CATEGORIES


class StorageSelectionDialog(QDialog):
    """Dialog for selecting which storage to scan."""
    
    def __init__(self, available_storage: dict[str, str], parent=None):
        """
        Args:
            available_storage: Dict mapping path -> display name
        """
        super().__init__(parent)
        self.available_storage = available_storage
        self.selected_storage: dict[str, str] = {}
        
        self.setWindowTitle("Seleziona Storage")
        self.setMinimumWidth(300)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Instructions
        label = QLabel("Seleziona gli storage da scansionare:")
        layout.addWidget(label)
        
        # List with checkboxes
        self.list_widget = QListWidget()
        for path, name in self.available_storage.items():
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            # Default: select internal, not SD cards
            if name == "Interno":
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, path)
            self.list_widget.addItem(item)
        
        layout.addWidget(self.list_widget)
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def get_selected_storage(self) -> dict[str, str]:
        """Return dict of selected storage paths and names."""
        selected = {}
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                path = item.data(Qt.ItemDataRole.UserRole)
                name = item.text()
                selected[path] = name
        return selected


class CategorySelectionDialog(QDialog):
    """Dialog for selecting which file categories to scan."""
    
    def __init__(self, parent=None, selected_categories: list[str] = None):
        super().__init__(parent)
        self.selected_categories = selected_categories or ['media']
        
        self.setWindowTitle("Seleziona Categorie")
        self.setMinimumWidth(300)
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Instructions
        label = QLabel("Seleziona le categorie di file da scansionare:")
        layout.addWidget(label)
        
        # List with checkboxes
        self.list_widget = QListWidget()
        for cat_id, cat_info in FILE_CATEGORIES.items():
            item = QListWidgetItem(cat_info['name'])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            if cat_id in self.selected_categories:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, cat_id)
            self.list_widget.addItem(item)
        
        layout.addWidget(self.list_widget)
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def get_selected_categories(self) -> list[str]:
        """Return list of selected category IDs."""
        selected = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                cat_id = item.data(Qt.ItemDataRole.UserRole)
                selected.append(cat_id)
        return selected
