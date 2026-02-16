"""
TUI Folder Tree Module
Tree widget for folder selection with styled checkboxes.
"""

from textual.widgets import Tree
from textual.widgets.tree import TreeNode

from core.models import MediaFolder


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
