# -*- coding: utf-8 -*-
"""文件扫描模块"""

import os
import re
from pathlib import Path
from typing import List, Dict, Optional
from ..services.config import ConfigManager


class FileScanner:
    """README文件扫描器"""
    
    def __init__(self, config_manager: ConfigManager):
        """初始化扫描器"""
        self.config = config_manager
    
    def extract_project_name(self, readme_path: str) -> str:
        """从README文件路径提取项目名"""
        path = Path(readme_path)
        parent_dir = path.parent.name
        
        # 跳过常见的代码目录名，如src/docs等目录，但保留有意义的目录名
        # 只有当目录名是明显的代码结构目录时才向上查找
        common_code_dirs = {'src', 'docs', 'doc', 'documentation', 'scripts'}
        
        # 特殊处理：如果父目录名是有意义的项目分类（如Script、Crawler等），
        # 即使它可能在常见目录名中，也应该保留
        if parent_dir.lower() in common_code_dirs:
            # 检查是否是项目分类目录（通常这些目录下会有多个子项目）
            grandparent_path = path.parent.parent
            if grandparent_path.exists():
                # 检查同级目录是否有其他项目目录
                sibling_dirs = [d for d in grandparent_path.iterdir() 
                               if d.is_dir() and d.name != parent_dir]
                if len(sibling_dirs) >= 1:  # 如果有其他同级目录，说明这是项目分类
                    # 保留当前目录名作为项目名
                    pass
                else:
                    # 使用上级目录名
                    grandparent = grandparent_path.name
                    if grandparent and grandparent != '.':
                        parent_dir = grandparent
        
        # 清理项目名
        project_name = self._clean_project_name(parent_dir)
        return project_name
    
    def _clean_project_name(self, name: str) -> str:
        """清理项目名中的非法字符"""
        # 移除项目名中的特殊字符，保留字母、数字、连字符
        cleaned = re.sub(r'[^a-zA-Z0-9\-_\u4e00-\u9fff]', '-', name)
        # 移除首尾连字符
        cleaned = cleaned.strip('-')
        # 合并多个连字符为单个
        cleaned = re.sub(r'-+', '-', cleaned)
        
        return cleaned or 'unknown-project'
    
    def generate_target_filename(self, project_name: str) -> str:
        """生成目标文件名"""
        pattern = self.config.get_naming_pattern()
        filename = pattern.format(project_name=project_name)
        
        # 处理大小写
        case_style = self.config.get("naming_rules.case_style", "keep")
        if case_style == "lower":
            filename = filename.lower()
        elif case_style == "upper":
            filename = filename.upper()
        
        # 确保有.md扩展名
        if not filename.lower().endswith('.md'):
            filename += '.md'
        
        return filename
    
    def find_readme_files(self, source_folder: str) -> List[Dict[str, str]]:
        """在指定文件夹中递归查找README文件"""
        readme_files = []
        source_path = Path(source_folder)
        
        if not source_path.exists():
            print(f"源文件夹不存在: {source_folder}")
            return readme_files
        
        # 递归查找README文件
        for root, dirs, files in os.walk(source_folder):
            # 检查当前路径是否被排除
            if self.config.is_excluded(root):
                continue
            
            # 过滤掉被排除的目录
            dirs[:] = [d for d in dirs if not self.config.is_excluded(os.path.join(root, d))]
            
            for file in files:
                # 检查是否为精确的README.md文件（大小写不敏感）
                if file.lower() == 'readme.md':
                    readme_path = os.path.join(root, file)
                    
                    # 检查路径是否被排除
                    if self.config.is_excluded(readme_path):
                        continue
                    
                    # 提取项目名
                    project_name = self.extract_project_name(readme_path)
                    
                    # 生成目标文件名
                    target_filename = self.generate_target_filename(project_name)
                    
                    readme_files.append({
                        'source_path': readme_path,
                        'project_name': project_name,
                        'target_filename': target_filename,
                        'relative_path': os.path.relpath(readme_path, source_folder)
                    })
        
        return readme_files
    
    def scan_all_sources(self) -> List[Dict[str, str]]:
        """扫描所有源文件夹"""
        all_readme_files = []
        source_folders = self.config.get_enabled_source_folders()
        
        for folder in source_folders:
            print(f"扫描文件夹: {folder}")
            readme_files = self.find_readme_files(folder)
            all_readme_files.extend(readme_files)
            print(f"找到 {len(readme_files)} 个README文件")
        
        # 去重（按源路径）
        unique_files = {}
        for file_info in all_readme_files:
            source_path = file_info['source_path']
            if source_path not in unique_files:
                unique_files[source_path] = file_info
        
        return list(unique_files.values())
    
    def scan_target_folder(self) -> List[Dict[str, str]]:
        """扫描目标文件夹中的所有Markdown文件"""
        target_files = []
        target_folder = self.config.get_target_folder()
        
        if not target_folder or not os.path.exists(target_folder):
            return target_files
        
        target_path = Path(target_folder)
        
        # 递归扫描目标文件夹
        for root, dirs, files in os.walk(target_folder):
            for file in files:
                if file.lower().endswith('.md'):
                    file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(file_path, target_folder)
                    
                    target_files.append({
                        'target_path': file_path,
                        'filename': file,
                        'relative_path': relative_path,
                        'subfolder': os.path.dirname(relative_path) if os.path.dirname(relative_path) != '.' else ''
                    })
        
        return target_files
    
    def detect_moved_files(self, db_manager) -> List[Dict[str, str]]:
        """检测被移动的目标文件"""
        moved_files = []
        target_files = self.scan_target_folder()
        
        for target_file in target_files:
            target_path = target_file['target_path']
            
            # 检查数据库中是否有对应映射
            mapping = db_manager.find_mapping_by_target(target_path)
            
            if not mapping:
                # 没有找到映射，通过哈希值查找
                file_hash = db_manager.get_file_hash(target_path)
                if file_hash:
                    hash_mapping = db_manager.find_mapping_by_hash(file_hash)
                    if hash_mapping and hash_mapping['target_path'] != target_path:
                        # 发现文件被移动
                        moved_files.append({
                            'old_target_path': hash_mapping['target_path'],
                            'new_target_path': target_path,
                            'source_path': hash_mapping['source_path'],
                            'project_name': hash_mapping['project_name']
                        })
        
        return moved_files
    
    def get_file_stats(self) -> Dict[str, int]:
        """获取文件统计信息"""
        readme_files = self.scan_all_sources()
        target_files = self.scan_target_folder()
        
        return {
            'source_files': len(readme_files),
            'target_files': len(target_files),
            'source_folders': len(self.config.get_enabled_source_folders())
        }
    
    def validate_paths(self) -> List[str]:
        """验证路径有效性"""
        errors = []
        
        # 检查源文件夹
        for folder in self.config.get_enabled_source_folders():
            if not os.path.exists(folder):
                errors.append(f"源文件夹不存在: {folder}")
            elif not os.access(folder, os.R_OK):
                errors.append(f"源文件夹无读取权限: {folder}")
        
        # 检查目标文件夹
        target_folder = self.config.get_target_folder()
        if target_folder:
            if not os.path.exists(target_folder):
                errors.append(f"目标文件夹不存在: {target_folder}")
            elif not os.access(target_folder, os.W_OK):
                errors.append(f"目标文件夹无写入权限: {target_folder}")
        
        return errors