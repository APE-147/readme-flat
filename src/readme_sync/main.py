#!/usr/bin/env python3
"""
README Sync Main Entry Point
"""

import sys
import os
import argparse
import logging
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from readme_sync.cli import app
from readme_sync.services.daemon import DaemonManager

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='README Sync Tool')
    parser.add_argument('command', choices=['daemon', 'sync', 'status'], 
                       help='Command to run')
    parser.add_argument('action', nargs='?', choices=['start', 'stop', 'restart', 'status'],
                       help='Action for daemon command')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    if args.command == 'daemon':
        if args.action == 'start':
            daemon = DaemonManager()
            daemon.start()
        elif args.action == 'stop':
            daemon = DaemonManager()
            daemon.stop()
        elif args.action == 'restart':
            daemon = DaemonManager()
            daemon.restart()
        elif args.action == 'status':
            daemon = DaemonManager()
            status = daemon.status()
            print(f"Daemon status: {'Running' if status['running'] else 'Stopped'}")
            if status['running']:
                print(f"PID: {status['pid']}")
                print(f"Memory: {status['memory_usage']} bytes")
        else:
            print("Daemon command requires an action: start, stop, restart, or status")
            sys.exit(1)
    elif args.command == 'sync':
        # Run one-time sync
        from readme_sync.core.sync_engine import SyncEngine
        from readme_sync.services.config import ConfigManager
        from readme_sync.services.database import DatabaseManager
        
        config_manager = ConfigManager()
        db_manager = DatabaseManager()
        sync_engine = SyncEngine(config_manager, db_manager)
        results = sync_engine.sync_all()
        print(f"同步完成：扫描 {results['scanned']} 个文件，同步 {results['synced']} 个文件，反向同步 {results['reverse_synced']} 个文件")
    elif args.command == 'status':
        # Show sync status
        from readme_sync.services.database import DatabaseManager
        db = DatabaseManager()
        db.show_status()
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == '__main__':
    main()