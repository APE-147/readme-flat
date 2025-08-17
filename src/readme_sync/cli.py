# -*- coding: utf-8 -*-
"""命令行界面模块 - 基于Typer框架"""

import typer
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.progress import Progress

from .services.config import ConfigManager
from .services.database import DatabaseManager
from .core.sync_engine import SyncEngine
from .core.scanner import FileScanner
from .services.watcher import RealtimeSyncManager
from .services.daemon import DaemonManager, format_uptime, format_memory
from .services.autostart import get_platform_manager

# 创建应用实例
app = typer.Typer(
    name="readme-sync",
    help="README同步管理器 - 集中管理所有项目的README.md文件",
    add_completion=False,
)

# 子命令组
config_app = typer.Typer(name="config", help="配置管理")
daemon_app = typer.Typer(name="daemon", help="守护进程管理")  
realtime_app = typer.Typer(name="realtime", help="实时同步管理")
autostart_app = typer.Typer(name="autostart", help="开机自启动管理")
conflicts_app = typer.Typer(name="conflicts", help="冲突管理")

app.add_typer(config_app)
app.add_typer(daemon_app)
app.add_typer(realtime_app)
app.add_typer(autostart_app)
app.add_typer(conflicts_app)

console = Console()


@app.command()
def init():
    """初始化配置文件"""
    config = ConfigManager()
    console.print("初始化配置文件...", style="yellow")
    
    # 检查文件是否已初始化
    if config.config_path.exists():
        if not typer.confirm(f"配置文件已存在于 {config.config_path}，是否重新初始化？"):
            return
    
    # 创建默认配置
    default_config = config.get_default_config()
    
    # 交互式配置
    console.print("\n请输入配置信息:", style="cyan")
    
    # 设置目标文件夹
    target_folder = typer.prompt(
        "目标文件夹路径",
        default="~/Documents/README-Sync"
    )
    
    if target_folder:
        expanded_target = os.path.expanduser(target_folder)
        try:
            os.makedirs(expanded_target, exist_ok=True)
            config.set_target_folder(target_folder)
            console.print(f"✓ 目标文件夹已设置: {expanded_target}", style="green")
        except Exception as e:
            console.print(f"✗ 创建目标文件夹失败: {e}", style="red")
            return
    
    # 添加源文件夹
    while True:
        source_folder = typer.prompt(
            "源文件夹路径 (留空结束)",
            default="",
            show_default=False
        )
        
        if not source_folder:
            break
        
        if config.add_source_folder(source_folder):
            console.print(f"✓ 已添加源文件夹: {os.path.expanduser(source_folder)}", style="green")
        else:
            console.print(f"✗ 添加源文件夹失败", style="red")
    
    console.print(f"\n✓ 初始化完成！配置文件已保存至: {config.config_path}", style="green")
    console.print("使用 'readme-sync config list' 查看配置")
    console.print("使用 'readme-sync add-source <path>' 添加更多源文件夹")


@app.command()
def add_source(folder_path: str = typer.Argument(..., help="源文件夹路径")):
    """添加源文件夹"""
    config = ConfigManager()
    
    if config.add_source_folder(folder_path):
        console.print(f"✓ 已添加源文件夹: {os.path.expanduser(folder_path)}", style="green")
    else:
        console.print(f"✗ 添加源文件夹失败: {folder_path}", style="red")


@app.command()
def remove_source(folder_path: str = typer.Argument(..., help="源文件夹路径")):
    """移除源文件夹"""
    config = ConfigManager()
    
    if config.remove_source_folder(folder_path):
        console.print(f"✓ 已移除源文件夹: {folder_path}", style="green")
    else:
        console.print(f"✗ 移除源文件夹失败: {folder_path}", style="red")


@app.command()
def set_target(folder_path: str = typer.Argument(..., help="目标文件夹路径")):
    """设置目标文件夹"""
    config = ConfigManager()
    
    if config.set_target_folder(folder_path):
        console.print(f"✓ 目标文件夹已设置: {os.path.expanduser(folder_path)}", style="green")
    else:
        console.print(f"✗ 设置目标文件夹失败: {folder_path}", style="red")


