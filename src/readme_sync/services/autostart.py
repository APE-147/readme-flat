# -*- coding: utf-8 -*-
"""开机自启动配置模块"""

import os
import sys
import shutil
import subprocess
from pathlib import Path
from typing import Optional
from .config import ConfigManager


class AutoStartManager:
    """开机自启动管理器"""
    
    def __init__(self):
        """初始化自启动管理器"""
        self.home_dir = Path.home()
        self.launch_agents_dir = self.home_dir / "Library" / "LaunchAgents"
        self.launch_agents_dir.mkdir(parents=True, exist_ok=True)
        
        # plist文件路径
        self.plist_file = self.launch_agents_dir / "com.readme-sync.daemon.plist"
        
        # 获取当前Python可执行文件路径
        self.python_path = sys.executable
        
        # 获取readme-sync命令路径
        self.readme_sync_path = self._get_readme_sync_path()
    
    def _get_readme_sync_path(self) -> Optional[str]:
        """获取readme-sync命令路径"""
        try:
            # 尝试通过which命令查找
            result = subprocess.run(['which', 'readme-sync'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
            
            # 如果没找到，尝试常见的安装路径
            possible_paths = [
                f"{sys.prefix}/bin/readme-sync",
                f"{self.home_dir}/.local/bin/readme-sync",
                "/usr/local/bin/readme-sync"
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    return path
            
            return None
            
        except Exception as e:
            print(f"获取readme-sync路径失败: {e}")
            return None
    
    def _get_data_dir(self) -> str:
        """获取数据目录路径（从配置目录推断）"""
        cfg = ConfigManager()
        return cfg.get_config_dir()
    
    def create_plist(self) -> bool:
        """创建launchd plist文件"""
        if not self.readme_sync_path:
            print("未找到readme-sync命令，请先安装软件包")
            return False
        
        # 创建plist内容
        plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.readme-sync.daemon</string>
    
    <key>ProgramArguments</key>
    <array>
        <string>{self.readme_sync_path}</string>
        <string>daemon</string>
        <string>start</string>
    </array>
    
    <key>RunAtLoad</key>
    <true/>
    
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    
    <key>StandardOutPath</key>
    <string>{self._get_data_dir()}/launchd.out</string>
    
    <key>StandardErrorPath</key>
    <string>{self._get_data_dir()}/launchd.err</string>
    
    <key>WorkingDirectory</key>
    <string>{self.home_dir}</string>
    
    <key>ProcessType</key>
    <string>Background</string>
    
    <key>Nice</key>
    <integer>1</integer>
    
    <key>LowPriorityIO</key>
    <true/>
    
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:{os.path.dirname(self.readme_sync_path)}</string>
    </dict>
</dict>
</plist>"""
        
        try:
            # 写入plist文件
            with open(self.plist_file, 'w') as f:
                f.write(plist_content)
            
            print(f"已创建launchd plist文件: {self.plist_file}")
            return True
            
        except Exception as e:
            print(f"创建plist文件失败: {e}")
            return False
    
    def install_autostart(self) -> bool:
        """安装开机自启动"""
        # 创建plist文件
        if not self.create_plist():
            return False
        
        try:
            # 加载launchd服务
            result = subprocess.run([
                'launchctl', 'load', str(self.plist_file)
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                print("开机自启动已安装")
                return True
            else:
                print(f"安装开机自启动失败: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"安装开机自启动失败: {e}")
            return False
    
    def uninstall_autostart(self) -> bool:
        """卸载开机自启动"""
        try:
            # 卸载launchd服务
            if self.plist_file.exists():
                result = subprocess.run([
                    'launchctl', 'unload', str(self.plist_file)
                ], capture_output=True, text=True)
                
                # 删除plist文件
                self.plist_file.unlink()
                
                if result.returncode == 0:
                    print("开机自启动已卸载")
                    return True
                else:
                    print(f"卸载开机自启动失败: {result.stderr}")
                    return False
            else:
                print("开机自启动未安装")
                return True
                
        except Exception as e:
            print(f"卸载开机自启动失败: {e}")
            return False
    
    def is_installed(self) -> bool:
        """检查是否已安装开机自启动"""
        return self.plist_file.exists()
    
    def get_status(self) -> dict:
        """获取自启动状态"""
        if not self.is_installed():
            return {
                'installed': False,
                'loaded': False,
                'running': False
            }
        
        try:
            # 检查服务是否已加载
            result = subprocess.run([
                'launchctl', 'list', 'com.readme-sync.daemon'
            ], capture_output=True, text=True)
            
            loaded = result.returncode == 0
            running = False
            
            if loaded:
                # 解析输出获取运行状态
                lines = result.stdout.strip().split('\\n')
                for line in lines:
                    if 'PID' in line:
                        parts = line.split()
                        if len(parts) >= 1 and parts[0] != '-':
                            running = True
                        break
            
            return {
                'installed': True,
                'loaded': loaded,
                'running': running,
                'plist_file': str(self.plist_file)
            }
            
        except Exception as e:
            print(f"获取自启动状态失败: {e}")
            return {
                'installed': True,
                'loaded': False,
                'running': False,
                'error': str(e)
            }
    
    def restart_service(self) -> bool:
        """重启launchd服务"""
        try:
            # 先卸载
            subprocess.run([
                'launchctl', 'unload', str(self.plist_file)
            ], capture_output=True)
            
            # 再加载
            result = subprocess.run([
                'launchctl', 'load', str(self.plist_file)
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                print("launchd服务已重启")
                return True
            else:
                print(f"重启launchd服务失败: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"重启launchd服务失败: {e}")
            return False


def create_system_service():
    """创建系统服务（用于Linux系统）"""
    service_content = """[Unit]
Description=README Sync Daemon
After=network.target

[Service]
Type=forking
User=%s
ExecStart=%s daemon start
ExecStop=%s daemon stop
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
""" % (os.getenv('USER'), shutil.which('readme-sync'), shutil.which('readme-sync'))
    
    service_file = Path('/etc/systemd/system/readme-sync.service')
    
    try:
        with open(service_file, 'w') as f:
            f.write(service_content)
        
        # 重载systemd配置
        subprocess.run(['sudo', 'systemctl', 'daemon-reload'])
        
        print("systemd服务文件已创建")
        print("使用以下命令启用开机自启动:")
        print("sudo systemctl enable readme-sync.service")
        print("sudo systemctl start readme-sync.service")
        
    except Exception as e:
        print(f"创建systemd服务失败: {e}")


def get_platform_manager():
    """根据平台返回对应的自启动管理器"""
    if sys.platform == 'darwin':
        return AutoStartManager()
    elif sys.platform.startswith('linux'):
        print("Linux系统请使用systemd服务")
        return None
    else:
        print(f"不支持的平台: {sys.platform}")
        return None
