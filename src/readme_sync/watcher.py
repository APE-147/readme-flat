# -*- coding: utf-8 -*-
"""文件系统监控模块 - 实现实时文件变化检测"""

import os
import time
import threading
from pathlib import Path
from typing import Dict, List, Optional, Callable
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent
from .config import ConfigManager
from .database import DatabaseManager
from .sync_engine import SyncEngine


class ReadmeFileHandler(FileSystemEventHandler):
    """README文件变化处理器"""
    
    def __init__(self, sync_engine: SyncEngine, config: ConfigManager, 
                 source_folder: str = None, is_target_folder: bool = False):
        """初始化文件处理器"""
        self.sync_engine = sync_engine
        self.config = config
        self.source_folder = source_folder
        self.is_target_folder = is_target_folder
        self.debounce_time = 2  # 防抖时间，秒
        self.pending_events = {}  # 待处理事件
        self.lock = threading.Lock()
        
        # 启动防抖处理线程
        self.debounce_thread = threading.Thread(target=self._debounce_worker, daemon=True)
        self.debounce_thread.start()
    
    def on_modified(self, event: FileSystemEvent):
        """文件修改事件"""
        if event.is_directory:
            return
        
        file_path = event.src_path
        if self._is_readme_file(file_path):
            self._schedule_sync(file_path, 'modified')
    
    def on_created(self, event: FileSystemEvent):
        """文件创建事件"""
        if event.is_directory:
            return
        
        file_path = event.src_path
        if self._is_readme_file(file_path):
            self._schedule_sync(file_path, 'created')
    
    def on_deleted(self, event: FileSystemEvent):
        """文件删除事件"""
        if event.is_directory:
            return
        
        file_path = event.src_path
        if self._is_readme_file(file_path):
            self._schedule_sync(file_path, 'deleted')
    
    def on_moved(self, event: FileSystemEvent):
        """文件移动事件"""
        if event.is_directory:
            return
        
        # 处理移动事件
        if hasattr(event, 'dest_path'):
            old_path = event.src_path
            new_path = event.dest_path
            
            if self._is_readme_file(old_path) or self._is_readme_file(new_path):
                self._schedule_sync(old_path, 'moved_from')
                self._schedule_sync(new_path, 'moved_to')
    
    def _is_readme_file(self, file_path: str) -> bool:
        """判断是否为README文件"""
        filename = os.path.basename(file_path).lower()
        return filename.startswith('readme') and filename.endswith('.md')
    
    def _schedule_sync(self, file_path: str, event_type: str):
        """调度同步任务（防抖）"""
        with self.lock:
            current_time = time.time()
            self.pending_events[file_path] = {
                'event_type': event_type,
                'timestamp': current_time,
                'is_target': self.is_target_folder
            }
    
    def _debounce_worker(self):
        """防抖处理工作线程"""
        while True:
            current_time = time.time()
            to_process = []
            
            with self.lock:
                for file_path, event_info in list(self.pending_events.items()):
                    if current_time - event_info['timestamp'] >= self.debounce_time:
                        to_process.append((file_path, event_info))
                        del self.pending_events[file_path]
            
            # 处理待同步事件
            for file_path, event_info in to_process:
                self._process_file_change(file_path, event_info)
            
            time.sleep(0.5)  # 检查间隔
    
    def _process_file_change(self, file_path: str, event_info: Dict):
        """处理文件变化"""
        try:
            event_type = event_info['event_type']
            is_target = event_info['is_target']
            
            print(f"[实时同步] 检测到文件变化: {file_path} ({event_type})")
            
            if event_type == 'deleted':
                # 处理删除事件
                if is_target:
                    # 目标文件被删除，从源文件恢复
                    self._handle_target_deleted(file_path)
                else:
                    # 源文件被删除，删除对应的目标文件
                    self._handle_source_deleted(file_path)
            
            elif event_type in ['modified', 'created', 'moved_to']:
                # 处理修改/创建/移动事件
                if is_target:
                    # 目标文件变化，反向同步
                    self._handle_target_changed(file_path)
                else:
                    # 源文件变化，正向同步
                    self._handle_source_changed(file_path)
            
        except Exception as e:
            print(f"[实时同步] 处理文件变化失败 {file_path}: {e}")
    
    def _handle_source_changed(self, source_path: str):
        """处理源文件变化"""
        if not os.path.exists(source_path):
            return
        
        # 生成文件信息
        project_name = self.sync_engine.scanner.extract_project_name(source_path)
        target_filename = self.sync_engine.scanner.generate_target_filename(project_name)
        
        file_info = {
            'source_path': source_path,
            'project_name': project_name,
            'target_filename': target_filename
        }
        
        # 执行同步
        result = self.sync_engine.sync_single_file(file_info)
        print(f"[实时同步] 源文件同步结果: {result}")
    
    def _handle_target_changed(self, target_path: str):
        """处理目标文件变化"""
        if not os.path.exists(target_path):
            return
        
        # 查找对应的源文件映射
        mapping = self.sync_engine.db.find_mapping_by_target(target_path)
        if not mapping:
            print(f"[实时同步] 未找到目标文件映射: {target_path}")
            return
        
        source_path = mapping['source_path']
        if not os.path.exists(source_path):
            print(f"[实时同步] 源文件不存在: {source_path}")
            return
        
        # 检查是否需要反向同步
        try:
            target_mtime = os.path.getmtime(target_path)
            source_mtime = os.path.getmtime(source_path)
            
            if target_mtime > source_mtime:
                # 目标文件更新，反向同步
                import shutil
                shutil.copy2(target_path, source_path)
                print(f"[实时同步] 反向同步: {target_path} -> {source_path}")
                
                # 更新数据库
                source_hash = self.sync_engine.db.get_file_hash(source_path)
                target_hash = self.sync_engine.db.get_file_hash(target_path)
                self.sync_engine.db.update_sync_time(source_path, source_hash, target_hash, 
                                                   source_mtime, target_mtime)
        except Exception as e:
            print(f"[实时同步] 反向同步失败: {e}")
    
    def _handle_source_deleted(self, source_path: str):
        """处理源文件删除"""
        # 查找对应的目标文件
        mapping = self.sync_engine.db.get_file_mapping(source_path)
        if mapping:
            target_path = mapping['target_path']
            if os.path.exists(target_path):
                try:
                    os.remove(target_path)
                    print(f"[实时同步] 删除目标文件: {target_path}")
                except Exception as e:
                    print(f"[实时同步] 删除目标文件失败: {e}")
            
            # 删除数据库映射
            self.sync_engine.db.remove_mapping(source_path)
    
    def _handle_target_deleted(self, target_path: str):
        """处理目标文件删除"""
        # 查找对应的源文件映射
        mapping = self.sync_engine.db.find_mapping_by_target(target_path)
        if mapping:
            source_path = mapping['source_path']
            if os.path.exists(source_path):
                try:
                    # 从源文件恢复目标文件
                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                    import shutil
                    shutil.copy2(source_path, target_path)
                    print(f"[实时同步] 恢复目标文件: {source_path} -> {target_path}")
                except Exception as e:
                    print(f"[实时同步] 恢复目标文件失败: {e}")