@app.command()
def sync(
    reverse: bool = typer.Option(False, "--reverse", help="从目标同步到源文件夹（谨慎使用）"),
    force: bool = typer.Option(False, "--force", help="强制反向同步，跳过安全确认")
):
    """执行同步操作"""
    config = ConfigManager()
    db = DatabaseManager()
    engine = SyncEngine(config, db)
    
    # 验证配置
    errors = config.validate_config()
    if errors:
        console.print("配置验证失败:", style="red")
        for error in errors:
            console.print(f"  ✗ {error}", style="red")
        console.print("请使用 'readme-sync config list' 检查配置")
        return
    
    # 执行同步
    try:
        if reverse:
            # 反向同步安全确认
            if not force:
                console.print("⚠️  警告：反向同步会将目标文件夹的内容覆盖到源文件夹", style="yellow")
                console.print("这可能会覆盖您在源项目中的修改！", style="yellow")
                if not typer.confirm("确定要继续吗？"):
                    console.print("已取消反向同步")
                    return
            
            results = engine.reverse_sync_from_target()
            console.print(f"\n反向同步完成:", style="green")
        else:
            results = engine.sync_all()
            console.print(f"\n同步完成:", style="green")
        
        for key, value in results.items():
            if value > 0:
                console.print(f"  {key}: {value}")
    
    except Exception as e:
        console.print(f"✗ 同步失败: {e}", style="red")


@app.command()
def watch(
    interval: int = typer.Option(300, "--interval", help="监控间隔时间（秒）"),
    daemon_mode: bool = typer.Option(False, "--daemon", help="后台运行模式")
):
    """文件监控模式"""
    config = ConfigManager()
    db = DatabaseManager()
    engine = SyncEngine(config, db)
    
    # 验证配置
    errors = config.validate_config()
    if errors:
        console.print("配置验证失败:", style="red")
        for error in errors:
            console.print(f"  ✗ {error}", style="red")
        return
    
    console.print(f"文件监控模式启动 (间隔: {interval}秒)", style="yellow")
    console.print("按 Ctrl+C 停止监控")
    
    try:
        while True:
            try:
                console.print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 检查更新...")
                results = engine.sync_all()
                
                if any(results.values()):
                    console.print("发现更新:", style="cyan")
                    for key, value in results.items():
                        if value > 0:
                            console.print(f"  {key}: {value}")
                else:
                    console.print("无更新")
                
                time.sleep(interval)
            
            except KeyboardInterrupt:
                console.print("\n监控已停止", style="yellow")
                break
            except Exception as e:
                console.print(f"监控过程中发生错误: {e}", style="red")
                time.sleep(interval)
    
    except Exception as e:
        console.print(f"文件监控失败: {e}", style="red")


