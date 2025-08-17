# -*- coding: utf-8 -*-
"""配置管理模块"""

import os
try:
    import yaml  # type: ignore
    _YAML_AVAILABLE = True
except Exception:
    yaml = None  # type: ignore
    _YAML_AVAILABLE = False
import json
from pathlib import Path
from typing import Dict, List, Any, Optional


class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_path: str = None, runtime_overrides: Optional[Dict[str, Any]] = None):
        """初始化配置管理器"""
        # 恢复从 config.yaml 读取路径设置；移除旧的 Developer/Code 默认值。
        # 优先级：--config 参数 > 环境变量 READMESYNC_CONFIG > 固定路径（Dropbox Cloud）
        env_config = os.getenv("READMESYNC_CONFIG")

        if config_path is None:
            if env_config:
                self.config_path = Path(env_config)
            else:
                # 默认集中配置路径（不再使用 ~/Developer/Code/...），但不会强制创建
                self.config_path = Path("/Users/niceday/Developer/Cloud/Dropbox/-Code-/Data/srv/readme_flat/config.yaml")
            self.config_dir = self.config_path.parent
        else:
            self.config_path = Path(config_path)
            self.config_dir = self.config_path.parent
        
        self._runtime_overrides = runtime_overrides or {}
        # 不自动创建目录与文件，除非调用方需要持久化
        self.scan_folders_file = self.config_dir / "scan_folders.json"
        self.config = self.load_config()
        # 迁移旧的 scan_folders.json 设置并删除残留
        self._migrate_scan_folders()
        # 应用运行时环境变量覆盖（不落盘），便于 n8n 等环境动态指定目录
        self._apply_env_overrides()
        # 应用调用方传入的运行时覆盖（最高优先级，不落盘）
        if self._runtime_overrides:
            self._apply_runtime_overrides(self._runtime_overrides)
    
    def get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "version": "1.0",
            "data_dir": str(self.config_dir),
            "source_folders": [],
            "target_folder": "",
            "sync_settings": {
                "conflict_resolution": "latest",  # latest, manual, source_priority, target_priority
                "tolerance_seconds": 5,           # 时间容忍度
                "auto_sync_interval": 1,          # 自动同步间隔(秒)
                "cleanup_interval": 3600,         # 清理间隔(秒) - 默认1小时
                "move_unlinked_files": True,      # 是否移动未链接文件
                "unlinked_subfolder": "unlinked", # 未链接文件子文件夹名称
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
            # 无配置文件：若提供了运行时覆盖，则使用覆盖构建临时配置；否则报错
            if self._runtime_overrides:
                base = self.get_default_config()
                # 将覆盖应用到内存配置副本
                merged = base.copy()
                try:
                    srcs = self._runtime_overrides.get("sources")
                    tgt = self._runtime_overrides.get("target")
                    if isinstance(srcs, list):
                        parts = [os.path.expanduser(str(p)) for p in srcs if str(p).strip()]
                        merged["source_folders"] = [{"path": p, "enabled": True} for p in parts]
                    if isinstance(tgt, str) and tgt.strip():
                        merged["target_folder"] = os.path.expanduser(tgt)
                except Exception:
                    pass
                return merged
            raise RuntimeError(f"配置文件不存在: {self.config_path}")
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                if _YAML_AVAILABLE:
                    config = yaml.safe_load(f)
                else:
                    import json as _json
                    config = _json.load(f)
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
                if _YAML_AVAILABLE:
                    yaml.dump(
                        config_to_save,
                        f,
                        default_flow_style=False,
                        allow_unicode=True,
                        indent=2,
                    )
                else:
                    import json as _json
                    _json.dump(config_to_save, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存配置文件失败: {e}")
            return False

    def _apply_env_overrides(self) -> None:
        """基于环境变量覆盖运行时配置（不写回文件）

        - READMESYNC_SOURCE_DIRS: 逗号分隔的源目录列表
        - READMESYNC_TARGET_DIR: 目标目录
        """
        sources_env = os.getenv("READMESYNC_SOURCE_DIRS")
        sources_json = os.getenv("READMESYNC_SOURCES_JSON")
        target_env = os.getenv("READMESYNC_TARGET_DIR")
        args_json = os.getenv("READMESYNC_ARGS_JSON")

        # Highest priority: READMESYNC_ARGS_JSON with {"sources": [...], "target": "..."}
        if args_json:
            try:
                import json as _json
                data = _json.loads(args_json)
                if isinstance(data, dict):
                    srcs = data.get("sources")
                    tgt = data.get("target")
                    if isinstance(srcs, list):
                        parts = [os.path.expanduser(str(p)) for p in srcs if str(p).strip()]
                        self.config["source_folders"] = [{"path": p, "enabled": True} for p in parts]
                    if isinstance(tgt, str) and tgt.strip():
                        self.config["target_folder"] = os.path.expanduser(tgt)
            except Exception:
                pass

        # Next: explicit JSON array for sources
        elif sources_json:
            try:
                import json as _json
                arr = _json.loads(sources_json)
                if isinstance(arr, list):
                    parts = [os.path.expanduser(str(p)) for p in arr if str(p).strip()]
                    self.config["source_folders"] = [{"path": p, "enabled": True} for p in parts]
            except Exception:
                pass

        # Finally: comma-separated list for sources
        elif sources_env:
            parts = [os.path.expanduser(p.strip()) for p in sources_env.split(',') if p.strip()]
            self.config["source_folders"] = [{"path": p, "enabled": True} for p in parts]

        # Target directory override
        if target_env:
            self.config["target_folder"] = os.path.expanduser(target_env)

    def _apply_runtime_overrides(self, overrides: Dict[str, Any]) -> None:
        """以最高优先级覆盖来源与目标（不写回文件）"""
        try:
            srcs = overrides.get("sources")
            tgt = overrides.get("target")
            if isinstance(srcs, list):
                parts = [os.path.expanduser(str(p)) for p in srcs if str(p).strip()]
                self.config["source_folders"] = [{"path": p, "enabled": True} for p in parts]
            if isinstance(tgt, str) and tgt.strip():
                self.config["target_folder"] = os.path.expanduser(tgt)
        except Exception:
            pass

    def get_config_dir(self) -> str:
        """返回配置目录绝对路径"""
        return str(self.config_dir)
    
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
    
    def _migrate_scan_folders(self):
        """一次性迁移 scan_folders.json 到 config.yaml 并删除残留文件"""
        if not self.scan_folders_file.exists():
            return
        try:
            with open(self.scan_folders_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            # 无法解析则直接删除
            try:
                self.scan_folders_file.unlink()
            except Exception:
                pass
            return

        # 迁移 source_folders -> config.source_folders (带 enabled 字段)
        migrated_sources = []
        for p in data.get("source_folders", []):
            migrated_sources.append({"path": os.path.expanduser(p), "enabled": True})
        if migrated_sources:
            self.config["source_folders"] = migrated_sources

        # 迁移 target_folder
        if data.get("target_folder"):
            self.config["target_folder"] = os.path.expanduser(data["target_folder"])

        # 迁移 exclude_patterns -> exclusions
        if data.get("exclude_patterns"):
            self.config["exclusions"] = data.get("exclude_patterns", [])

        self.save_config(self.config)
        # 删除旧文件避免残留
        try:
            self.scan_folders_file.unlink()
        except Exception:
            pass
    
    def get_source_folders(self) -> List[str]:
        """获取源文件夹列表（字符串路径）"""
        folders = self.get("source_folders", [])
        # 兼容纯字符串列表与 dict 列表
        normalized = []
        for item in folders:
            if isinstance(item, str):
                normalized.append(os.path.expanduser(item))
            elif isinstance(item, dict) and item.get("path"):
                normalized.append(os.path.expanduser(item["path"]))
        return normalized
    
    def get_target_folder(self) -> str:
        """获取目标文件夹（来自 config.yaml）"""
        target = self.get("target_folder", "")
        return os.path.expanduser(target) if target else ""
    
    def get_file_patterns(self) -> List[str]:
        """获取文件模式列表（无强制使用，仅保留向后兼容）"""
        return self.get("file_patterns", ["README.md", "readme.md"]) or ["README.md", "readme.md"]
    
    def get_exclude_patterns(self) -> List[str]:
        """获取排除模式列表（来自 config.yaml 的 exclusions）"""
        return self.get("exclusions", [])
    
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
    
    def get_target_folder_from_config(self) -> str:
        """兼容方法：等同于 get_target_folder"""
        return self.get_target_folder()
    
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
        return self.get("sync_settings.auto_sync_interval", 1)
    
    def get_cleanup_interval(self) -> int:
        """获取清理间隔(秒)"""
        return self.get("sync_settings.cleanup_interval", 3600)  # 默认1小时
    
    def set_cleanup_interval(self, interval_seconds: int) -> bool:
        """设置清理间隔(秒)"""
        if interval_seconds < 60:  # 最小1分钟
            print("清理间隔不能小于60秒")
            return False
        return self.set("sync_settings.cleanup_interval", interval_seconds)
    
    def get_move_unlinked_files(self) -> bool:
        """获取是否移动未链接文件"""
        return self.get("sync_settings.move_unlinked_files", True)
    
    def set_move_unlinked_files(self, enabled: bool) -> bool:
        """设置是否移动未链接文件"""
        return self.set("sync_settings.move_unlinked_files", enabled)
    
    def get_unlinked_subfolder(self) -> str:
        """获取未链接文件子文件夹名称"""
        return self.get("sync_settings.unlinked_subfolder", "unlinked")
    
    def set_unlinked_subfolder(self, subfolder_name: str) -> bool:
        """设置未链接文件子文件夹名称"""
        if not subfolder_name or "/" in subfolder_name or "\\" in subfolder_name:
            print("子文件夹名称无效")
            return False
        return self.set("sync_settings.unlinked_subfolder", subfolder_name)
    
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
        if _YAML_AVAILABLE:
            print(yaml.dump(self.config, default_flow_style=False, allow_unicode=True, indent=2))
        else:
            import json as _json
            print(_json.dumps(self.config, ensure_ascii=False, indent=2))
