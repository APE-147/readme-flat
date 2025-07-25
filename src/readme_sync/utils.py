# -*- coding: utf-8 -*-
"""工具函数模块"""

import os
import hashlib
import time
from pathlib import Path
from typing import Optional, Dict, Any


def calculate_file_hash(file_path: str, algorithm: str = 'md5') -> str:
    """计算文件哈希值"""
    try:
        hash_obj = hashlib.new(algorithm)
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_obj.update(chunk)
        return hash_obj.hexdigest()
    except Exception:
        return ""


def get_file_info(file_path: str) -> Dict[str, Any]:
    """获取文件信息"""
    if not os.path.exists(file_path):
        return {}
    
    stat = os.stat(file_path)
    return {
        'size': stat.st_size,
        'mtime': stat.st_mtime,
        'ctime': stat.st_ctime,
        'mode': stat.st_mode,
        'exists': True
    }


def ensure_directory(dir_path: str) -> bool:
    """确保目录存在"""
    try:
        os.makedirs(dir_path, exist_ok=True)
        return True
    except Exception:
        return False


def is_newer_file(file1: str, file2: str, tolerance: int = 0) -> Optional[bool]:
    """比较两个文件的修改时间
    
    Returns:
        True: file1更新
        False: file2更新
        None: 无法比较或时间相同
    """
    if not os.path.exists(file1) or not os.path.exists(file2):
        return None
    
    mtime1 = os.path.getmtime(file1)
    mtime2 = os.path.getmtime(file2)
    
    diff = abs(mtime1 - mtime2)
    if diff <= tolerance:
        return None  # 时间相同
    
    return mtime1 > mtime2


def format_timestamp(timestamp: float) -> str:
    """格式化时间戳"""
    if timestamp <= 0:
        return "未知"
    
    try:
        from datetime import datetime
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return "格式错误"


def format_file_size(size_bytes: int) -> str:
    """格式化文件大小"""
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    size = float(size_bytes)
    
    while size >= 1024.0 and i < len(size_names) - 1:
        size /= 1024.0
        i += 1
    
    return f"{size:.1f} {size_names[i]}"


def safe_copy_file(src: str, dst: str, preserve_metadata: bool = True) -> bool:
    """安全复制文件"""
    try:
        import shutil
        
        # 确保目标目录存在
        dst_dir = os.path.dirname(dst)
        ensure_directory(dst_dir)
        
        # 复制文件
        if preserve_metadata:
            shutil.copy2(src, dst)
        else:
            shutil.copy(src, dst)
        
        return True
    except Exception as e:
        print(f"复制文件失败 {src} -> {dst}: {e}")
        return False


def safe_move_file(src: str, dst: str) -> bool:
    """安全移动文件"""
    try:
        import shutil
        
        # 确保目标目录存在
        dst_dir = os.path.dirname(dst)
        ensure_directory(dst_dir)
        
        # 移动文件
        shutil.move(src, dst)
        return True
    except Exception as e:
        print(f"移动文件失败 {src} -> {dst}: {e}")
        return False


def validate_file_path(file_path: str) -> bool:
    """验证文件路径有效性"""
    try:
        path = Path(file_path)
        # 检查路径是否包含非法字符
        str(path.resolve())
        return True
    except Exception:
        return False


def clean_filename(filename: str) -> str:
    """清理文件名中的非法字符"""
    import re
    
    # 移除非法字符
    cleaned = re.sub(r'[<>:"/\\|?*]', '-', filename)
    # 移除首尾空格和点
    cleaned = cleaned.strip(' .')
    # 长度限制
    if len(cleaned) > 255:
        name, ext = os.path.splitext(cleaned)
        max_name_len = 255 - len(ext)
        cleaned = name[:max_name_len] + ext
    
    return cleaned or 'untitled'


def get_relative_path(file_path: str, base_path: str) -> str:
    """获取相对路径"""
    try:
        return os.path.relpath(file_path, base_path)
    except Exception:
        return file_path


def expand_path(path: str) -> str:
    """展开用户路径和环境变量"""
    return os.path.expandvars(os.path.expanduser(path))


def is_hidden_file(file_path: str) -> bool:
    """判断文件是否为隐藏文件"""
    filename = os.path.basename(file_path)
    return filename.startswith('.')


def get_project_root(file_path: str, indicators: list = None) -> Optional[str]:
    """查找项目根目录
    
    Args:
        file_path: 文件路径
        indicators: 项目根目录标识符列表
    """
    if indicators is None:
        indicators = ['.git', '.svn', '.hg', 'package.json', 'setup.py', 'Cargo.toml', 'go.mod']
    
    current_path = Path(file_path).parent
    
    while current_path != current_path.parent:
        for indicator in indicators:
            if (current_path / indicator).exists():
                return str(current_path)
        current_path = current_path.parent
    
    return None


def retry_operation(func, max_retries: int = 3, delay: float = 1.0):
    """重试操作"""
    import time
    
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            time.sleep(delay)
    
    return None


def create_backup(file_path: str, suffix: str = '.bak') -> Optional[str]:
    """创建备份文件"""
    if not os.path.exists(file_path):
        return None
    
    backup_path = file_path + suffix
    counter = 1
    
    # 如果备份文件已存在，添加数字后缀
    while os.path.exists(backup_path):
        backup_path = f"{file_path}{suffix}.{counter}"
        counter += 1
    
    try:
        import shutil
        shutil.copy2(file_path, backup_path)
        return backup_path
    except Exception:
        return None