@app.command()
def status():
    """查看同步状态"""
    config = ConfigManager()
    db = DatabaseManager()
    engine = SyncEngine(config, db)
    
    console.print("README同步管理器状态:", style="bold cyan")
    console.print("=" * 40)
    
    # 配置信息
    target_folder = config.get_target_folder()
    source_folders = config.get_enabled_source_folders()
    
    console.print(f"目标文件夹: {target_folder or '未设置'}")
    console.print(f"源文件夹数量: {len(source_folders)}")
    
    if source_folders:
        for folder in source_folders:
            exists = "✓" if os.path.exists(folder) else "✗"
            style = "green" if exists == "✓" else "red"
            console.print(f"  {exists} {folder}", style=style)
    
    # 同步状态
    try:
        status_info = engine.get_sync_status()
        console.print(f"\n同步状态:", style="cyan")
        console.print(f"  映射总数: {status_info['total_mappings']}")
        console.print(f"  源文件数: {status_info['source_files']}")
        console.print(f"  目标文件数: {status_info['target_files']}")
        console.print(f"  过期文件数: {status_info['outdated_files']}")
        console.print(f"  缺失源文件: {status_info['missing_source']}")
        console.print(f"  缺失目标文件: {status_info['missing_target']}")
        
        if status_info['last_sync'] > 0:
            last_sync = datetime.fromtimestamp(status_info['last_sync'])
            console.print(f"  上次同步: {last_sync.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            console.print(f"  上次同步: 从未同步")
    
    except Exception as e:
        console.print(f"获取状态失败: {e}", style="red")


@app.command()
def mappings():
    """列出已建立的源-目标映射关系"""
    db = DatabaseManager()
    try:
        rows = db.get_all_mappings()
        if not rows:
            console.print("当前没有任何映射记录", style="yellow")
            return

        table = Table(title="文件映射列表")
        table.add_column("项目", style="cyan", no_wrap=True)
        table.add_column("源文件", style="green")
        table.add_column("目标文件", style="yellow")
        table.add_column("文件名", style="magenta", no_wrap=True)
        table.add_column("上次同步", style="dim", no_wrap=True)

        from datetime import datetime
        for m in rows:
            last_sync = m.get("last_sync_time") or 0
            ts = datetime.fromtimestamp(last_sync).strftime("%Y-%m-%d %H:%M:%S") if last_sync else "-"
            table.add_row(
                str(m.get("project_name", "-")),
                str(m.get("source_path", "-")),
                str(m.get("target_path", "-")),
                str(m.get("renamed_filename", "-")),
                ts,
            )
        console.print(table)
        console.print(f"共 {len(rows)} 条映射", style="green")
    except Exception as e:
        console.print(f"获取映射失败: {e}", style="red")


@app.command()
def scan():
    """扫描并显示README文件"""
    config = ConfigManager()
    scanner = FileScanner(config)
    
    console.print("扫描README文件...", style="yellow")
    
    # 扫描所有文件
    readme_files = scanner.scan_all_sources()
    
    if not readme_files:
        console.print("未找到任何README文件", style="yellow")
        return
    
    console.print(f"找到 {len(readme_files)} 个README文件:", style="green")
    
    # 创建表格显示结果
    table = Table(title="README文件扫描结果")
    table.add_column("项目名称", style="cyan", no_wrap=True)
    table.add_column("源文件路径", style="green")
    table.add_column("目标文件名", style="yellow")
    
    for file_info in readme_files:
        table.add_row(
            file_info['project_name'],
            file_info['source_path'],
            file_info['target_filename']
        )
    
    console.print(table)


@app.command()
def cleanup():
    """清理数据库中的孤立映射"""
    db = DatabaseManager()
    
    console.print("清理数据库中的孤立映射...", style="yellow")
    orphaned_count = db.cleanup_orphaned_mappings()
    
    if orphaned_count > 0:
        console.print(f"✓ 清理了 {orphaned_count} 个孤立映射", style="green")
    else:
        console.print("没有发现孤立映射", style="yellow")


@app.command()
def move_unlinked():
    """移动未链接文件到子文件夹"""
    config = ConfigManager()
    db = DatabaseManager()
    
    # 获取目标文件夹
    target_folder = config.get_target_folder_from_config()
    if not target_folder:
        console.print("❌ 未设置目标文件夹", style="red")
        return
    
    if not os.path.exists(target_folder):
        console.print(f"❌ 目标文件夹不存在: {target_folder}", style="red")
        return
    
    # 检查配置
    if not config.get_move_unlinked_files():
        console.print("ℹ️ 未链接文件移动功能已禁用", style="yellow")
        console.print("可使用以下命令启用: readme-sync config set sync_settings.move_unlinked_files true")
        return
    
    subfolder = config.get_unlinked_subfolder()
    
    console.print(f"扫描目标文件夹中的未链接文件: {target_folder}", style="yellow")
    
    # 查找未链接文件
    unlinked_files = db.find_unlinked_files(target_folder)
    
    if not unlinked_files:
        console.print("✓ 没有发现未链接文件", style="green")
        return
    
    console.print(f"发现 {len(unlinked_files)} 个未链接文件:", style="yellow")
    for file_path in unlinked_files:
        console.print(f"  • {os.path.basename(file_path)}", style="dim")
    
    # 移动文件
    console.print(f"\n移动文件到 {subfolder}/ 文件夹...", style="yellow")
    moved_count = db.move_unlinked_files(target_folder, subfolder)
    
    if moved_count > 0:
        console.print(f"✓ 成功移动了 {moved_count} 个文件", style="green")
    else:
        console.print("❌ 移动失败", style="red")


@app.command()
def list_unlinked():
    """列出未链接文件"""
    config = ConfigManager()
    db = DatabaseManager()
    
    # 获取目标文件夹
    target_folder = config.get_target_folder_from_config()
    if not target_folder:
        console.print("❌ 未设置目标文件夹", style="red")
        return
    
    if not os.path.exists(target_folder):
        console.print(f"❌ 目标文件夹不存在: {target_folder}", style="red")
        return
    
    console.print(f"扫描目标文件夹: {target_folder}", style="yellow")
    
    # 查找未链接文件
    unlinked_files = db.find_unlinked_files(target_folder)
    
    if not unlinked_files:
        console.print("✓ 没有发现未链接文件", style="green")
        return
    
    console.print(f"\n发现 {len(unlinked_files)} 个未链接文件:", style="yellow")
    
    for file_path in unlinked_files:
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        file_size_str = f"{file_size:,} bytes" if file_size < 1024 else f"{file_size/1024:.1f} KB"
        
        console.print(f"  📄 {file_name} ({file_size_str})", style="white")
    
    subfolder = config.get_unlinked_subfolder()
    console.print(f"\n💡 使用 'readme-sync move-unlinked' 将这些文件移动到 {subfolder}/ 文件夹", style="cyan")


@app.command()
def smart_sync(
    dry_run: bool = typer.Option(False, "--dry-run", help="仅显示需要同步的文件，不执行实际同步")
):
    """智能增量同步 - 安全地同步用户在Obsidian中的修改"""
    config = ConfigManager()
    db = DatabaseManager()
    engine = SyncEngine(config, db)
    
    # 验证配置
    errors = config.validate_config()
    if errors:
        console.print("配置验证失败:", style="red")
        for error in errors:
            console.print(f"  ✗ {error}", style="red")
        return
    
    console.print("开始智能增量同步...", style="yellow")
    
    try:
        # 扫描目标文件夹，查找用户修改
        target_files = engine.scanner.scan_target_folder()
        pending_syncs = []
        
        for target_file in target_files:
            target_path = target_file['target_path']
            
            # 查找对应的源文件映射
            mapping = engine.db.find_mapping_by_target(target_path)
            if not mapping:
                continue
            
            source_path = mapping['source_path']
            if not os.path.exists(source_path):
                continue
            
            # 使用智能策略判断是否需要同步
            sync_action = engine._determine_sync_action(source_path, target_path, mapping)
            
            if sync_action == 'target_to_source':
                pending_syncs.append({
                    'source_path': source_path,
                    'target_path': target_path,
                    'mapping': mapping
                })
        
        if not pending_syncs:
            console.print("✓ 没有检测到需要反向同步的文件", style="green")
            return
        
        console.print(f"检测到 {len(pending_syncs)} 个文件需要反向同步:", style="cyan")
        for sync in pending_syncs:
            console.print(f"  {sync['target_path']} -> {sync['source_path']}")
        
        if dry_run:
            console.print("\n这是干运行模式，没有执行实际同步", style="yellow")
            return
        
        if not typer.confirm(f"\n确定要将这 {len(pending_syncs)} 个文件同步到源项目吗？"):
            console.print("已取消同步")
            return
        
        # 执行同步
        synced = 0
        errors = 0
        
        with Progress() as progress:
            task = progress.add_task("同步进度", total=len(pending_syncs))
            
            for sync in pending_syncs:
                try:
                    result = engine._perform_reverse_sync(
                        sync['source_path'], 
                        sync['target_path'], 
                        sync['mapping']
                    )
                    if result == 'reverse_synced':
                        synced += 1
                        console.print(f"✓ 同步完成: {sync['target_path']}", style="green")
                    else:
                        errors += 1
                        console.print(f"✗ 同步失败: {sync['target_path']}", style="red")
                except Exception as e:
                    errors += 1
                    console.print(f"✗ 同步失败 {sync['target_path']}: {e}", style="red")
                
                progress.advance(task)
        
        console.print(f"\n智能增量同步完成: 成功 {synced}, 失败 {errors}", style="green")
    
    except Exception as e:
        console.print(f"✗ 智能同步失败: {e}", style="red")


# 配置管理命令
@config_app.command("list")
def config_list():
    """显示当前配置"""
    config = ConfigManager()
    config.print_config()


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="配置项名称"),
    value: str = typer.Argument(..., help="配置项值")
):
    """设置配置项"""
    config = ConfigManager()
    
    if config.set(key, value):
        console.print(f"✓ 配置已更新: {key} = {value}", style="green")
    else:
        console.print(f"✗ 设置配置项失败", style="red")


