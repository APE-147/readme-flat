# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Restructured project according to Python CLI framework standards
- Migrated from Click to Typer CLI framework with Rich styling
- Enhanced command-line interface with colorized output and progress bars
- Added comprehensive installation script with cross-platform support
- Introduced modular architecture with core/, services/, utils/, plugins/ structure
- Added pyproject.toml for modern Python packaging
- Created automated installation scripts for macOS, Linux, and Windows
- Enhanced configuration management with standardized data directory

### Changed
- **BREAKING**: Migrated CLI framework from Click to Typer
- **BREAKING**: Changed data directory from `~/.readme-sync/` to `~/Developer/Code/Script_data/readme-sync/`
- Reorganized source code structure according to framework guidelines
- Updated entry point from `readme_sync.cli:cli` to `readme_sync.cli:app`
- Enhanced autostart command for simplified daemon management
- Improved error handling and user feedback with Rich console output

### Fixed
- Standardized import paths for restructured modules
- Updated configuration and database initialization for new data directory structure
- Corrected daemon file paths to use unified data directory

### Technical Debt
- Replaced setup.py with modern pyproject.toml configuration
- Separated concerns between core logic, services, and utilities
- Improved code organization and maintainability

## [0.1.0] - 2025-07-11

### Added
- Initial release of README Sync Manager
- Bidirectional synchronization between source projects and centralized location
- Intelligent project detection and README file scanning
- Real-time file monitoring with configurable sync intervals
- Anti-loop protection mechanisms
- SQLite database for mapping and metadata persistence
- Background daemon process with system service integration
- Comprehensive CLI with configuration management
- Conflict resolution strategies
- Smart sync capabilities for user edit protection
- Obsidian vault integration support

### Features
- **Core Sync Engine**: Bidirectional sync with timestamp-based conflict resolution
- **File Scanner**: Intelligent project name extraction and README detection
- **Real-time Watcher**: File system monitoring with debounce protection
- **Daemon Manager**: Background service with process management
- **Configuration System**: YAML-based configuration with validation
- **Database Layer**: SQLite persistence for file mappings and state
- **Autostart Integration**: System service installation for automatic startup

### Supported Platforms
- macOS (with launchd integration)
- Linux (systemd support planned)
- Windows/WSL (basic support)

### Dependencies
- Python 3.8+
- click>=8.0.0
- pyyaml>=6.0
- watchdog>=3.0.0
- psutil>=5.8.0