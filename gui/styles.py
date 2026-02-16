"""
GUI Styles Module
Application stylesheet for the dark theme.
"""


def get_stylesheet() -> str:
    """Return the application stylesheet."""
    return """
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
    """