@config_app.command("get")
def config_get(key: str = typer.Argument(..., help="配置项名称")):
    """获取配置项"""
    config = ConfigManager()
    value = config.get(key)
    
    if value is not None:
        console.print(f"{key} = {value}")
    else:
        console.print(f"配置项不存在: {key}", style="red")


@config_app.command("cleanup-interval")
def config_cleanup_interval(
    interval: Optional[int] = typer.Argument(
        None, 
        help="清理间隔(秒)，最小60秒。如果不提供，则显示当前值"
    )
):
    """设置或查看清理间隔"""
    config = ConfigManager()
    
    if interval is None:
        # 显示当前值
        current_interval = config.get_cleanup_interval()
        hours = current_interval // 3600
        minutes = (current_interval % 3600) // 60
        
        if hours > 0:
            interval_str = f"{hours}小时{minutes}分钟" if minutes > 0 else f"{hours}小时"
        else:
            interval_str = f"{minutes}分钟"
        
        console.print(f"当前清理间隔: {current_interval}秒 ({interval_str})", style="yellow")
    else:
        # 设置新值
        if config.set_cleanup_interval(interval):
            hours = interval // 3600
            minutes = (interval % 3600) // 60
            
            if hours > 0:
                interval_str = f"{hours}小时{minutes}分钟" if minutes > 0 else f"{hours}小时"
            else:
                interval_str = f"{minutes}分钟"
            
            console.print(f"✓ 清理间隔已设置为: {interval}秒 ({interval_str})", style="green")
            console.print("💡 提示: 重启守护进程以应用新设置", style="yellow")
        else:
            console.print("❌ 设置失败", style="red")


