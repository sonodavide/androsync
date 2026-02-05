"""
CLI Application Module
Interactive command-line interface for Android Media Backup.
"""

import sys
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich.prompt import Prompt, Confirm
from rich import print as rprint

from core.adb import check_adb_available, get_connected_devices, get_single_device, ADBError
from core.scanner import scan_media_folders, MediaFolder, ScanResult
from core.backup import BackupManager, BackupProgress, BackupStatus


console = Console()


def format_size(size_bytes: int) -> str:
    """Format bytes to human readable string."""
    if size_bytes >= 1024 ** 3:
        return f"{size_bytes / (1024**3):.2f} GB"
    elif size_bytes >= 1024 ** 2:
        return f"{size_bytes / (1024**2):.2f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.2f} KB"
    return f"{size_bytes} B"


def check_prerequisites() -> bool:
    """Check if ADB is available and a device is connected."""
    # Check ADB
    if not check_adb_available():
        console.print("[bold red]ERRORE:[/] ADB non trovato. Installa Android SDK Platform Tools.", style="red")
        return False
    
    console.print("[green][OK][/] ADB disponibile")
    
    # Check device
    try:
        devices = get_connected_devices()
        authorized = [d for d in devices if d.status == "device"]
        
        if len(authorized) == 0:
            console.print("[bold red]ERRORE:[/] Nessun dispositivo Android connesso.", style="red")
            console.print("  Assicurati che:")
            console.print("  - Il dispositivo sia collegato via USB")
            console.print("  - Il debug USB sia attivo")
            console.print("  - Hai autorizzato il computer sul dispositivo")
            return False
        
        if len(authorized) > 1:
            console.print("[bold yellow]ATTENZIONE:[/] Piu dispositivi connessi. Usa solo un dispositivo.", style="yellow")
            return False
        
        device = authorized[0]
        console.print(f"[green][OK][/] Dispositivo connesso: [bold cyan]{device.model}[/] ({device.serial})")
        return True
        
    except ADBError as e:
        console.print(f"[bold red]ERRORE ADB:[/] {e}", style="red")
        return False


def scan_device() -> Optional[ScanResult]:
    """Scan device for media folders."""
    console.print("\n[bold]Scansione dispositivo...[/]")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("Scansione cartelle media...", total=None)
        
        def on_progress(path: str, index: int, total: int):
            progress.update(task, description=f"Scansione: {path}")
        
        try:
            result = scan_media_folders(progress_callback=on_progress)
            return result
        except ADBError as e:
            console.print(f"[bold red]ERRORE durante la scansione:[/] {e}", style="red")
            return None


def display_scan_results(result: ScanResult):
    """Display scan results in a nice table."""
    console.print("\n")
    
    # Summary panel
    summary = f"""[bold cyan]Foto:[/] {result.total_photos:,}
[bold cyan]Video:[/] {result.total_videos:,}
[bold cyan]Totale:[/] {result.total_media:,} file ({result.size_human()})"""
    
    console.print(Panel(summary, title="[bold]Riepilogo Media[/]", border_style="cyan"))
    
    # Folders table
    if result.folders:
        table = Table(title="Cartelle Trovate", show_header=True, header_style="bold magenta")
        table.add_column("#", style="dim", width=4)
        table.add_column("Cartella", style="cyan")
        table.add_column("Foto", justify="right")
        table.add_column("Video", justify="right")
        table.add_column("Totale", justify="right", style="bold")
        table.add_column("Dimensione", justify="right", style="green")
        
        for i, folder in enumerate(result.folders, 1):
            table.add_row(
                str(i),
                folder.name,
                str(folder.photo_count),
                str(folder.video_count),
                str(folder.total_count),
                folder.size_human()
            )
        
        console.print(table)
    else:
        console.print("[yellow]Nessuna cartella con media trovata.[/]")


def select_folders(folders: list[MediaFolder]) -> list[MediaFolder]:
    """Interactive folder selection."""
    console.print("\n[bold]Seleziona le cartelle da sincronizzare[/]")
    console.print("Inserisci i numeri separati da virgola (es: 1,2,3) o 'all' per tutte:")
    
    while True:
        choice = Prompt.ask("[bold cyan]Selezione[/]", default="all")
        
        if choice.lower() == 'all':
            return folders
        
        try:
            indices = [int(x.strip()) for x in choice.split(',')]
            selected = []
            
            for idx in indices:
                if 1 <= idx <= len(folders):
                    selected.append(folders[idx - 1])
                else:
                    console.print(f"[yellow]Indice {idx} non valido, ignorato.[/]")
            
            if selected:
                console.print(f"\n[green][OK][/] Selezionate {len(selected)} cartelle")
                return selected
            else:
                console.print("[red]Nessuna cartella valida selezionata.[/]")
                
        except ValueError:
            console.print("[red]Input non valido. Usa numeri separati da virgola.[/]")


