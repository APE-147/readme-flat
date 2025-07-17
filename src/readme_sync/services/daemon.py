# -*- coding: utf-8 -*-
"""守护进程模块 - 实现后台服务管理"""

import os
import sys
import time
import signal
import atexit
import psutil
from pathlib import Path
from typing import Optional
from .watcher import RealtimeSyncManager


class DaemonManager:
    """守护进程管理器"""
    
    def __init__(self, config_path: str = None):
        """初始化守护进程管理器"""
        self.config_path = config_path
        
        # 守护进程相关文件路径
        project_data_dir = os.getenv('PROJECT_DATA_DIR')
        if project_data_dir:
            self.daemon_dir = Path(project_data_dir)
        else:
            # 使用默认的新数据目录结构
            self.daemon_dir = Path.home() / "Developer" / "Code" / "Data" / "srv" / "readme_flat"
        self.daemon_dir.mkdir(parents=True, exist_ok=True)
        
        self.pid_file = self.daemon_dir / "daemon.pid"
        self.log_file = self.daemon_dir / "daemon.log"
        self.status_file = self.daemon_dir / "daemon.status"
        
        # 实时同步管理器
        self.sync_manager = None
    
    def start(self, detach: bool = True) -> bool:
        """启动守护进程"""
        # 检查是否已经在运行
        if self.is_running():
            print("守护进程已在运行")
            return False
        
        if detach:
            # 后台运行
            self._daemonize()
        else:
            # 前台运行（用于调试）
            self._run_daemon()
        
        return True
    
    def stop(self) -> bool:
        """停止守护进程"""
        pid = self._get_daemon_pid()
        if not pid:
            print("守护进程未运行")
            return False
        
        try:
            # 发送终止信号
            os.kill(pid, signal.SIGTERM)
            
            # 等待进程结束
            for _ in range(10):  # 最多等待10秒
                if not self._is_pid_running(pid):
                    break
                time.sleep(1)
            
            # 如果进程仍在运行，强制终止
            if self._is_pid_running(pid):
                os.kill(pid, signal.SIGKILL)
                time.sleep(1)
            
            # 清理文件
            self._cleanup_files()
            
            print(f"守护进程已停止 (PID: {pid})")
            return True
            
        except ProcessLookupError:
            # 进程不存在
            self._cleanup_files()
            print("守护进程已停止")
            return True
        except Exception as e:
            print(f"停止守护进程失败: {e}")
            return False
    
    def restart(self) -> bool:
        """重启守护进程"""
        self.stop()
        time.sleep(2)
        return self.start()
    
    def status(self) -> dict:
        """获取守护进程状态"""
        pid = self._get_daemon_pid()
        
        if not pid:
            return {
                'running': False,
                'pid': None,
                'uptime': None,
                'memory_usage': None,
                'cpu_usage': None
            }
        
        try:
            process = psutil.Process(pid)
            
            # 获取进程信息
            create_time = process.create_time()
            uptime = time.time() - create_time
            memory_info = process.memory_info()
            cpu_percent = process.cpu_percent()
            
            return {
                'running': True,
                'pid': pid,
                'uptime': uptime,
                'memory_usage': memory_info.rss,  # 内存使用量（字节）
                'cpu_usage': cpu_percent,
                'start_time': create_time
            }
            
        except psutil.NoSuchProcess:
            # 进程不存在，清理文件
            self._cleanup_files()
            return {
                'running': False,
                'pid': None,
                'uptime': None,
                'memory_usage': None,
                'cpu_usage': None
            }
    
    def is_running(self) -> bool:
        """检查守护进程是否在运行"""
        pid = self._get_daemon_pid()
        return pid is not None and self._is_pid_running(pid)
    
    def _daemonize(self):
        """创建守护进程"""
        try:
            # 第一次fork
            pid = os.fork()
            if pid > 0:
                # 父进程退出
                sys.exit(0)
        except OSError as e:
            print(f"第一次fork失败: {e}")
            sys.exit(1)
        
        # 脱离控制终端
        os.chdir("/")
        os.setsid()
        os.umask(0)
        
        try:
            # 第二次fork
            pid = os.fork()
            if pid > 0:
                # 父进程退出
                sys.exit(0)
        except OSError as e:
            print(f"第二次fork失败: {e}")
            sys.exit(1)
        
        # 重定向标准输入输出
        self._redirect_streams()
        
        # 运行守护进程
        self._run_daemon()
    
    def _redirect_streams(self):
        """重定向标准输入输出到日志文件"""
        # 刷新输出缓冲区
        sys.stdout.flush()
        sys.stderr.flush()
        
        # 重定向到日志文件
        with open(self.log_file, 'a') as f:
            os.dup2(f.fileno(), sys.stdout.fileno())
            os.dup2(f.fileno(), sys.stderr.fileno())
        
        # 重定向标准输入到/dev/null
        with open(os.devnull, 'r') as f:
            os.dup2(f.fileno(), sys.stdin.fileno())
    
    def _run_daemon(self):
        """运行守护进程主逻辑"""
        # 记录PID
        with open(self.pid_file, 'w') as f:
            f.write(str(os.getpid()))
        
        # 注册清理函数
        atexit.register(self._cleanup_files)
        
        # 设置信号处理
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
        # 记录启动时间
        start_time = time.time()
        print(f"[守护进程] 启动时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_time))}")
        
        try:
            # 创建并启动实时同步管理器
            self.sync_manager = RealtimeSyncManager(self.config_path)
            
            # 写入状态文件
            self._write_status("starting")
            
            # 启动实时同步
            self.sync_manager.start()
            
            if self.sync_manager.is_running:
                print("[守护进程] 实时同步已启动")
                self._write_status("running")
                
                # 持续运行
                self.sync_manager.run_forever()
            else:
                print("[守护进程] 实时同步启动失败")
                self._write_status("failed")
                
        except Exception as e:
            print(f"[守护进程] 运行时错误: {e}")
            self._write_status("error")
        finally:
            # 清理资源
            if self.sync_manager:
                self.sync_manager.stop()
            self._cleanup_files()
    
    def _signal_handler(self, signum, frame):
        """信号处理函数"""
        print(f"[守护进程] 收到信号 {signum}，正在停止...")
        
        if self.sync_manager:
            self.sync_manager.stop()
        
        self._cleanup_files()
        sys.exit(0)
    
    def _get_daemon_pid(self) -> Optional[int]:
        """获取守护进程PID"""
        try:
            if self.pid_file.exists():
                with open(self.pid_file, 'r') as f:
                    pid = int(f.read().strip())
                    return pid if self._is_pid_running(pid) else None
        except (ValueError, FileNotFoundError):
            pass
        return None
    
    def _is_pid_running(self, pid: int) -> bool:
        """检查指定PID的进程是否在运行"""
        try:
            # 发送0信号检查进程是否存在
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
    
    def _cleanup_files(self):
        """清理守护进程相关文件"""
        try:
            if self.pid_file.exists():
                self.pid_file.unlink()
            if self.status_file.exists():
                self.status_file.unlink()
        except Exception as e:
            print(f"清理文件失败: {e}")
    
    def _write_status(self, status: str):
        """写入状态文件"""
        try:
            with open(self.status_file, 'w') as f:
                f.write(f"{status}\\n{time.time()}\\n")
        except Exception as e:
            print(f"写入状态文件失败: {e}")
    
    def get_logs(self, lines: int = 50) -> str:
        """获取守护进程日志"""
        try:
            if not self.log_file.exists():
                return "日志文件不存在"
            
            with open(self.log_file, 'r') as f:
                all_lines = f.readlines()
                return ''.join(all_lines[-lines:])
        except Exception as e:
            return f"读取日志失败: {e}"
    
    def clear_logs(self):
        """清理日志文件"""
        try:
            if self.log_file.exists():
                self.log_file.unlink()
            print("日志文件已清理")
        except Exception as e:
            print(f"清理日志文件失败: {e}")


def format_uptime(seconds: float) -> str:
    """格式化运行时间"""
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    
    parts = []
    if days > 0:
        parts.append(f"{days}天")
    if hours > 0:
        parts.append(f"{hours}小时")
    if minutes > 0:
        parts.append(f"{minutes}分钟")
    if seconds > 0 or not parts:
        parts.append(f"{seconds}秒")
    
    return " ".join(parts)


def format_memory(bytes_value: int) -> str:
    """格式化内存使用量"""
    if bytes_value < 1024:
        return f"{bytes_value}B"
    elif bytes_value < 1024 * 1024:
        return f"{bytes_value / 1024:.1f}KB"
    elif bytes_value < 1024 * 1024 * 1024:
        return f"{bytes_value / (1024 * 1024):.1f}MB"
    else:
        return f"{bytes_value / (1024 * 1024 * 1024):.1f}GB"