@config_app.command("unlinked-files")
def config_unlinked_files(
    enable: Optional[bool] = typer.Argument(None, help="启用或禁用未链接文件移动 (true/false)")
):
    """设置或查看未链接文件移动配置"""
    config = ConfigManager()
    
    if enable is None:
        # 显示当前值
        current_enabled = config.get_move_unlinked_files()
        subfolder = config.get_unlinked_subfolder()
        
        status = "启用" if current_enabled else "禁用"
        console.print(f"未链接文件移动: {status}", style="yellow")
        console.print(f"目标子文件夹: {subfolder}/", style="yellow")
    else:
        # 设置新值
        if config.set_move_unlinked_files(enable):
            status = "启用" if enable else "禁用"
            console.print(f"✓ 未链接文件移动已{status}", style="green")
            console.print("💡 提示: 重启守护进程以应用新设置", style="yellow")
        else:
            console.print("❌ 设置失败", style="red")


@config_app.command("unlinked-subfolder")
def config_unlinked_subfolder(
    subfolder: Optional[str] = typer.Argument(None, help="未链接文件子文件夹名称")
):
    """设置或查看未链接文件子文件夹名称"""
    config = ConfigManager()
    
    if subfolder is None:
        # 显示当前值
        current_subfolder = config.get_unlinked_subfolder()
        console.print(f"当前子文件夹名称: {current_subfolder}", style="yellow")
    else:
        # 设置新值
        if config.set_unlinked_subfolder(subfolder):
            console.print(f"✓ 子文件夹名称已设置为: {subfolder}", style="green")
            console.print("💡 提示: 重启守护进程以应用新设置", style="yellow")
        else:
            console.print("❌ 设置失败", style="red")


