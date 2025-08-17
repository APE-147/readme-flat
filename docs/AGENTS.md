# Repository Guidelines

## 项目路径指定
- 项目配置数据地址: "/Users/niceday/Developer/Cloud/Dropbox/-Code-/Data/srv/readme_flat"
- 保存相关配置的文件: "/Users/niceday/Developer/Cloud/Dropbox/-Code-/Data/srv/readme_flat/config.yaml"
  - 始终使用这个文件, 去除关于scan_folders.json的无效逻辑
- 需要搜索的地址(源地址): "/Users/niceday/Developer/Cloud/Dropbox/-Code-/Scripts"
- 将文件复制的地址(目标地址): "/Users/niceday/Developer/Cloud/Dropbox/-Code-/Data/file/APP/Obsidian/Remote-temp/[readme]"
- 在调试的时候停止项目, 停止的时候需要停止所有相关的文件存储路径设置, 不得有残留, 确保所有路径相关的设置放在 "/Users/niceday/Developer/Cloud/Dropbox/-Code-/Data/srv/readme_flat/config.yaml" 这个配置文件中

## Project Structure & Module Organization
- `src/readme_sync/`: Main package. Key modules: `core/` (sync engine), `services/` (config, daemon, database, watcher), `utils/`, `plugins/`, `cli.py` (Typer app), `main.py`.
- `tests/`: Pytest test suite (patterns configured in `pyproject.toml`).
- `scripts/`: Environment/setup helpers (`install.sh`, `setup_env.sh`, `macos/`).
- Root docs: `README.md`, `README_deployment.md`, `CHANGELOG.md`.

## Build, Test, and Development Commands
- Install (dev): `pip install -e .[dev]`
- Run CLI: `readme-sync --help`
- Format: `black src tests && isort src tests`
- Lint: `flake8 src tests`
- Type check: `mypy src`
- Test: `pytest -v` or `pytest -v --cov=readme_sync`
- Deploy (macOS LaunchAgent, data dir, etc.): `./deploy.sh`

## Coding Style & Naming Conventions
- Indentation: 4 spaces; max line length 88 (Black).
- Imports: `isort` with Black profile; keep first-party as `readme_sync`.
- Naming: modules and packages `snake_case`; classes `PascalCase`; functions/variables `snake_case`; constants `UPPER_SNAKE_CASE`.
- Tools: Black, isort, Flake8, MyPy configured in `pyproject.toml`.

## Testing Guidelines
- Framework: Pytest with coverage (`--cov=readme_sync --cov-report=term-missing`).
- Locations/patterns: `tests/` with `test_*.py` or `*_test.py`; classes `Test*`; functions `test_*`.
- Write focused, deterministic tests around `core/` and `services/` behaviors; prefer CLI tests via Typer’s `CliRunner` where applicable.

## Commit & Pull Request Guidelines
- Commit messages: concise, present tense. Prefer Conventional Commits (e.g., `feat:`, `fix:`, `chore:`) to support changelog and SemVer.
- PRs: include summary, rationale, screenshots or terminal output for CLI UX changes, and linked issues.
- Keep changes atomic; add/adjust tests and docs when behavior changes.

## Security & Configuration Tips
- Data directory: defaults to `~/Developer/Code/Data/srv/readme_sync/` (see `README_deployment.md`). Ensure proper permissions.
- Environment: `PROJECT_DATA_DIR` can override the data path; validate before running long-lived services.
- Services: use `readme-sync autostart`/`daemon` commands or `deploy.sh` to manage background processes; check logs under the data directory.
