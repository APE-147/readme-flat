# -*- coding: utf-8 -*-
"""同步引擎模块"""

import os
import shutil
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from .config import ConfigManager
from .database import DatabaseManager
from .scanner import FileScanner


class SyncEngine:
    """同步引擎"""
    
    def __init__(self, config_manager: ConfigManager, db_manager: DatabaseManager):
        """初始化同步引擎"""
        self.config = config_manager
        self.db = db_manager
        self.scanner = FileScanner(config_manager)
    
    def sync_all(self) -> Dict[str, int]:
        """执行完整同步"""
        print("开始执行完整同步...")
        
        results = {
            'scanned': 0,
            'synced': 0,
            'conflicts': 0,
            'errors': 0,
            'moved_detected': 0
        }
        
        # 1. 检测文件移动
        moved_files = self.scanner.detect_moved_files(self.db)
        if moved_files:
            print(f"检测到 {len(moved_files)} 个文件被移动，更新映射...")
            for moved in moved_files:
                self.db.update_target_path(moved['old_target_path'], moved['new_target_path'])
            results['moved_detected'] = len(moved_files)
        
        # 2. 扫描所有文件
        readme_files = self.scanner.scan_all_sources()
        results['scanned'] = len(readme_files)
        
        if not readme_files:
            print("未找到任何README文件")
            return results
        
        # 3. 同步每个文件
        for file_info in readme_files:
            try:
                sync_result = self.sync_single_file(file_info)
                if sync_result == 'synced':
                    results['synced'] += 1
                elif sync_result == 'conflict':
                    results['conflicts'] += 1
            except Exception as e:
                print(f"同步文件失败 {file_info['source_path']}: {e}")
                results['errors'] += 1
        
        # 4. 清理孤立映射
        orphaned = self.db.cleanup_orphaned_mappings()
        if orphaned > 0:
            print(f"清理了 {orphaned} 个孤立映射")
        
        print(f"同步完成: 扫描 {results['scanned']}, 同步 {results['synced']}, 冲突 {results['conflicts']}, 错误 {results['errors']}")
        return results
    
    def sync_single_file(self, file_info: Dict[str, str]) -> str:
        """同步单个文件"""
        source_path = file_info['source_path']
        project_name = file_info['project_name']
        target_filename = file_info['target_filename']
        
        # 构建目标路径
        target_folder = self.config.get_target_folder()
        target_path = os.path.join(target_folder, target_filename)
        
        # 检查数据库中是否有现有映射
        mapping = self.db.get_file_mapping(source_path)
        
        if mapping and mapping['target_path'] != target_path:
            # 目标文件名变化或目录重命名
            if os.path.exists(mapping['target_path']):
                # 检查新位置是否已存在文件
                if os.path.exists(target_path):
                    # 新位置已存在文件，更新映射而不移动
                    print(f"检测到文件已存在于新位置: {target_path}")
                    self.db.update_target_path(mapping['target_path'], target_path)
                else:
                    # 旧文件存在，移动到新位置
                    self._move_target_file(mapping['target_path'], target_path)
            else:
                # 旧文件不存在，递归搜索目标文件夹查找是否存在对应文件
                existing_file = self._find_existing_target_file(source_path, target_filename)
                if existing_file:
                    # 找到已存在的文件，更新映射
                    print(f"在目标文件夹中找到已存在的文件: {existing_file}")
                    self.db.update_target_path(mapping['target_path'], existing_file)
                    target_path = existing_file  # 更新目标路径
        
        # 判断是否需要同步
        sync_action = self._determine_sync_action(source_path, target_path, mapping)
        
        if sync_action == 'no_sync':
            return 'no_change'
        elif sync_action == 'conflict':
            return self._handle_conflict(source_path, target_path, mapping)
        else:
            # 执行同步
            return self._perform_sync(source_path, target_path, project_name, target_filename, sync_action)
    
    def _determine_sync_action(self, source_path: str, target_path: str, mapping: Optional[Dict]) -> str:
        """决定同步操作类型"""
        source_exists = os.path.exists(source_path)
        target_exists = os.path.exists(target_path)
        
        if not source_exists:
            return 'no_sync'  # 源文件不存在
        
        if not target_exists:
            return 'source_to_target'  # 目标不存在，复制源文件
        
        # 比较文件内容和修改时间
        source_mtime = os.path.getmtime(source_path)
        target_mtime = os.path.getmtime(target_path)
        source_hash = self.db.get_file_hash(source_path)
        target_hash = self.db.get_file_hash(target_path)
        
        # 内容相同，无需同步
        if source_hash == target_hash:
            # 更新数据库记录
            if mapping:
                self.db.update_sync_time(source_path, source_hash, target_hash, source_mtime, target_mtime)
            return 'no_sync'
        
        # 考虑时间容忍度
        tolerance = self.config.get_tolerance_seconds()
        time_diff = abs(source_mtime - target_mtime)
        
        if time_diff <= tolerance:
            # 时间差在容忍范围内，选择较新的文件
            return 'source_to_target' if source_mtime >= target_mtime else 'target_to_source'
        
        # 时间差超出容忍度，根据配置决定
        if source_mtime > target_mtime:
            return 'source_to_target'
        elif target_mtime > source_mtime:
            return 'target_to_source'
        else:
            return 'conflict'
    
    def _handle_conflict(self, source_path: str, target_path: str, mapping: Optional[Dict]) -> str:
        """处理冲突"""
        resolution = self.config.get_conflict_resolution()
        
        if resolution == 'latest':
            source_mtime = os.path.getmtime(source_path)
            target_mtime = os.path.getmtime(target_path)
            action = 'source_to_target' if source_mtime >= target_mtime else 'target_to_source'
        elif resolution == 'source_priority':
            action = 'source_to_target'
        elif resolution == 'target_priority':
            action = 'target_to_source'
        else:  # manual
            print(f"发现冲突: {source_path} <-> {target_path}")
            print("冲突需要手动解决")
            return 'conflict'
        
        # 执行冲突解决
        project_name = self.scanner.extract_project_name(source_path)
        target_filename = self.scanner.generate_target_filename(project_name)
        return self._perform_sync(source_path, target_path, project_name, target_filename, action)
    
    def _perform_sync(self, source_path: str, target_path: str, project_name: str, 
                     target_filename: str, action: str) -> str:
        """执行同步操作"""
        try:
            if action == 'source_to_target':
                # 在复制之前，先检查目标文件夹中是否已存在对应文件
                if not os.path.exists(target_path):
                    existing_file = self._find_existing_target_file(source_path, target_filename)
                    if existing_file:
                        # 找到已存在的文件，更新映射而不复制
                        print(f"发现已存在的文件，更新映射: {existing_file}")
                        target_path = existing_file
                    else:
                        # 确保目标目录存在并复制文件
                        os.makedirs(os.path.dirname(target_path), exist_ok=True)
                        shutil.copy2(source_path, target_path)
                        print(f"同步: {source_path} -> {target_path}")
                else:
                    # 目标文件已存在，直接复制覆盖
                    shutil.copy2(source_path, target_path)
                    print(f"同步: {source_path} -> {target_path}")
            elif action == 'target_to_source':
                shutil.copy2(target_path, source_path)
                print(f"反向同步: {target_path} -> {source_path}")
            
            # 更新数据库映射
            self.db.add_file_mapping(source_path, target_path, project_name, target_filename)
            
            # 更新同步时间
            source_hash = self.db.get_file_hash(source_path)
            target_hash = self.db.get_file_hash(target_path)
            source_mtime = os.path.getmtime(source_path)
            target_mtime = os.path.getmtime(target_path)
            
            self.db.update_sync_time(source_path, source_hash, target_hash, source_mtime, target_mtime)
            
            return 'synced'
        
        except Exception as e:
            print(f"同步失败: {e}")
            return 'error'
    
    def _move_target_file(self, old_path: str, new_path: str):
        """移动目标文件"""
        try:
            # 确保新目标目录存在
            os.makedirs(os.path.dirname(new_path), exist_ok=True)
            shutil.move(old_path, new_path)
            print(f"移动文件: {old_path} -> {new_path}")
        except Exception as e:
            print(f"移动文件失败: {e}")
    
    def _find_existing_target_file(self, source_path: str, target_filename: str) -> Optional[str]:
        """在目标文件夹中递归搜索是否存在对应的文件"""
        target_folder = self.config.get_target_folder()
        if not target_folder or not os.path.exists(target_folder):
            return None
        
        # 获取源文件的哈希值用于匹配
        source_hash = self.db.get_file_hash(source_path)
        if not source_hash:
            return None
        
        # 递归搜索目标文件夹
        for root, dirs, files in os.walk(target_folder):
            for file in files:
                if file.lower().endswith('.md'):
                    file_path = os.path.join(root, file)
                    
                    # 方法1: 通过文件名匹配（精确匹配或相似匹配）
                    if file == target_filename:
                        return file_path
                    
                    # 方法2: 通过文件哈希值匹配（内容相同）
                    file_hash = self.db.get_file_hash(file_path)
                    if file_hash and file_hash == source_hash:
                        return file_path
                    
                    # 方法3: 通过文件名模糊匹配（去除扩展名后的基本匹配）
                    base_target = os.path.splitext(target_filename)[0].lower()
                    base_file = os.path.splitext(file)[0].lower()
                    if base_target == base_file:
                        return file_path
        
        return None
    
    def reverse_sync_from_target(self) -> Dict[str, int]:
        """从目标文件夹反向同步到源文件夹"""
        print("开始反向同步...")
        
        results = {
            'scanned': 0,
            'synced': 0,
            'errors': 0,
            'no_mapping': 0
        }
        
        # 扫描目标文件夹
        target_files = self.scanner.scan_target_folder()
        results['scanned'] = len(target_files)
        
        for target_file in target_files:
            target_path = target_file['target_path']
            
            # 查找对应的源文件映射
            mapping = self.db.find_mapping_by_target(target_path)
            
            if not mapping:
                # 通过哈希查找
                file_hash = self.db.get_file_hash(target_path)
                mapping = self.db.find_mapping_by_hash(file_hash)
                
                if mapping:
                    # 更新映射
                    self.db.update_target_path(mapping['target_path'], target_path)
                else:
                    results['no_mapping'] += 1
                    continue
            
            # 检查源文件是否存在
            source_path = mapping['source_path']
            if not os.path.exists(source_path):
                print(f"源文件不存在，跳过: {source_path}")
                continue
            
            # 判断是否需要反向同步
            try:
                target_mtime = os.path.getmtime(target_path)
                source_mtime = os.path.getmtime(source_path)
                
                if target_mtime > source_mtime:
                    shutil.copy2(target_path, source_path)
                    print(f"反向同步: {target_path} -> {source_path}")
                    results['synced'] += 1
                    
                    # 更新数据库
                    source_hash = self.db.get_file_hash(source_path)
                    target_hash = self.db.get_file_hash(target_path)
                    self.db.update_sync_time(source_path, source_hash, target_hash, source_mtime, target_mtime)
            
            except Exception as e:
                print(f"反向同步失败 {target_path}: {e}")
                results['errors'] += 1
        
        print(f"反向同步完成: 扫描 {results['scanned']}, 同步 {results['synced']}, 无映射 {results['no_mapping']}, 错误 {results['errors']}")
        return results
    
    def get_sync_status(self) -> Dict[str, any]:
        """获取同步状态"""
        mappings = self.db.get_all_mappings()
        stats = self.scanner.get_file_stats()
        
        # 统计分析
        outdated_count = 0
        missing_source = 0
        missing_target = 0
        
        for mapping in mappings:
            source_path = mapping['source_path']
            target_path = mapping['target_path']
            
            if not os.path.exists(source_path):
                missing_source += 1
                continue
            
            if not os.path.exists(target_path):
                missing_target += 1
                continue
            
            # 检查是否过期
            current_source_hash = self.db.get_file_hash(source_path)
            current_target_hash = self.db.get_file_hash(target_path)
            
            if (current_source_hash != mapping.get('source_hash') or 
                current_target_hash != mapping.get('target_hash')):
                outdated_count += 1
        
        return {
            'total_mappings': len(mappings),
            'source_files': stats['source_files'],
            'target_files': stats['target_files'],
            'source_folders': stats['source_folders'],
            'outdated_files': outdated_count,
            'missing_source': missing_source,
            'missing_target': missing_target,
            'last_sync': max([m.get('last_sync_time', 0) for m in mappings], default=0)
        }