def get_destination() -> Optional[str]:
    """Get backup destination from user."""
    console.print("\n[bold]Destinazione Backup[/]")
    
    destination = Prompt.ask(
        "[bold cyan]Cartella di destinazione[/]",
        default="./backup"
    )
    
    # Expand user path
    destination = destination.replace("~", str(__import__('pathlib').Path.home()))
    
    return destination


def run_backup(folders: list[MediaFolder], destination: str):
    """Run the backup process with progress display."""
    console.print(f"\n[bold]Avvio backup verso:[/] {destination}")
    
    manager = BackupManager(destination)
    
    # Analyze first
    console.print("\n[bold]Analisi file...[/]")
    to_sync, already_synced = manager.analyze_folders(folders)
    
    # Show sync status
    sync_size = sum(f.size for f in already_synced)
    new_size = sum(f.size for f in to_sync)
    
    status_panel = f"""[bold green]Gia sincronizzati:[/] {len(already_synced):,} file ({format_size(sync_size)})
[bold yellow]Da scaricare:[/] {len(to_sync):,} file ({format_size(new_size)})"""
    
    console.print(Panel(status_panel, title="[bold]Stato Sincronizzazione[/]", border_style="blue"))
    
    if not to_sync:
        console.print("\n[bold green]Tutto sincronizzato! Nessun nuovo file da scaricare.[/]")
        return
    
    if not Confirm.ask("\n[bold]Procedere con il backup?[/]", default=True):
        console.print("[yellow]Backup annullato.[/]")
        return
    
    console.print("\n[bold]Download in corso...[/]")
    console.print("[dim]Premi Ctrl+C per interrompere (potrai riprendere dopo)[/]\n")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console
    ) as progress:
        task = progress.add_task(
            "Backup in corso...",
            total=len(to_sync)
        )
        
        def on_progress(bp: BackupProgress):
            completed = bp.completed_files
            progress.update(
                task,
                completed=completed,
                description=f"[cyan]{bp.current_file}[/]" if bp.current_file else "Completato"
            )
        
        try:
            result = manager.start_backup(folders, progress_callback=on_progress)
            
            # Show results
            console.print("\n")
            if result.status == BackupStatus.COMPLETED:
                result_panel = f"""[bold green]Completati:[/] {result.completed_files:,} file
[bold blue]Gia presenti:[/] {result.skipped_files:,} file
[bold red]Falliti:[/] {result.failed_files:,} file"""
                console.print(Panel(result_panel, title="[bold green]Backup Completato![/]", border_style="green"))
            elif result.status == BackupStatus.CANCELLED:
                console.print("[bold yellow]Backup interrotto. Potrai riprendere al prossimo avvio.[/]")
                
        except KeyboardInterrupt:
            manager.cancel()
            console.print("\n[bold yellow]Backup interrotto dall'utente.[/]")
            console.print("[dim]I progressi sono stati salvati. Riavvia per riprendere.[/]")


def run_cli(destination: Optional[str] = None, selected_folders: Optional[list[str]] = None):
    """
    Main CLI entry point.
    
    Args:
        destination: Optional preset destination path.
        selected_folders: Optional list of folder names to backup.
    """
    console.print(Panel.fit(
        "[bold cyan]Android Media Backup[/]\n[dim]Backup incrementale dei media via ADB[/]",
        border_style="cyan"
    ))
    
    # Check prerequisites
    if not check_prerequisites():
        sys.exit(1)
    
    # Scan device
    result = scan_device()
    if not result:
        sys.exit(1)
    
    if not result.folders:
        console.print("[yellow]Nessun media trovato sul dispositivo.[/]")
        sys.exit(0)
    
    # Display results
    display_scan_results(result)
    
    # Select folders
    if selected_folders:
        # Filter by name if provided
        folders = [f for f in result.folders if f.name in selected_folders]
        if not folders:
            console.print("[red]Nessuna delle cartelle specificate trovata.[/]")
            folders = select_folders(result.folders)
    else:
        folders = select_folders(result.folders)
    
    if not folders:
        console.print("[yellow]Nessuna cartella selezionata. Uscita.[/]")
        sys.exit(0)
    
    # Get destination
    if not destination:
        destination = get_destination()
    
    if not destination:
        sys.exit(1)
    
    # Run backup
    run_backup(folders, destination)
    
    console.print("\n[bold]Fine.[/]")
