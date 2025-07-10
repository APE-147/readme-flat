# README Sync Manager

A tool for centralizing and synchronizing README.md files from multiple projects.

## Features

- Multi-source scanning: Recursively search for README.md files in multiple folders
- Smart renaming: Automatically rename files to `{project_name}-README` format
- Bidirectional sync: Support sync from source to target and vice versa
- Dynamic mapping: Target files can be moved to subfolders while maintaining sync relationship
- State persistence: SQLite database stores file mapping relationships
- Command-line interface: Rich CLI commands for configuration and operation

## Installation

```bash
pip install readme-sync-manager
```

## Quick Start

```bash
# Initialize configuration
readme-sync init

# Add source folders
readme-sync add-source ~/Developer/Projects

# Set target folder
readme-sync set-target ~/Documents/README-Collection

# Manual sync
readme-sync sync

# Watch mode
readme-sync watch
```

## Commands

- `init`: Initialize configuration file
- `add-source <path>`: Add source folder
- `set-target <path>`: Set target folder
- `sync`: Execute manual sync
- `watch`: Start file monitoring mode
- `status`: View sync status
- `config`: Configuration management

## Configuration

Configuration file location: `~/.readme-sync/config.yaml`

```yaml
source_folders:
  - path: "~/Developer/Projects"
    enabled: true

target_folder: "~/Documents/README-Collection"

sync_settings:
  conflict_resolution: "latest"
  tolerance_seconds: 5
```
