#!/usr/bin/env python3
"""
Android Media Backup - CLI Entry Point
"""

import argparse
import sys

from cli.app import run_cli


def main():
    parser = argparse.ArgumentParser(
        description="Android Media Backup - Backup incrementale dei media via ADB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi:
  %(prog)s                          # Modalità interattiva
  %(prog)s -d ~/backup              # Specifica destinazione
  %(prog)s -d ~/backup -f DCIM      # Backup solo di DCIM
  %(prog)s -d ~/backup -f DCIM Pictures  # Backup di più cartelle
        """
    )
    
    parser.add_argument(
        '-d', '--destination',
        type=str,
        help='Cartella di destinazione per il backup'
    )
    
    parser.add_argument(
        '-f', '--folders',
        nargs='+',
        type=str,
        help='Nomi delle cartelle da sincronizzare (es: DCIM Pictures)'
    )
    
    parser.add_argument(
        '-a', '--all',
        action='store_true',
        dest='select_all',
        help='Seleziona automaticamente tutte le cartelle'
    )
    
    parser.add_argument(
        '-v', '--version',
        action='version',
        version='%(prog)s 1.0.0'
    )
    
    args = parser.parse_args()
    
    try:
        run_cli(
            destination=args.destination,
            selected_folders=args.folders,
            select_all=args.select_all
        )
    except KeyboardInterrupt:
        print("\n\nInterrotto dall'utente.")
        sys.exit(130)


if __name__ == '__main__':
    main()
