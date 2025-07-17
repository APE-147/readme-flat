# -*- coding: utf-8 -*-
"""数据库管理模块"""

import sqlite3
import os
import hashlib
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple


class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self, db_path: str = None):
        """初始化数据库"""
        if db_path is None:
            # 使用新的数据目录路径
            project_data_dir = os.getenv('PROJECT_DATA_DIR')
            if project_data_dir:
                config_dir = Path(project_data_dir)
            else:
                # 使用默认的新数据目录结构
                config_dir = Path.home() / "Developer" / "Code" / "Data" / "srv" / "readme_flat"
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
        """清理数据库中不存在的源文件映射"""
        orphaned_count = 0
        mappings = self.get_all_mappings()
        
        for mapping in mappings:
            if not os.path.exists(mapping['source_path']):
                self.remove_mapping(mapping['source_path'])
                orphaned_count += 1
        
        return orphaned_count
    
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