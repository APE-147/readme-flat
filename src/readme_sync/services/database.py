# -*- coding: utf-8 -*-
"""数据库管理模块"""

import sqlite3
import os
import hashlib
import time
from pathlib import Path
from .config import ConfigManager
from typing import List, Dict, Optional, Tuple


class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self, db_path: str = None):
        """初始化数据库"""
        if db_path is None:
            # 统一从配置文件目录读取数据库位置
            cfg = ConfigManager()
            config_dir = Path(cfg.get_config_dir())
            config_dir.mkdir(parents=True, exist_ok=True)
            db_path = config_dir / "database.db"
        
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """初始化数据库结构"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS file_mappings (
                    id INTEGER PRIMARY KEY,
                    source_path TEXT UNIQUE NOT NULL,
                    target_path TEXT NOT NULL,
                    project_name TEXT NOT NULL,
                    renamed_filename TEXT NOT NULL,
                    source_hash TEXT,
                    target_hash TEXT,
                    source_mtime REAL,
                    target_mtime REAL,
                    last_sync_time REAL,
                    sync_direction TEXT DEFAULT 'both',
                    created_at REAL DEFAULT (julianday('now')),
                    updated_at REAL DEFAULT (julianday('now'))
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at REAL DEFAULT (julianday('now'))
                )
            """)
            
            conn.commit()
    
    def get_file_hash(self, file_path: str) -> str:
        """计算文件哈希值"""
        try:
            with open(file_path, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception:
            return ""
    
    def add_file_mapping(self, source_path: str, target_path: str, 
                        project_name: str, renamed_filename: str) -> bool:
        """添加文件映射"""
        try:
            source_hash = self.get_file_hash(source_path)
            target_hash = self.get_file_hash(target_path) if os.path.exists(target_path) else ""
            source_mtime = os.path.getmtime(source_path) if os.path.exists(source_path) else 0
            target_mtime = os.path.getmtime(target_path) if os.path.exists(target_path) else 0
            
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO file_mappings 
                    (source_path, target_path, project_name, renamed_filename, 
                     source_hash, target_hash, source_mtime, target_mtime, 
                     last_sync_time, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, julianday('now'))
                """, (source_path, target_path, project_name, renamed_filename,
                      source_hash, target_hash, source_mtime, target_mtime, time.time()))
                conn.commit()
            return True
        except Exception as e:
            print(f"添加文件映射失败: {e}")
            return False
    
    def get_file_mapping(self, source_path: str) -> Optional[Dict]:
        """获取文件映射"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM file_mappings WHERE source_path = ?", 
                (source_path,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_all_mappings(self) -> List[Dict]:
        """获取所有文件映射"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM file_mappings ORDER BY updated_at DESC")
            return [dict(row) for row in cursor.fetchall()]
    
    def find_mapping_by_target(self, target_path: str) -> Optional[Dict]:
        """根据目标路径查找映射"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM file_mappings WHERE target_path = ?", 
                (target_path,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def find_mapping_by_hash(self, file_hash: str) -> Optional[Dict]:
        """根据哈希值查找映射"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM file_mappings WHERE source_hash = ? OR target_hash = ?", 
                (file_hash, file_hash)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def find_mapping_by_filename(self, renamed_filename: str) -> Optional[Dict]:
        """根据重命名后的目标文件名查找映射（忽略路径，仅匹配文件名）"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM file_mappings WHERE lower(renamed_filename) = lower(?)",
                    (renamed_filename,)
                )
                rows = cursor.fetchall()
                if not rows:
                    return None
                # 如果有多个，返回最新更新的一条
                rows = sorted(rows, key=lambda r: r["updated_at"] if "updated_at" in r.keys() else 0, reverse=True)
                return dict(rows[0])
        except Exception:
            return None
    
    def update_target_path(self, old_target: str, new_target: str) -> bool:
        """更新目标文件路径（用于处理移动）"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    UPDATE file_mappings 
                    SET target_path = ?, updated_at = julianday('now')
                    WHERE target_path = ?
                """, (new_target, old_target))
                conn.commit()
            return True
        except Exception as e:
            print(f"更新路径失败: {e}")
            return False
    
    def update_sync_time(self, source_path: str, 
                        source_hash: str = None, target_hash: str = None,
                        source_mtime: float = None, target_mtime: float = None) -> bool:
        """更新同步时间信息"""
        try:
            current_time = time.time()
            with sqlite3.connect(self.db_path) as conn:
                params = [current_time]
                sql_parts = ["last_sync_time = ?", "updated_at = julianday('now')"]
                
                if source_hash is not None:
                    sql_parts.append("source_hash = ?")
                    params.append(source_hash)
                
                if target_hash is not None:
                    sql_parts.append("target_hash = ?")
                    params.append(target_hash)
                
                if source_mtime is not None:
                    sql_parts.append("source_mtime = ?")
                    params.append(source_mtime)
                
                if target_mtime is not None:
                    sql_parts.append("target_mtime = ?")
                    params.append(target_mtime)
                
                params.append(source_path)
                
                sql = f"UPDATE file_mappings SET {', '.join(sql_parts)} WHERE source_path = ?"
                conn.execute(sql, params)
                conn.commit()
            return True
        except Exception as e:
            print(f"更新同步时间失败: {e}")
            return False
    
    def remove_mapping(self, source_path: str) -> bool:
        """删除文件映射"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM file_mappings WHERE source_path = ?", (source_path,))
                conn.commit()
            return True
        except Exception as e:
            print(f"删除文件映射失败: {e}")
            return False
    
    def set_config(self, key: str, value: str) -> bool:
        """设置配置项"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO config (key, value, updated_at)
                    VALUES (?, ?, julianday('now'))
                """, (key, value))
                conn.commit()
            return True
        except Exception as e:
            print(f"设置配置失败: {e}")
            return False
    
    def get_config(self, key: str, default: str = None) -> Optional[str]:
        """获取配置项"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT value FROM config WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row[0] if row else default
    
    def get_all_configs(self) -> Dict[str, str]:
        """获取所有配置项"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT key, value FROM config")
            return dict(cursor.fetchall())
    
    def cleanup_orphaned_mappings(self) -> int:
        """清理数据库中的孤立映射（文件不存在或超出源文件夹范围）"""
        from .config import ConfigManager
        
        orphaned_count = 0
        mappings = self.get_all_mappings()
        config = ConfigManager()
        enabled_sources = config.get_enabled_source_folders()
        
        for mapping in mappings:
            source_path = mapping.get('source_path', '')
            should_remove = False
            
            # 检查源文件是否存在
            if not os.path.exists(source_path):
                should_remove = True
                print(f"移除孤立映射（文件不存在）: {source_path}")
            else:
                # 检查源文件是否在当前配置的源文件夹范围内
                is_in_scope = False
                for source_folder in enabled_sources:
                    if source_path.startswith(source_folder):
                        is_in_scope = True
                        break
                
                if not is_in_scope:
                    should_remove = True
                    print(f"移除孤立映射（超出范围）: {source_path}")
            
            if should_remove:
                self.remove_mapping(source_path)
                orphaned_count += 1
        
        return orphaned_count
    
    def find_unlinked_files(self, target_folder: str) -> List[str]:
        """递归查找目标文件夹中的未链接文件（包括源地址不存在的文件）"""
        if not os.path.exists(target_folder):
            return []
        
        # 获取所有映射
        mappings = self.get_all_mappings()
        
        # 构建已跟踪文件的完整路径集合
        tracked_files = set()
        files_with_missing_source = []
        
        for mapping in mappings:
            target_path = mapping.get('target_path', '')
            source_path = mapping.get('source_path', '')
            
            if target_path:
                tracked_files.add(os.path.normpath(target_path))
                
                # 检查源文件是否存在，如果不存在则标记目标文件为需要移动
                if source_path and not os.path.exists(source_path):
                    if os.path.exists(target_path):
                        files_with_missing_source.append(target_path)
        
        # 递归扫描目标文件夹中的所有文件
        unlinked_files = []
        
        def scan_directory(directory):
            try:
                for item in os.listdir(directory):
                    item_path = os.path.join(directory, item)
                    
                    if os.path.isfile(item_path) and item.endswith('.md'):
                        # 标准化路径进行比较
                        normalized_path = os.path.normpath(item_path)
                        
                        # 如果文件不在跟踪列表中，则为未链接文件
                        if normalized_path not in tracked_files:
                            unlinked_files.append(item_path)
                    
                    elif os.path.isdir(item_path):
                        # 跳过unlinked文件夹本身，避免重复处理
                        if os.path.basename(item_path) != self._get_unlinked_subfolder_name():
                            scan_directory(item_path)
                            
            except PermissionError:
                print(f"权限不足，跳过目录: {directory}")
            except Exception as e:
                print(f"扫描目录失败 {directory}: {e}")
        
        scan_directory(target_folder)
        
        # 合并未链接文件和源地址不存在的文件
        all_unlinked = list(set(unlinked_files + files_with_missing_source))
        
        return all_unlinked
    
    def _get_unlinked_subfolder_name(self) -> str:
        """获取未链接文件子文件夹名称"""
        try:
            from .config import ConfigManager
            config = ConfigManager()
            return config.get_unlinked_subfolder()
        except:
            return "unlinked"
    
    def move_unlinked_files(self, target_folder: str, unlinked_subfolder: str = "unlinked") -> int:
        """移动未链接文件到子文件夹"""
        unlinked_files = self.find_unlinked_files(target_folder)
        
        if not unlinked_files:
            return 0
        
        # 创建未链接文件夹
        unlinked_dir = os.path.join(target_folder, unlinked_subfolder)
        os.makedirs(unlinked_dir, exist_ok=True)
        
        moved_count = 0
        
        for file_path in unlinked_files:
            try:
                file_name = os.path.basename(file_path)
                new_path = os.path.join(unlinked_dir, file_name)
                
                # 如果目标位置已存在文件，添加时间戳
                if os.path.exists(new_path):
                    import time
                    timestamp = int(time.time())
                    name, ext = os.path.splitext(file_name)
                    new_name = f"{name}_{timestamp}{ext}"
                    new_path = os.path.join(unlinked_dir, new_name)
                
                # 移动文件
                import shutil
                shutil.move(file_path, new_path)
                moved_count += 1
                
                print(f"移动未链接文件: {file_name} -> {unlinked_subfolder}/{os.path.basename(new_path)}")
                
            except Exception as e:
                print(f"移动文件失败 {file_path}: {e}")
        
        return moved_count
    
    def show_status(self):
        """显示数据库和同步状态"""
        try:
            mappings = self.get_all_mappings()
            configs = self.get_all_configs()
            
            print("\n=== README Sync 状态 ===")
            print(f"总映射数量: {len(mappings)}")
            
            if mappings:
                print("\n文件映射:")
                for mapping in mappings[:5]:  # 显示前5个映射
                    print(f"  {mapping['project_name']}: {mapping['source_path']} -> {mapping['target_path']}")
                
                if len(mappings) > 5:
                    print(f"  ... 还有 {len(mappings) - 5} 个映射")
            
            if configs:
                print("\n配置信息:")
                for key, value in configs.items():
                    print(f"  {key}: {value}")
            
            print("\n数据库位置:", self.db_path)
            
        except Exception as e:
            print(f"获取状态失败: {e}")