class RealtimeSyncManager:
    """实时同步管理器"""
    
    def __init__(self, config_path: str = None):
        """初始化实时同步管理器"""
        self.config = ConfigManager(config_path)
        self.db = DatabaseManager()
        self.sync_engine = SyncEngine(self.config, self.db)
        self.observer = Observer()
        self.is_running = False
        
    def start(self):
        """启动实时同步"""
        if self.is_running:
            print("[实时同步] 已在运行中")
            return
        
        # 验证配置
        errors = self.config.validate_config()
        if errors:
            print("[实时同步] 配置验证失败:")
            for error in errors:
                print(f"  ✗ {error}")
            return
        
        # 添加源文件夹监控
        source_folders = self.config.get_enabled_source_folders()
        for folder in source_folders:
            if os.path.exists(folder):
                handler = ReadmeFileHandler(self.sync_engine, self.config, folder, False)
                self.observer.schedule(handler, folder, recursive=True)
                print(f"[实时同步] 监控源文件夹: {folder}")
        
        # 添加目标文件夹监控
        target_folder = self.config.get_target_folder()
        if target_folder and os.path.exists(target_folder):
            handler = ReadmeFileHandler(self.sync_engine, self.config, None, True)
            self.observer.schedule(handler, target_folder, recursive=True)
            print(f"[实时同步] 监控目标文件夹: {target_folder}")
        
        # 启动监控
        self.observer.start()
        self.is_running = True
        print("[实时同步] 实时同步已启动")
        
        # 执行一次初始同步
        self._initial_sync()
    
    def stop(self):
        """停止实时同步"""
        if not self.is_running:
            return
        
        self.observer.stop()
        self.observer.join()
        self.is_running = False
        print("[实时同步] 实时同步已停止")
    
    def _initial_sync(self):
        """执行初始同步"""
        try:
            print("[实时同步] 执行初始同步...")
            results = self.sync_engine.sync_all()
            print(f"[实时同步] 初始同步完成: 扫描 {results['scanned']}, 同步 {results['synced']}")
        except Exception as e:
            print(f"[实时同步] 初始同步失败: {e}")
    
    def get_status(self) -> Dict:
        """获取实时同步状态"""
        return {
            'running': self.is_running,
            'source_folders': self.config.get_enabled_source_folders(),
            'target_folder': self.config.get_target_folder(),
            'observer_threads': len(self.observer.emitters) if self.observer else 0
        }
    
    def run_forever(self):
        """持续运行（用于守护进程）"""
        self.start()
        
        if not self.is_running:
            return
        
        try:
            while self.is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[实时同步] 收到中断信号，正在停止...")
            self.stop()
        except Exception as e:
            print(f"[实时同步] 运行时错误: {e}")
            self.stop()