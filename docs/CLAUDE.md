# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is README Sync Manager (readme-flat), a Python tool for centralized management and synchronization of README files across multiple projects. It provides bidirectional sync between source projects and a target directory (e.g., for Obsidian knowledge management).

## Architecture

The application follows a modular architecture:

- **Core Layer**: `sync_engine.py` (main sync logic), `scanner.py` (file discovery)
- **Services Layer**: `config.py` (configuration), `database.py` (SQLite persistence), `daemon.py` (background process), `watcher.py` (real-time monitoring), `autostart.py` (platform-specific startup)
- **CLI Layer**: `cli.py` (Typer-based commands), `main.py` (entry point for daemon)
- **Data Flow**: Source dirs → Scanner → Sync Engine → Database mapping → Target dir

The system uses SQLite for mapping relationships and supports intelligent conflict resolution with MD5 hash-based change detection.

## Development Commands

### Installation & Setup
```bash
# Install dependencies
pip install -e .

# Initialize configuration (creates config in PROJECT_DATA_DIR or ~/Developer/Code/Data/srv/readme_flat)
readme-sync init
```

### Testing & Validation
```bash
# Run linting
black --check src/
isort --check-only src/
flake8 src/

# Run type checking
mypy src/

# Format code
black src/
isort src/

# Run tests (if available)
pytest tests/ -v --cov=readme_sync
```

### Core Commands
```bash
# Manual sync
readme-sync sync

# Start/stop daemon
readme-sync daemon start
readme-sync daemon stop
readme-sync daemon status

# Configuration management
readme-sync config list
readme-sync config set sync_settings.cleanup_interval 3600

# File management
readme-sync scan                    # Show all discovered README files
readme-sync cleanup                 # Remove orphaned mappings
readme-sync list-unlinked          # Show untracked files in target
readme-sync move-unlinked          # Move untracked files to subfolder
```

## Configuration & Data Management

- **Configuration**: YAML files in `$PROJECT_DATA_DIR` (environment variable) or `~/Developer/Code/Data/srv/readme_flat/`
- **Main config**: `config.yaml` (sync settings, naming rules, exclusions)
- **Scan config**: `scan_folders.json` (source/target paths, patterns)
- **Database**: SQLite files for file mappings and sync metadata
- **Deployment**: `deploy.sh` creates LaunchAgent for macOS auto-startup

## Key Implementation Details

### Sync Engine Strategy
- Uses MD5 hashing for change detection
- Implements intelligent conflict resolution (latest, manual, source/target priority)
- Supports tolerance windows to prevent sync loops
- Provides bidirectional sync with safety confirmations

### Database Schema
- File mappings: source_path ↔ target_path relationships
- Tracks modification times, hashes, and sync timestamps
- Automatic cleanup of orphaned mappings and out-of-scope entries

### Daemon Operations
- Real-time file monitoring with watchdog
- Periodic cleanup tasks (configurable interval, default 1 hour)
- Background processing with PID management and logging
- Platform-specific autostart (LaunchAgent on macOS)

## Dependencies

Runtime: `typer[all]`, `pyyaml`, `watchdog`, `psutil`, `rich`
Development: `pytest`, `pytest-cov`, `black`, `isort`, `flake8`, `mypy`

## File Patterns & Exclusions

Default scan patterns: `README.md`, `readme.md`, `README.txt`, `readme.txt`
Default exclusions: `node_modules`, `.git`, `venv`, `__pycache__`, `.DS_Store`, `*.tmp`, `*.log`

## Conflict Resolution

The system detects file conflicts and offers multiple resolution strategies:
- `latest`: Use most recently modified file
- `manual`: Create conflict copies for user review
- `source_priority`: Always prefer source file
- `target_priority`: Always prefer target file