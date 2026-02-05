#!/usr/bin/env python3
"""
Android Media Backup - TUI Entry Point
"""

import sys

from tui.app import AndroSyncTUI


def main():
    """Run the TUI application."""
    app = AndroSyncTUI()
    try:
        app.run()
    except KeyboardInterrupt:
        print("\n\nInterrotto dall'utente.")
        sys.exit(130)


if __name__ == '__main__':
    main()
