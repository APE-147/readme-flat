# -*- coding: utf-8 -*-
"""配置管理模块"""

import os
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional


class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_path: str = None):
        """初始化配置管理器"""
        if config_path is None:
            self.config_dir = Path.home() / ".readme-sync"
            self.config_path = self.config_dir / "config.yaml"
        else:
            self.config_path = Path(config_path)
            self.config_dir = self.config_path.parent
        
        self.config_dir.mkdir(exist_ok=True)
        self.config = self.load_config()
    
    def get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "version": "1.0",
            "source_folders": [],
            "target_folder": "",
            "sync_settings": {
                "conflict_resolution": "latest",  # latest, manual, source_priority, target_priority
                "tolerance_seconds": 5,           # 时间容忍度
                "auto_sync_interval": 300,        # 自动同步间隔(秒)
            },
            "naming_rules": {
                "pattern": "{project_name}-README",  # 命名模式
                "case_style": "keep",               # keep, lower, upper
            },
            "exclusions": [
                "node_modules",
                ".git",
                "venv",
                "__pycache__",
                ".DS_Store",
                "*.tmp",
                "*.log"
            ]
        }
    
    def load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        if not self.config_path.exists():
            # 配置文件不存在，创建默认配置
            default_config = self.get_default_config()
            self.save_config(default_config)
            return default_config
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                # 合并默认配置以确保所有必需的键都存在
                default_config = self.get_default_config()
                return self._merge_config(default_config, config)
        except Exception as e:
            print(f"加载配置文件失败: {e}")
            return self.get_default_config()
    
    def _merge_config(self, default: Dict, user: Dict) -> Dict:
        """合并配置（用户配置会覆盖默认配置，但会保留必需的键）"""
        if not isinstance(user, dict):
            return default
        
        result = default.copy()
        for key, value in user.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_config(result[key], value)
            else:
                result[key] = value
        
        return result
    
    def save_config(self, config: Dict[str, Any] = None) -> bool:
        """保存配置文件"""
        try:
            config_to_save = config if config is not None else self.config
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config_to_save, f, default_flow_style=False, 
                         allow_unicode=True, indent=2)
            return True
        except Exception as e:
            print(f"保存配置文件失败: {e}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项（支持点号分隔的嵌套键）"""
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any) -> bool:
        """设置配置项（支持点号分隔的嵌套键）"""
        keys = key.split('.')
        current = self.config
        
        # 创建中间层级
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        
        # 设置最终值
        current[keys[-1]] = value
        return self.save_config()
    
    def add_source_folder(self, folder_path: str, enabled: bool = True) -> bool:
        """添加源文件夹"""
        folder_path = os.path.expanduser(folder_path)
        
        if not os.path.exists(folder_path):
            print(f"文件夹不存在: {folder_path}")
            return False
        
        source_folders = self.get("source_folders", [])
        
        # 检查是否已存在
        for folder in source_folders:
            if folder.get("path") == folder_path:
                folder["enabled"] = enabled
                return self.save_config()
        
        # 添加新文件夹
        source_folders.append({
            "path": folder_path,
            "enabled": enabled
        })
        
        return self.set("source_folders", source_folders)
    
    def remove_source_folder(self, folder_path: str) -> bool:
        """移除源文件夹"""
        folder_path = os.path.expanduser(folder_path)
        source_folders = self.get("source_folders", [])
        
        # 过滤掉指定文件夹
        new_folders = [f for f in source_folders if f.get("path") != folder_path]
        
        if len(new_folders) != len(source_folders):
            return self.set("source_folders", new_folders)
        
        return False
    
    def get_enabled_source_folders(self) -> List[str]:
        """获取启用的源文件夹列表"""
        source_folders = self.get("source_folders", [])
        return [
            os.path.expanduser(folder["path"]) 
            for folder in source_folders 
            if folder.get("enabled", True)
        ]
    
    def set_target_folder(self, folder_path: str) -> bool:
        """设置目标文件夹"""
        folder_path = os.path.expanduser(folder_path)
        
        # 创建目录如果不存在
        try:
            os.makedirs(folder_path, exist_ok=True)
        except Exception as e:
            print(f"创建目录失败: {e}")
            return False
        
        return self.set("target_folder", folder_path)
    
    def get_target_folder(self) -> str:
        """获取目标文件夹"""
        target = self.get("target_folder", "")
        return os.path.expanduser(target) if target else ""
    
    def is_excluded(self, path: str) -> bool:
        """检查路径是否被排除"""
        exclusions = self.get("exclusions", [])
        path_parts = Path(path).parts
        
        for exclusion in exclusions:
            # 检查目录或文件名是否匹配排除规则
            if any(part == exclusion or 
                   (exclusion.startswith('*') and part.endswith(exclusion[1:])) or
                   (exclusion.endswith('*') and part.startswith(exclusion[:-1]))
                   for part in path_parts):
                return True
        
        return False
    
    def get_naming_pattern(self) -> str:
        """获取命名模式"""
        return self.get("naming_rules.pattern", "{project_name}-README")
    
    def get_tolerance_seconds(self) -> int:
        """获取时间容忍度（秒）"""
        return self.get("sync_settings.tolerance_seconds", 5)
    
    def get_conflict_resolution(self) -> str:
        """获取冲突解决策略"""
        return self.get("sync_settings.conflict_resolution", "latest")
    
    def get_auto_sync_interval(self) -> int:
        """获取自动同步间隔"""
        return self.get("sync_settings.auto_sync_interval", 300)
    
    def validate_config(self) -> List[str]:
        """验证配置有效性，返回错误列表"""
        errors = []
        
        # 检查目标文件夹
        target_folder = self.get_target_folder()
        if not target_folder:
            errors.append("未设置目标文件夹")
        elif not os.path.exists(target_folder):
            errors.append(f"目标文件夹不存在: {target_folder}")
        
        # 检查源文件夹
        source_folders = self.get_enabled_source_folders()
        if not source_folders:
            errors.append("未设置有效的源文件夹")
        else:
            for folder in source_folders:
                if not os.path.exists(folder):
                    errors.append(f"源文件夹不存在: {folder}")
        
        # 检查冲突解决策略
        valid_resolutions = ["latest", "manual", "source_priority", "target_priority"]
        resolution = self.get_conflict_resolution()
        if resolution not in valid_resolutions:
            errors.append(f"无效的冲突解决策略: {resolution}")
        
        return errors
    
    def print_config(self):
        """打印当前配置"""
        print("当前配置:")
        print(yaml.dump(self.config, default_flow_style=False, allow_unicode=True, indent=2))