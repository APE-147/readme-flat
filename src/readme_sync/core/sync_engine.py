# -*- coding: utf-8 -*-
"""同步引擎模块"""

import os
import shutil
import time
import threading
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set
from ..services.config import ConfigManager
from ..services.database import DatabaseManager
from .scanner import FileScanner


class SyncEngine:
    """同步引擎"""
    
    def __init__(self, config_manager: ConfigManager, db_manager: DatabaseManager):
        """初始化同步引擎"""
        self.config = config_manager
        self.db = db_manager
        self.scanner = FileScanner(config_manager)
        
        # 同步状态锁防止循环同步
        self._sync_locks: Set[str] = set()
        self._sync_lock = threading.Lock()
        
        # 时间窗口过滤 - 记录最近同步的文件和时间
        self._recent_syncs: Dict[str, float] = {}
        self._sync_cooldown = 3.0  # 3秒冷却时间
    
    def _can_sync(self, file_path: str) -> bool:
        """检查文件是否可以同步（防止循环同步）"""
        with self._sync_lock:
            # 检查是否已在同步中
            if file_path in self._sync_locks:
                print(f"[防循环] 文件正在同步中，跳过: {file_path}")
                return False
            
            # 检查时间窗口
            current_time = time.time()
            if file_path in self._recent_syncs:
                time_diff = current_time - self._recent_syncs[file_path]
                if time_diff < self._sync_cooldown:
                    print(f"[防循环] 文件在冷却期内，跳过: {file_path} (距离上次同步 {time_diff:.1f}秒)")
                    return False
            
            return True
    
    def _acquire_sync_lock(self, file_path: str) -> bool:
        """获取同步锁"""
        with self._sync_lock:
            if file_path in self._sync_locks:
                return False
            self._sync_locks.add(file_path)
            return True
    
    def _release_sync_lock(self, file_path: str):
        """释放同步锁并更新时间戳"""
        with self._sync_lock:
            self._sync_locks.discard(file_path)
            self._recent_syncs[file_path] = time.time()
    
    def _cleanup_old_syncs(self):
        """清理过期的同步记录"""
        current_time = time.time()
        with self._sync_lock:
            expired_files = [
                file_path for file_path, sync_time in self._recent_syncs.items()
                if current_time - sync_time > self._sync_cooldown * 2
            ]
            for file_path in expired_files:
                del self._recent_syncs[file_path]
    
    def sync_all(self) -> Dict[str, int]:
        """执行完整同步"""
        print("开始执行完整同步...")
        
        results = {
            'scanned': 0,
            'synced': 0,
            'reverse_synced': 0,
            'conflicts': 0,
            'errors': 0,
            'moved_detected': 0,
            'unlinked_moved': 0,
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
                elif sync_result == 'reverse_synced':
                    results['reverse_synced'] += 1
                elif sync_result == 'conflict':
                    results['conflicts'] += 1
            except Exception as e:
                print(f"同步文件失败 {file_info['source_path']}: {e}")
                results['errors'] += 1
        
        # 4. 清理孤立映射
        orphaned = self.db.cleanup_orphaned_mappings()
        if orphaned > 0:
            print(f"清理了 {orphaned} 个孤立映射")

        # 4.1 移动未链接文件（包括源文件丢失对应的目标文件）
        try:
            if self.config.get_move_unlinked_files():
                target_folder = self.config.get_target_folder()
                if target_folder and os.path.exists(target_folder):
                    moved = self.db.move_unlinked_files(target_folder, self.config.get_unlinked_subfolder())
                    results['unlinked_moved'] = moved
                    if moved > 0:
                        print(f"移动了 {moved} 个未链接文件到 {self.config.get_unlinked_subfolder()}/ 文件夹")
        except Exception as e:
            print(f"移动未链接文件阶段失败: {e}")

        # 5. 反向同步一遍（处理用户在目标的修改）
        try:
            reverse = self.reverse_sync_from_target()
            results['reverse_synced'] += reverse.get('synced', 0)
        except Exception as e:
            print(f"执行反向同步阶段失败: {e}")
        
        print(f"同步完成: 扫描 {results['scanned']}, 正向同步 {results['synced']}, 反向同步 {results['reverse_synced']}, 冲突 {results['conflicts']}, 错误 {results['errors']}")
        return results
    
    def sync_single_file(self, file_info: Dict[str, str]) -> str:
        """同步单个文件"""
        source_path = file_info['source_path']
        project_name = file_info['project_name']
        target_filename = file_info['target_filename']
        
        # 防循环同步检查
        if not self._can_sync(source_path):
            return 'skipped'
        
        # 获取同步锁
        if not self._acquire_sync_lock(source_path):
            return 'locked'
        
        try:
            # 检查数据库中是否有现有映射
            mapping = self.db.get_file_mapping(source_path)
            
            # 首先尝试在目标文件夹中递归搜索已存在的文件
            existing_target_file = self._find_existing_target_file(source_path, target_filename)
            
            if existing_target_file:
                # 找到已存在的文件，使用现有路径，不移动文件
                target_path = existing_target_file
                print(f"使用已存在的目标文件: {target_path}")
            else:
                # 构建默认目标路径（目标文件夹根目录，扁平化文件名）
                target_folder = self.config.get_target_folder()
                target_path = os.path.join(target_folder, os.path.basename(target_filename))
            
            if mapping and mapping['target_path'] != target_path:
                # 目标文件路径发生变化
                if os.path.exists(mapping['target_path']):
                    # 如果是因为找到了已存在的文件而改变路径，只更新映射，不移动文件
                    if existing_target_file:
                        print(f"更新映射到已存在的文件: {target_path}")
                        self.db.update_target_path(mapping['target_path'], target_path)
                    else:
                        # 检查新位置是否已存在文件
                        if os.path.exists(target_path):
                            # 新位置已存在文件，更新映射而不移动
                            print(f"检测到文件已存在于新位置: {target_path}")
                            self.db.update_target_path(mapping['target_path'], target_path)
                        else:
                            # 只有在确实需要移动文件时才移动（比如项目名称变化）
                            # 但是要避免不必要的文件夹结构调整
                            old_filename = os.path.basename(mapping['target_path'])
                            new_filename = os.path.basename(target_path)
                            
                            if old_filename != new_filename:
                                # 文件名变化
                                try:
                                    src_size = os.path.getsize(source_path) if os.path.exists(source_path) else -1
                                except Exception:
                                    src_size = -1
                                if src_size == 0:
                                    # 源文件为空：避免因为空文件（哈希相同）误移已有文件，改为新建目标文件
                                    print(
                                        f"源文件为空，避免误移。创建新目标文件: {target_path} 并保留原文件"
                                    )
                                    # 确保目录存在
                                    target_dir = os.path.dirname(target_path)
                                    target_folder = self.config.get_target_folder()
                                    if target_dir != target_folder:
                                        os.makedirs(target_dir, exist_ok=True)
                                    shutil.copy2(source_path, target_path)
                                    # 更新映射到新目标
                                    self.db.update_target_path(mapping['target_path'], target_path)
                                else:
                                    # 非空：按原逻辑移动
                                    print(f"项目名称变化，移动文件: {mapping['target_path']} -> {target_path}")
                                    self._move_target_file(mapping['target_path'], target_path)
                            else:
                                # 仅路径变化（用户手动移动），保持现有位置，更新映射
                                print(f"保持用户的文件组织结构: {mapping['target_path']}")
                                target_path = mapping['target_path']  # 使用现有路径
                else:
                    # 旧文件不存在，已经通过existing_target_file处理过了
                    pass
        
            # 判断是否需要同步
            sync_action = self._determine_sync_action(source_path, target_path, mapping)
            
            if sync_action == 'no_sync':
                return 'no_change'
            elif sync_action == 'conflict':
                return self._handle_conflict(source_path, target_path, mapping)
            elif sync_action == 'target_to_source':
                # 执行反向同步
                return self._perform_reverse_sync(source_path, target_path, mapping)
            else:
                # 执行正向同步
                return self._perform_sync(source_path, target_path, project_name, target_filename, sync_action)
        finally:
            # 释放同步锁
            self._release_sync_lock(source_path)
    
    def _determine_sync_action(self, source_path: str, target_path: str, mapping: Optional[Dict]) -> str:
        """决定同步操作类型 - 智能合并策略，尊重手动修改"""
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
        
        # 获取上次同步时间和哈希值
        last_sync_source_hash = mapping.get('source_hash') if mapping else None
        last_sync_target_hash = mapping.get('target_hash') if mapping else None
        last_sync_time = mapping.get('last_sync_time', 0) if mapping else 0
        
        # 检查自上次同步以来哪个文件被修改了
        source_changed = (last_sync_source_hash != source_hash) if last_sync_source_hash else True
        target_changed = (last_sync_target_hash != target_hash) if last_sync_target_hash else True
        
        # 智能合并策略
        if not source_changed and target_changed:
            # 只有目标文件被修改（用户手动编辑），执行反向同步
            print(f"检测到目标文件被手动修改，执行反向同步: {target_path} -> {source_path}")
            return 'target_to_source'
        elif source_changed and not target_changed:
            # 只有源文件被修改，同步到目标
            return 'source_to_target'
        elif source_changed and target_changed:
            # 两个文件都被修改，需要更细致的判断
            return self._handle_dual_modification(source_path, target_path, source_mtime, target_mtime, last_sync_time)
        else:
            # 都没有修改（理论上不应该到这里，因为哈希不同）
            # 考虑时间容忍度
            tolerance = self.config.get_tolerance_seconds()
            time_diff = abs(source_mtime - target_mtime)
            
            if time_diff <= tolerance:
                # 时间差在容忍范围内，保持目标文件（尊重用户的修改环境）
                return 'no_sync'
            
            # 选择较新的文件，但优先保护目标文件
            if target_mtime > source_mtime:
                return 'no_sync'  # 目标较新，保持不变
            else:
                return 'source_to_target'  # 源文件较新，同步
    
    def _handle_dual_modification(self, source_path: str, target_path: str, 
                                 source_mtime: float, target_mtime: float, last_sync_time: float) -> str:
        """处理双方都被修改的情况"""
        tolerance = self.config.get_tolerance_seconds()
        
        # 检查修改时间相对于上次同步的间隔
        source_time_since_sync = source_mtime - last_sync_time
        target_time_since_sync = target_mtime - last_sync_time
        
        # 如果目标文件的修改时间明显更近，优先保护目标文件
        if target_time_since_sync > source_time_since_sync and (target_mtime - source_mtime) > tolerance:
            print(f"目标文件修改更频繁，保护用户修改: {target_path}")
            return 'no_sync'
        
        # 如果源文件的修改时间明显更近，同步源文件
        if source_time_since_sync > target_time_since_sync and (source_mtime - target_mtime) > tolerance:
            return 'source_to_target'
        
        # 时间差不大，根据绝对时间和配置决定
        time_diff = abs(source_mtime - target_mtime)
        
        if time_diff <= tolerance:
            # 时间差很小，保护目标文件
            return 'no_sync'
        elif target_mtime > source_mtime:
            # 目标文件更新，保护用户修改
            print(f"目标文件更新，保护用户修改: {target_path}")
            return 'no_sync'
        else:
            # 源文件更新，但询问是否要覆盖用户修改
            return 'conflict'
    
    def _handle_conflict(self, source_path: str, target_path: str, mapping: Optional[Dict]) -> str:
        """处理冲突 - 智能冲突解决，优先保护用户修改"""
        resolution = self.config.get_conflict_resolution()
        source_mtime = os.path.getmtime(source_path)
        target_mtime = os.path.getmtime(target_path)
        
        # 增强的冲突检测 - 检查修改的显著性
        if mapping:
            last_sync_time = mapping.get('last_sync_time', 0)
            target_modification_gap = target_mtime - last_sync_time
            source_modification_gap = source_mtime - last_sync_time
            
            # 如果目标文件是最近修改的（相对于上次同步），优先保护
            if target_modification_gap > 0 and target_modification_gap < 3600:  # 1小时内的修改
                print(f"检测到目标文件最近被修改（{target_modification_gap/60:.1f}分钟前），保护用户修改: {target_path}")
                return 'no_sync'
        
        if resolution == 'latest':
            # 在latest模式下，也要尊重用户的手动修改
            if target_mtime > source_mtime:
                print(f"目标文件更新，保护用户修改: {target_path}")
                return 'no_sync'
            else:
                action = 'source_to_target'
        elif resolution == 'source_priority':
            # 即使是source_priority，也要给用户一个警告
            if target_mtime > source_mtime:
                print(f"警告: 即将覆盖较新的目标文件 {target_path}")
                print(f"源文件: {source_mtime}, 目标文件: {target_mtime}")
            action = 'source_to_target'
        elif resolution == 'target_priority':
            action = 'no_sync'  # 直接保护目标文件
        else:  # manual
            print(f"发现冲突: {source_path} <-> {target_path}")
            print(f"源文件修改时间: {time.ctime(source_mtime)}")
            print(f"目标文件修改时间: {time.ctime(target_mtime)}")
            print("冲突需要手动解决，跳过此文件")
            return 'conflict'
        
        # 执行冲突解决
        if action == 'no_sync':
            return 'no_sync'
        else:
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
                        # 只有在必要时才创建目录（避免在根目录下创建不必要的子文件夹）
                        target_dir = os.path.dirname(target_path)
                        target_folder = self.config.get_target_folder()
                        
                        # 如果target_path在根目录，不需要创建额外目录
                        if target_dir != target_folder:
                            os.makedirs(target_dir, exist_ok=True)
                        
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
    
    def _perform_reverse_sync(self, source_path: str, target_path: str, mapping: Optional[Dict]) -> str:
        """执行反向同步操作（从目标同步到源）"""
        try:
            if not os.path.exists(target_path):
                print(f"目标文件不存在，无法反向同步: {target_path}")
                return 'error'
            
            if not os.path.exists(source_path):
                print(f"源文件不存在，无法反向同步: {source_path}")
                return 'error'
            
            # 执行反向同步
            shutil.copy2(target_path, source_path)
            print(f"反向同步: {target_path} -> {source_path}")
            
            # 更新数据库映射
            if mapping:
                project_name = mapping.get('project_name', 'Unknown')
                target_filename = mapping.get('target_filename')
                
                # 如果target_filename不存在，从路径中生成
                if not target_filename:
                    project_name_extracted = self.scanner.extract_project_name(source_path)
                    target_filename = self.scanner.generate_target_filename(project_name_extracted)
                
                self.db.add_file_mapping(source_path, target_path, project_name, target_filename)
            
            # 更新同步时间
            source_hash = self.db.get_file_hash(source_path)
            target_hash = self.db.get_file_hash(target_path)
            source_mtime = os.path.getmtime(source_path)
            target_mtime = os.path.getmtime(target_path)
            
            self.db.update_sync_time(source_path, source_hash, target_hash, source_mtime, target_mtime)
            
            return 'reverse_synced'
        
        except Exception as e:
            print(f"反向同步失败: {e}")
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
        """在目标文件夹中递归搜索是否存在对应的文件

        只按目标“文件名”匹配，避免因为内容哈希相同（例如 0 字节文件）而误将不同项目视为同一文件。
        """
        target_folder = self.config.get_target_folder()
        if not target_folder or not os.path.exists(target_folder):
            return None

        # 仅文件名（扁平化比较）
        base_target_name = os.path.basename(target_filename)
        base_target_noext = os.path.splitext(base_target_name)[0].lower()

        # 递归搜索目标文件夹
        for root, dirs, files in os.walk(target_folder):
            for file in files:
                if file.lower().endswith('.md'):
                    file_path = os.path.join(root, file)
                    # 文件名精确匹配（扁平化）
                    if file == base_target_name:
                        return file_path

                    # 基名匹配（去扩展名后相等）
                    base_file = os.path.splitext(file)[0].lower()
                    if base_target_noext == base_file:
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
                    # 通过文件名匹配映射（忽略路径）
                    from os.path import basename
                    fname = basename(target_path)
                    mapping = self.db.find_mapping_by_filename(fname)
                    if mapping:
                        self.db.update_target_path(mapping['target_path'], target_path)
                    else:
                        # 最后回退：扫描源目录，按生成的目标文件名比对，建立新映射
                        try:
                            expected = fname
                            candidates = self.scanner.scan_all_sources()
                            matched = None
                            for fi in candidates:
                                if fi.get('target_filename') == expected:
                                    matched = fi
                                    break
                            if matched:
                                source_path = matched['source_path']
                                project_name = matched['project_name']
                                # 建立/更新映射关系
                                self.db.add_file_mapping(source_path, target_path, project_name, expected)
                                mapping = self.db.get_file_mapping(source_path)
                            else:
                                results['no_mapping'] += 1
                                continue
                        except Exception:
                            results['no_mapping'] += 1
                            continue
            
            # 检查源文件是否存在
            source_path = mapping['source_path']
            if not os.path.exists(source_path):
                print(f"源文件不存在，跳过: {source_path}")
                continue
            
            # 使用更稳健的判定：目标较新且内容不同 -> 反向
            try:
                if not self._can_sync(source_path) or not self._acquire_sync_lock(source_path):
                    continue
                try:
                    tolerance = self.config.get_tolerance_seconds()
                    s_m = os.path.getmtime(source_path)
                    t_m = os.path.getmtime(target_path)
                    s_hash = self.db.get_file_hash(source_path)
                    t_hash = self.db.get_file_hash(target_path)
                    if t_hash != s_hash and (t_m - s_m) > tolerance:
                        result = self._perform_reverse_sync(source_path, target_path, mapping)
                        if result == 'reverse_synced':
                            results['synced'] += 1
                            print(f"智能反向同步: {target_path} -> {source_path}")
                        else:
                            print(f"反向同步失败: {target_path}")
                            results['errors'] += 1
                    else:
                        # 回退到原有策略
                        sync_action = self._determine_sync_action(source_path, target_path, mapping)
                        if sync_action == 'target_to_source':
                            result = self._perform_reverse_sync(source_path, target_path, mapping)
                            if result == 'reverse_synced':
                                results['synced'] += 1
                                print(f"智能反向同步: {target_path} -> {source_path}")
                            else:
                                print(f"反向同步失败: {target_path}")
                                results['errors'] += 1
                        elif sync_action == 'no_sync':
                            print(f"检测到目标文件被手动修改，保持现状: {target_path}")
                        else:
                            print(f"根据智能策略，不执行反向同步: {target_path} (动作: {sync_action})")
                finally:
                    self._release_sync_lock(source_path)
            
            except Exception as e:
                print(f"反向同步失败 {target_path}: {e}")
                results['errors'] += 1
        
        print(f"反向同步完成: 扫描 {results['scanned']}, 同步 {results['synced']}, 无映射 {results['no_mapping']}, 错误 {results['errors']}")
        return results

    def reverse_all(self, force: bool = False) -> Dict[str, int]:
        """从目标文件夹反向同步到源（可选强制）

        - 当 force=True 时，只要目标与源内容不同，一律执行 target->source。
        - 否则遵循智能策略（_determine_sync_action）。
        """
        results = {
            'scanned': 0,
            'synced': 0,
            'errors': 0,
            'no_mapping': 0
        }
        target_files = self.scanner.scan_target_folder()
        results['scanned'] = len(target_files)
        from os.path import basename

        for tf in target_files:
            target_path = tf['target_path']
            try:
                mapping = self.db.find_mapping_by_target(target_path)
                if not mapping:
                    file_hash = self.db.get_file_hash(target_path)
                    mapping = self.db.find_mapping_by_hash(file_hash)
                    if mapping:
                        self.db.update_target_path(mapping['target_path'], target_path)
                    else:
                        # 文件名匹配
                        mapping = self.db.find_mapping_by_filename(basename(target_path))
                        if mapping:
                            self.db.update_target_path(mapping['target_path'], target_path)
                if not mapping:
                    results['no_mapping'] += 1
                    continue

                source_path = mapping['source_path']
                if not os.path.exists(source_path) or not os.path.exists(target_path):
                    continue

                # 加锁防止与正向同步竞争
                if not self._can_sync(source_path):
                    continue
                if not self._acquire_sync_lock(source_path):
                    continue
                try:
                    if force:
                        s_hash = self.db.get_file_hash(source_path)
                        t_hash = self.db.get_file_hash(target_path)
                        if s_hash != t_hash:
                            r = self._perform_reverse_sync(source_path, target_path, mapping)
                            if r == 'reverse_synced':
                                results['synced'] += 1
                        continue

                    # 简化且可靠的目标优先策略：当目标较新且内容不同则反向
                    tolerance = self.config.get_tolerance_seconds()
                    s_m = os.path.getmtime(source_path)
                    t_m = os.path.getmtime(target_path)
                    s_hash = self.db.get_file_hash(source_path)
                    t_hash = self.db.get_file_hash(target_path)
                    if t_hash != s_hash and (t_m - s_m) > tolerance:
                        r = self._perform_reverse_sync(source_path, target_path, mapping)
                        if r == 'reverse_synced':
                            results['synced'] += 1
                    else:
                        # 回退到原有智能策略
                        action = self._determine_sync_action(source_path, target_path, mapping)
                        if action == 'target_to_source':
                            r = self._perform_reverse_sync(source_path, target_path, mapping)
                            if r == 'reverse_synced':
                                results['synced'] += 1
                finally:
                    self._release_sync_lock(source_path)
                # 其余保持现状
            except Exception as e:
                print(f"反向同步（force={force}) 失败 {target_path}: {e}")
                results['errors'] += 1

        return results
    
    def force_sync_target_to_source(self, target_path: str) -> bool:
        """强制将目标文件同步到源文件（用户手动解决冲突时使用）"""
        try:
            # 查找对应的源文件映射
            mapping = self.db.find_mapping_by_target(target_path)
            
            if not mapping:
                # 通过哈希查找
                file_hash = self.db.get_file_hash(target_path)
                mapping = self.db.find_mapping_by_hash(file_hash)
                
                if not mapping:
                    print(f"无法找到目标文件的源文件映射: {target_path}")
                    return False
            
            source_path = mapping['source_path']
            
            if not os.path.exists(source_path):
                print(f"源文件不存在: {source_path}")
                return False
            
            # 执行反向同步
            shutil.copy2(target_path, source_path)
            print(f"手动解决冲突 - 反向同步: {target_path} -> {source_path}")
            
            # 更新数据库
            source_hash = self.db.get_file_hash(source_path)
            target_hash = self.db.get_file_hash(target_path)
            source_mtime = os.path.getmtime(source_path)
            target_mtime = os.path.getmtime(target_path)
            
            self.db.update_sync_time(source_path, source_hash, target_hash, source_mtime, target_mtime)
            return True
            
        except Exception as e:
            print(f"强制同步失败: {e}")
            return False
    
    def get_conflicts(self) -> List[Dict[str, str]]:
        """获取当前存在冲突的文件列表"""
        conflicts = []
        mappings = self.db.get_all_mappings()
        
        for mapping in mappings:
            source_path = mapping['source_path']
            target_path = mapping['target_path']
            
            if not os.path.exists(source_path) or not os.path.exists(target_path):
                continue
            
            source_hash = self.db.get_file_hash(source_path)
            target_hash = self.db.get_file_hash(target_path)
            
            # 检查是否有内容差异
            if source_hash != target_hash:
                source_mtime = os.path.getmtime(source_path)
                target_mtime = os.path.getmtime(target_path)
                last_sync_time = mapping.get('last_sync_time', 0)
                
                # 检查是否为实际冲突（双方都有修改）
                source_changed = mapping.get('source_hash') != source_hash if mapping.get('source_hash') else True
                target_changed = mapping.get('target_hash') != target_hash if mapping.get('target_hash') else True
                
                if source_changed and target_changed:
                    conflicts.append({
                        'source_path': source_path,
                        'target_path': target_path,
                        'source_mtime': source_mtime,
                        'target_mtime': target_mtime,
                        'last_sync_time': last_sync_time,
                        'source_newer': source_mtime > target_mtime,
                        'target_newer': target_mtime > source_mtime
                    })
        
        return conflicts
    
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
