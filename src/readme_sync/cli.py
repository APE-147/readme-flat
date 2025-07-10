# -*- coding: utf-8 -*-
"""命令行界面模块"""

import click
import os
import time
from datetime import datetime
from pathlib import Path
from .config import ConfigManager
from .database import DatabaseManager
from .sync_engine import SyncEngine
from .scanner import FileScanner
from .watcher import RealtimeSyncManager
from .daemon import DaemonManager, format_uptime, format_memory
from .autostart import get_platform_manager


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """README同步管理器 - 集中管理所有项目的README.md文件"""
    pass


@cli.command()
def init():
    """初始化配置文件"""
    config = ConfigManager()
    click.echo("初始化配置文件...")
    
    # 检查文件是否已初始化
    if config.config_path.exists():
        if not click.confirm(f"配置文件已存在于 {config.config_path}，是否重新初始化？"):
            return
    
    # 创建默认配置
    default_config = config.get_default_config()
    
    # 交互式配置
    click.echo("\n请输入配置信息:")
    
    # 设置目标文件夹
    target_folder = click.prompt(
        "目标文件夹路径",
        default="~/Documents/README-Sync",
        type=str
    )
    
    if target_folder:
        expanded_target = os.path.expanduser(target_folder)
        try:
            os.makedirs(expanded_target, exist_ok=True)
            config.set_target_folder(target_folder)
            click.echo(f"✓ 目标文件夹已设置: {expanded_target}")
        except Exception as e:
            click.echo(f"✗ 创建目标文件夹失败: {e}")
            return
    
    # 添加源文件夹
    while True:
        source_folder = click.prompt(
            "源文件夹路径 (留空结束)",
            default="",
            type=str,
            show_default=False
        )
        
        if not source_folder:
            break
        
        if config.add_source_folder(source_folder):
            click.echo(f"✓ 已添加源文件夹: {os.path.expanduser(source_folder)}")
        else:
            click.echo(f"✗ 添加源文件夹失败")
    
    click.echo(f"\n✓ 初始化完成！配置文件已保存至: {config.config_path}")
    click.echo("使用 'readme-sync config list' 查看配置")
    click.echo("使用 'readme-sync add-source <path>' 添加更多源文件夹")


@cli.command()
@click.argument('folder_path')
def add_source(folder_path):
    """添加源文件夹"""
    config = ConfigManager()
    
    if config.add_source_folder(folder_path):
        click.echo(f"✓ 已添加源文件夹: {os.path.expanduser(folder_path)}")
    else:
        click.echo(f"✗ 添加源文件夹失败: {folder_path}")


@cli.command()
@click.argument('folder_path')
def remove_source(folder_path):
    """移除源文件夹"""
    config = ConfigManager()
    
    if config.remove_source_folder(folder_path):
        click.echo(f"✓ 已移除源文件夹: {folder_path}")
    else:
        click.echo(f"✗ 移除源文件夹失败: {folder_path}")


@cli.command()
@click.argument('folder_path')
def set_target(folder_path):
    """设置目标文件夹"""
    config = ConfigManager()
    
    if config.set_target_folder(folder_path):
        click.echo(f"✓ 目标文件夹已设置: {os.path.expanduser(folder_path)}")
    else:
        click.echo(f"✗ 设置目标文件夹失败: {folder_path}")


@cli.command()
@click.option('--reverse', is_flag=True, help='从目标同步到源文件夹')
def sync(reverse):
    """执行同步操作"""
    config = ConfigManager()
    db = DatabaseManager()
    engine = SyncEngine(config, db)
    
    # 验证配置
    errors = config.validate_config()
    if errors:
        click.echo("配置验证失败:")
        for error in errors:
            click.echo(f"  ✗ {error}")
        click.echo("请使用 'readme-sync config' 检查配置")
        return
    
    # 执行同步
    try:
        if reverse:
            results = engine.reverse_sync_from_target()
            click.echo(f"\n反向同步完成:")
        else:
            results = engine.sync_all()
            click.echo(f"\n同步完成:")
        
        for key, value in results.items():
            if value > 0:
                click.echo(f"  {key}: {value}")
    
    except Exception as e:
        click.echo(f"✗ 同步失败: {e}")


