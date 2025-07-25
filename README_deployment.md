# README Sync System

## 功能实现原理

```mermaid
graph TD
    A[deploy.sh] --> B[生成scan_folders.json]
    A --> C[创建LaunchAgent]
    A --> D[设置PROJECT_DATA_DIR]
    
    E[main.py] --> F[Config加载]
    F --> G[读取scan_folders.json]
    F --> H[设置数据目录]
    
    I[文件扫描] --> J[遍历源目录]
    J --> K[查找README文件]
    K --> L[复制到目标目录]
    
    M[同步服务] --> N[定时扫描]
    N --> O[文件变化检测]
    O --> P[增量同步]
    
    Q[LaunchAgent] --> R[守护进程]
    R --> S[自动同步]
    S --> T[日志记录]
    
    subgraph "数据目录结构"
        U[~/Developer/Code/Data/srv/readme_sync/]
        U --> V[config.yaml]
        U --> W[scan_folders.json]
        U --> X[logs/]
        U --> Y[database.db]
        U --> Z[sync_data.db]
    end
```

## 文件引用关系

```mermaid
graph LR
    A[deploy.sh] --> B[src/readme_sync/services/config.py]
    B --> C[src/readme_sync/core/sync_manager.py]
    C --> D[src/readme_sync/services/database.py]
    D --> E[src/readme_sync/services/daemon.py]
    
    F[scan_folders.json] --> B
    G[config.yaml] --> B
    H[LaunchAgent plist] --> I[main.py]
    I --> J[daemon start]
    J --> E
    
    K[PROJECT_DATA_DIR] --> B
    K --> D
    K --> L[logs/]
    K --> M[target_folder/]
```

## 部署说明

1. **运行部署脚本**：
   ```bash
   ./deploy.sh
   ```

2. **配置文件**：
   - `scan_folders.json`: 定义源目录、目标目录和文件模式
   - `config.yaml`: 项目配置和同步设置

3. **数据目录**：
   - 位置：`~/Developer/Code/Data/srv/readme_sync/`
   - 包含：配置文件、数据库、日志

4. **服务管理**：
   - LaunchAgent 自动启动
   - 守护进程监控文件变化
   - 实时同步 README 文件

## 新架构特性

- ✅ 使用 PROJECT_DATA_DIR 环境变量
- ✅ 符合新的文件结构规范
- ✅ 支持用户自定义扫描目录
- ✅ 规范化数据目录命名
- ✅ 统一的部署脚本模板