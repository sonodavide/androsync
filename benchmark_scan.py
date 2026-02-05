#!/usr/bin/env python3
"""
Benchmark script to compare scanning methods.
Tests: find command (new) vs recursive ls (old)
"""

import time
import sys
sys.path.insert(0, '.')

from core.adb import shell_command, find_media_files, list_files, ADBError
from core.scanner import MEDIA_EXTENSIONS, SKIP_DIRECTORIES, get_storage_roots, is_media_file


def benchmark_find_method(storage_root: str) -> tuple[int, float]:
    """Benchmark the new find-based method."""
    start = time.time()
    
    files = find_media_files(
        storage_root=storage_root,
        extensions=MEDIA_EXTENSIONS,
        exclude_patterns=SKIP_DIRECTORIES
    )
    
    elapsed = time.time() - start
    return len(files), elapsed


def benchmark_ls_recursive(storage_root: str, max_depth: int = 6) -> tuple[int, float]:
    """Benchmark the old recursive ls method."""
    start = time.time()
    files_found = []
    dirs_scanned = 0
    
    def scan_dir(path: str, depth: int = 0):
        nonlocal dirs_scanned
        if depth > max_depth:
            return
        
        # Skip excluded directories
        for skip in SKIP_DIRECTORIES:
            if skip in path:
                return
        
        try:
            files = list_files(path)
            dirs_scanned += 1
            
            for f in files:
                if f['is_dir']:
                    scan_dir(f['path'], depth + 1)
                else:
                    is_media, _ = is_media_file(f['name'])
                    if is_media:
                        files_found.append(f)
        except ADBError:
            pass
    
    scan_dir(storage_root)
    
    elapsed = time.time() - start
    return len(files_found), elapsed, dirs_scanned


def main():
    print("=" * 60)
    print("BENCHMARK: Scansione Media Android")
    print("=" * 60)
    
    # Get storage roots
    print("\nRilevamento storage...")
    roots = get_storage_roots()
    
    for root, storage_type in roots.items():
        print(f"\n{'─' * 60}")
        print(f"Storage: {storage_type} ({root})")
        print(f"{'─' * 60}")
        
        # Benchmark find method
        print("\n[1] Metodo FIND (nuovo)...")
        find_count, find_time = benchmark_find_method(root)
        print(f"    File trovati: {find_count:,}")
        print(f"    Tempo: {find_time:.2f}s")
        
        # Benchmark ls recursive (limited depth to avoid timeout)
        print("\n[2] Metodo LS ricorsivo (vecchio, max 6 livelli)...")
        ls_count, ls_time, dirs_scanned = benchmark_ls_recursive(root, max_depth=6)
        print(f"    File trovati: {ls_count:,}")
        print(f"    Directory scansionate: {dirs_scanned:,}")
        print(f"    Tempo: {ls_time:.2f}s")
        
        # Comparison
        print("\n[RISULTATO]")
        if find_time > 0 and ls_time > 0:
            speedup = ls_time / find_time
            print(f"    Speedup: {speedup:.1f}x più veloce con find")
        
        if find_count != ls_count:
            print(f"    Nota: differenza file ({find_count} vs {ls_count}) dovuta a profondità limitata ls")
    
    print("\n" + "=" * 60)
    print("Benchmark completato!")
    print("=" * 60)


if __name__ == '__main__':
    main()