@cli.command()
@click.option('--interval', default=300, help='监控间隔时间（秒）')
@click.option('--daemon', is_flag=True, help='后台运行模式')
def watch(interval, daemon):
    """文件监控模式"""
    config = ConfigManager()
    db = DatabaseManager()
    engine = SyncEngine(config, db)
    
    # 验证配置
    errors = config.validate_config()
    if errors:
        click.echo("配置验证失败:")
        for error in errors:
            click.echo(f"  ✗ {error}")
        return
    
    click.echo(f"文件监控模式启动 (间隔: {interval}秒)")
    click.echo("按 Ctrl+C 停止监控")
    
    try:
        while True:
            try:
                click.echo(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 检查更新...")
                results = engine.sync_all()
                
                if any(results.values()):
                    click.echo("发现更新:")
                    for key, value in results.items():
                        if value > 0:
                            click.echo(f"  {key}: {value}")
                else:
                    click.echo("无更新")
                
                time.sleep(interval)
            
            except KeyboardInterrupt:
                click.echo("\n监控已停止")
                break
            except Exception as e:
                click.echo(f"监控过程中发生错误: {e}")
                time.sleep(interval)
    
    except Exception as e:
        click.echo(f"文件监控失败: {e}")


@cli.command()
def status():
    """查看同步状态"""
    config = ConfigManager()
    db = DatabaseManager()
    engine = SyncEngine(config, db)
    
    click.echo("README同步管理器状态:")
    click.echo("=" * 40)
    
    # 配置信息
    target_folder = config.get_target_folder()
    source_folders = config.get_enabled_source_folders()
    
    click.echo(f"目标文件夹: {target_folder or '未设置'}")
    click.echo(f"源文件夹数量: {len(source_folders)}")
    
    if source_folders:
        for folder in source_folders:
            exists = "✓" if os.path.exists(folder) else "✗"
            click.echo(f"  {exists} {folder}")
    
    # 同步状态
    try:
        status_info = engine.get_sync_status()
        click.echo(f"\n同步状态:")
        click.echo(f"  映射总数: {status_info['total_mappings']}")
        click.echo(f"  源文件数: {status_info['source_files']}")
        click.echo(f"  目标文件数: {status_info['target_files']}")
        click.echo(f"  过期文件数: {status_info['outdated_files']}")
        click.echo(f"  缺失源文件: {status_info['missing_source']}")
        click.echo(f"  缺失目标文件: {status_info['missing_target']}")
        
        if status_info['last_sync'] > 0:
            last_sync = datetime.fromtimestamp(status_info['last_sync'])
            click.echo(f"  上次同步: {last_sync.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            click.echo(f"  上次同步: 从未同步")
    
    except Exception as e:
        click.echo(f"获取状态失败: {e}")


@cli.group()
def config():
    """配置管理"""
    pass


@config.command('list')
def config_list():
    """显示当前配置"""
    config = ConfigManager()
    config.print_config()


@config.command('set')
@click.argument('key')
@click.argument('value')
def config_set(key, value):
    """设置配置项"""
    config = ConfigManager()
    
    if config.set(key, value):
        click.echo(f"✓ 配置已更新: {key} = {value}")
    else:
        click.echo(f"✗ 设置配置项失败")


@config.command('get')
@click.argument('key')
def config_get(key):
    """获取配置项"""
    config = ConfigManager()
    value = config.get(key)
    
    if value is not None:
        click.echo(f"{key} = {value}")
    else:
        click.echo(f"配置项不存在: {key}")


@cli.command()
def scan():
    """扫描并显示README文件"""
    config = ConfigManager()
    scanner = FileScanner(config)
    
    click.echo("扫描README文件...")
    
    # 扫描所有文件
    readme_files = scanner.scan_all_sources()
    
    if not readme_files:
        click.echo("未找到任何README文件")
        return
    
    click.echo(f"找到 {len(readme_files)} 个README文件:")
    click.echo("=" * 60)
    
    for file_info in readme_files:
        click.echo(f"项目: {file_info['project_name']}")
        click.echo(f"源文件: {file_info['source_path']}")
        click.echo(f"目标文件名: {file_info['target_filename']}")
        click.echo("-" * 40)


@cli.command()
def cleanup():
    """清理数据库中的孤立映射"""
    db = DatabaseManager()
    
    click.echo("清理数据库中的孤立映射...")
    orphaned_count = db.cleanup_orphaned_mappings()
    
    if orphaned_count > 0:
        click.echo(f"✓ 清理了 {orphaned_count} 个孤立映射")
    else:
        click.echo("没有发现孤立映射")


@cli.group()
def daemon():
    """守护进程管理"""
    pass


@daemon.command('start')
@click.option('--foreground', '-f', is_flag=True, help='前台运行（用于调试）')
def daemon_start(foreground):
    """启动守护进程"""
    daemon_mgr = DaemonManager()
    
    if daemon_mgr.is_running():
        click.echo("守护进程已在运行")
        return
    
    click.echo("启动守护进程...")
    
    if daemon_mgr.start(detach=not foreground):
        if foreground:
            click.echo("守护进程已在前台启动")
        else:
            click.echo("守护进程已在后台启动")
    else:
        click.echo("启动守护进程失败")


@daemon.command('stop')
def daemon_stop():
    """停止守护进程"""
    daemon_mgr = DaemonManager()
    
    if not daemon_mgr.is_running():
        click.echo("守护进程未运行")
        return
    
    click.echo("停止守护进程...")
    
    if daemon_mgr.stop():
        click.echo("守护进程已停止")
    else:
        click.echo("停止守护进程失败")


@daemon.command('restart')
def daemon_restart():
    """重启守护进程"""
    daemon_mgr = DaemonManager()
    
    click.echo("重启守护进程...")
    
    if daemon_mgr.restart():
        click.echo("守护进程已重启")
    else:
        click.echo("重启守护进程失败")


@daemon.command('status')
def daemon_status():
    """查看守护进程状态"""
    daemon_mgr = DaemonManager()
    status = daemon_mgr.status()
    
    click.echo("守护进程状态:")
    click.echo("=" * 40)
    
    if status['running']:
        click.echo("状态: 运行中 ✓")
        click.echo(f"PID: {status['pid']}")
        click.echo(f"运行时间: {format_uptime(status['uptime'])}")
        click.echo(f"内存使用: {format_memory(status['memory_usage'])}")
        click.echo(f"CPU使用: {status['cpu_usage']:.1f}%")
        
        start_time = datetime.fromtimestamp(status['start_time'])
        click.echo(f"启动时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        click.echo("状态: 未运行 ✗")


@daemon.command('logs')
@click.option('--lines', '-n', default=50, help='显示日志行数')
@click.option('--follow', '-f', is_flag=True, help='持续显示日志')
def daemon_logs(lines, follow):
    """查看守护进程日志"""
    daemon_mgr = DaemonManager()
    
    if follow:
        click.echo("持续显示日志 (Ctrl+C 退出)...")
        try:
            import subprocess
            subprocess.run([
                'tail', '-f', str(daemon_mgr.log_file)
            ])
        except KeyboardInterrupt:
            click.echo("\n停止显示日志")
        except FileNotFoundError:
            click.echo("日志文件不存在")
        except Exception as e:
            click.echo(f"显示日志失败: {e}")
    else:
        logs = daemon_mgr.get_logs(lines)
        click.echo(logs)


@daemon.command('clear-logs')
def daemon_clear_logs():
    """清理守护进程日志"""
    daemon_mgr = DaemonManager()
    
    if click.confirm("确定要清理所有日志吗？"):
        daemon_mgr.clear_logs()


@cli.group()
def realtime():
    """实时同步管理"""
    pass


@realtime.command('start')
def realtime_start():
    """启动实时同步（前台运行）"""
    sync_mgr = RealtimeSyncManager()
    
    click.echo("启动实时同步...")
    click.echo("按 Ctrl+C 停止")
    
    try:
        sync_mgr.run_forever()
    except KeyboardInterrupt:
        click.echo("\n停止实时同步")
        sync_mgr.stop()


@realtime.command('status')
def realtime_status():
    """查看实时同步状态"""
    sync_mgr = RealtimeSyncManager()
    status = sync_mgr.get_status()
    
    click.echo("实时同步状态:")
    click.echo("=" * 40)
    click.echo(f"运行中: {'是' if status['running'] else '否'}")
    click.echo(f"监控源文件夹: {len(status['source_folders'])}")
    click.echo(f"目标文件夹: {status['target_folder']}")
    click.echo(f"监控线程数: {status['observer_threads']}")
    
    if status['source_folders']:
        click.echo("\n源文件夹列表:")
        for folder in status['source_folders']:
            exists = "✓" if os.path.exists(folder) else "✗"
            click.echo(f"  {exists} {folder}")


@cli.group()
def autostart():
    """开机自启动管理"""
    pass


@autostart.command('install')
def autostart_install():
    """安装开机自启动"""
    manager = get_platform_manager()
    
    if not manager:
        click.echo("当前平台不支持自动配置开机自启动")
        return
    
    click.echo("安装开机自启动...")
    
    if manager.install_autostart():
        click.echo("✓ 开机自启动已安装")
        click.echo("重启后将自动启动README同步守护进程")
    else:
        click.echo("✗ 安装开机自启动失败")


@autostart.command('uninstall')
def autostart_uninstall():
    """卸载开机自启动"""
    manager = get_platform_manager()
    
    if not manager:
        click.echo("当前平台不支持自动配置开机自启动")
        return
    
    if not manager.is_installed():
        click.echo("开机自启动未安装")
        return
    
    click.echo("卸载开机自启动...")
    
    if manager.uninstall_autostart():
        click.echo("✓ 开机自启动已卸载")
    else:
        click.echo("✗ 卸载开机自启动失败")


@autostart.command('status')
def autostart_status():
    """查看开机自启动状态"""
    manager = get_platform_manager()
    
    if not manager:
        click.echo("当前平台不支持自动配置开机自启动")
        return
    
    status = manager.get_status()
    
    click.echo("开机自启动状态:")
    click.echo("=" * 40)
    click.echo(f"已安装: {'是' if status['installed'] else '否'}")
    
    if status['installed']:
        click.echo(f"已加载: {'是' if status.get('loaded', False) else '否'}")
        click.echo(f"运行中: {'是' if status.get('running', False) else '否'}")
        
        if 'plist_file' in status:
            click.echo(f"配置文件: {status['plist_file']}")
        
        if 'error' in status:
            click.echo(f"错误: {status['error']}")


@autostart.command('restart')
def autostart_restart():
    """重启开机自启动服务"""
    manager = get_platform_manager()
    
    if not manager:
        click.echo("当前平台不支持自动配置开机自启动")
        return
    
    if not manager.is_installed():
        click.echo("开机自启动未安装")
        return
    
    click.echo("重启开机自启动服务...")
    
    if manager.restart_service():
        click.echo("✓ 开机自启动服务已重启")
    else:
        click.echo("✗ 重启开机自启动服务失败")


if __name__ == '__main__':
    cli()