"""
GUI Widgets Module
Custom widget classes for the GUI.
"""

from PySide6.QtWidgets import QTreeWidgetItem
from PySide6.QtCore import Qt


class NumericTreeWidgetItem(QTreeWidgetItem):
    """QTreeWidgetItem that sorts numeric columns correctly."""
    
    # Columns that contain numeric data (0-indexed)
    NUMERIC_COLUMNS = {2, 3, 4, 5}  # Foto, Video, Totale, Dimensione
    
    def __lt__(self, other: QTreeWidgetItem) -> bool:
        column = self.treeWidget().sortColumn()
        
        if column in self.NUMERIC_COLUMNS:
            # Get numeric data stored in UserRole
            my_value = self.data(column, Qt.ItemDataRole.UserRole)
            other_value = other.data(column, Qt.ItemDataRole.UserRole)
            
            if my_value is not None and other_value is not None:
                return my_value < other_value
        
        # Fall back to string comparison
        return self.text(column) < other.text(column)