# 守护进程管理命令
@daemon_app.command("start")
def daemon_start(
    foreground: bool = typer.Option(False, "--foreground", "-f", help="前台运行（用于调试）")
):
    """启动守护进程"""
    daemon_mgr = DaemonManager()
    
    if daemon_mgr.is_running():
        console.print("守护进程已在运行", style="yellow")
        return
    
    console.print("启动守护进程...", style="yellow")
    
    if daemon_mgr.start(detach=not foreground):
        if foreground:
            console.print("守护进程已在前台启动", style="green")
        else:
            console.print("守护进程已在后台启动", style="green")
    else:
        console.print("启动守护进程失败", style="red")


@daemon_app.command("stop")
def daemon_stop():
    """停止守护进程"""
    daemon_mgr = DaemonManager()
    
    if not daemon_mgr.is_running():
        console.print("守护进程未运行", style="yellow")
        return
    
    console.print("停止守护进程...", style="yellow")
    
    if daemon_mgr.stop():
        console.print("守护进程已停止", style="green")
    else:
        console.print("停止守护进程失败", style="red")


@daemon_app.command("clean")
def daemon_clean():
    """清理守护进程相关状态文件（pid/log/status/launchd日志）"""
    daemon_mgr = DaemonManager()
    daemon_mgr.clean_state()
    console.print("已清理守护进程状态文件与日志", style="green")


@daemon_app.command("restart")
def daemon_restart():
    """重启守护进程"""
    daemon_mgr = DaemonManager()
    
    console.print("重启守护进程...", style="yellow")
    
    if daemon_mgr.restart():
        console.print("守护进程已重启", style="green")
    else:
        console.print("重启守护进程失败", style="red")


@daemon_app.command("status")
def daemon_status():
    """查看守护进程状态"""
    daemon_mgr = DaemonManager()
    status = daemon_mgr.status()
    
    console.print("守护进程状态:", style="bold cyan")
    console.print("=" * 40)
    
    if status['running']:
        console.print("状态: 运行中 ✓", style="green")
        console.print(f"PID: {status['pid']}")
        console.print(f"运行时间: {format_uptime(status['uptime'])}")
        console.print(f"内存使用: {format_memory(status['memory_usage'])}")
        console.print(f"CPU使用: {status['cpu_usage']:.1f}%")
        
        start_time = datetime.fromtimestamp(status['start_time'])
        console.print(f"启动时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        console.print("状态: 未运行 ✗", style="red")


@daemon_app.command("logs")
def daemon_logs(
    lines: int = typer.Option(50, "--lines", "-n", help="显示日志行数"),
    follow: bool = typer.Option(False, "--follow", "-f", help="持续显示日志")
):
    """查看守护进程日志"""
    daemon_mgr = DaemonManager()
    
    if follow:
        console.print("持续显示日志 (Ctrl+C 退出)...", style="yellow")
        try:
            import subprocess
            subprocess.run([
                'tail', '-f', str(daemon_mgr.log_file)
            ])
        except KeyboardInterrupt:
            console.print("\n停止显示日志")
        except FileNotFoundError:
            console.print("日志文件不存在", style="red")
        except Exception as e:
            console.print(f"显示日志失败: {e}", style="red")
    else:
        logs = daemon_mgr.get_logs(lines)
        console.print(logs)


# 添加autostart命令
@app.command()
def autostart():
    """配置开机自启动守护进程"""
    manager = get_platform_manager()
    
    if not manager:
        console.print("当前平台不支持自动配置开机自启动", style="red")
        return
    
    if manager.is_installed():
        console.print("开机自启动已安装", style="green")
        if typer.confirm("是否要卸载开机自启动？"):
            if manager.uninstall_autostart():
                console.print("✓ 开机自启动已卸载", style="green")
            else:
                console.print("✗ 卸载开机自启动失败", style="red")
    else:
        console.print("安装开机自启动...", style="yellow")
        if manager.install_autostart():
            console.print("✓ 开机自启动已安装", style="green")
            console.print("重启后将自动启动README同步守护进程")
        else:
            console.print("✗ 安装开机自启动失败", style="red")


if __name__ == "__main__":
    app()
