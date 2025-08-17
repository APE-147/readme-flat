#!/bin/bash

# 保险模板
source ~/.env_common
slug=$(slugify "$(basename "$PWD")")
PROJECT_DIR=$(get_project_data "$slug")

# 项目配置
PROJECT_NAME="readme_sync"
SCRIPT_DIR="$HOME/Code/Scripts/desktop/readme-flat"
PYTHON_BIN="$HOME/Developer/Python/miniconda/envs/System/bin/python"

# 确保项目数据目录存在
mkdir -p "$PROJECT_DIR"
mkdir -p "$PROJECT_DIR/logs"

# 创建用户配置文件
cat > "$PROJECT_DIR/scan_folders.json" << 'EOF'
{
  "source_folders": [
    "/Users/niceday/Developer/Cloud/Dropbox/-WorkSpace-/Code/Area/Project/Application",
    "/Users/niceday/Developer/Code/Scripts"
  ],
  "target_folder": "/Users/niceday/Developer/Code/Temp/[readme]",
  "file_patterns": [
    "README.md",
    "readme.md",
    "README.txt",
    "readme.txt"
  ],
  "exclude_patterns": [
    "*.git*",
    "node_modules",
    "__pycache__",
    "*.pyc",
    ".venv",
    "venv"
  ]
}
EOF

# 停止现有服务
launchctl unload "$HOME/Library/LaunchAgents/com.readme-sync.plist" 2>/dev/null || true

# 创建 LaunchAgent plist
cat > "$HOME/Library/LaunchAgents/com.readme-sync.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.readme-sync</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_BIN</string>
        <string>$SCRIPT_DIR/src/readme_sync/main.py</string>
        <string>daemon</string>
        <string>start</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$PROJECT_DIR/logs/launchd.out</string>
    <key>StandardErrorPath</key>
    <string>$PROJECT_DIR/logs/launchd.err</string>
    <key>WorkingDirectory</key>
    <string>$SCRIPT_DIR</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
        <key>PROJECT_DATA_DIR</key>
        <string>$PROJECT_DIR</string>
    </dict>
</dict>
</plist>
EOF

# 加载服务
launchctl load "$HOME/Library/LaunchAgents/com.readme-sync.plist"

echo "✅ readme_sync 部署完成"
echo "📁 数据目录: $PROJECT_DIR"
echo "⚙️ 配置文件: $PROJECT_DIR/scan_folders.json"
echo "📋 日志目录: $PROJECT_DIR/logs"