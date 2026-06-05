# Kimi WebBridge MCP Server

将 Kimi WebBridge 封装为 Docker MCP Server，部署在服务器上供远程 AI IDE 通过 MCP 协议使用。控制真实浏览器，提供网页导航、点击、填表、截图、PDF 导出等功能。

## 架构

```
Docker Container
├── Chromium (Xvfb 虚拟显示器) + Kimi WebBridge 扩展
├── kimi-webbridge daemon (:10086, 内部)
├── MCP Server (FastMCP :8000, 对外)
│   ├── API Key 鉴权
│   ├── 调用日志 (SQLite)
│   └── Admin Panel (/admin)
└── Health Monitor (自愈)
```

## 快速开始

### 方式一：直接拉镜像（推荐）

```bash
# 1. 创建 docker-compose.yml（替换 <版本> 为具体版本号或 latest）
cat > docker-compose.yml << 'EOF'
volumes:
  chrome-data:
    driver: local

services:
  kimi-webbridge-mcp:
    image: ghcr.io/molicherry/webbridge:latest
    container_name: kimi-webbridge-mcp
    ports:
      - "${MCP_PORT:-8000}:8000"
    environment:
      - MCP_API_KEY=${MCP_API_KEY:?MCP_API_KEY must be set}
      - MCP_PORT=8000
      - ADMIN_PASSWORD=${ADMIN_PASSWORD:-}
      - ADMIN_SESSION_SECRET=${ADMIN_SESSION_SECRET:-}
      - EXTERNAL_API_KEY=${EXTERNAL_API_KEY:-}
      - DB_PATH=/home/chrome/data/call_records.db
    volumes:
      - chrome-data:/home/chrome/data
    shm_size: "2gb"
    restart: unless-stopped
EOF

# 2. 设置 API Key 并启动
export MCP_API_KEY="your-secret-key-here"
docker compose up -d

# 3. 等待就绪（约 30-60 秒首次启动）
curl http://localhost:8000/health
# → {"status": "ok", "server": "kimi-webbridge-mcp", "version": "1.0.0"}
```

### 方式二：从源码构建

```bash
# 1. 克隆仓库
git clone https://github.com/molicherry/webbridge.git
cd webbridge

# 2. 设置 API Key
export MCP_API_KEY="your-secret-key-here"

# 3. 构建并启动
docker compose up -d --build

# 4. 等待就绪
curl http://localhost:8000/health
```

## 配置

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `MCP_API_KEY` | (必填) | 默认 API 密钥，启动时自动导入为初始密钥 |
| `MCP_PORT` | 8000 | MCP 服务端口 |
| `CDP_PORT` | 9222 | Chrome DevTools 端口 (内部) |
| `DAEMON_PORT` | 10086 | WebBridge daemon 端口 (内部) |
| `CHROME_BROWSER` | `chromium` | 浏览器二进制 (chromium / google-chrome-stable) |
| `ADMIN_PASSWORD` | (空=关闭) | 管理面板登录密码，不设置则不启用面板 |
| `ADMIN_SESSION_SECRET` | (自动生成) | 管理员会话签名密钥 |
| `DB_PATH` | `/home/chrome/data/call_records.db` | SQLite 数据库路径（调用记录 + API 密钥 + 会话映射） |
| `CALL_RECORD_RETENTION_DAYS` | 30 | 调用记录保留天数 |

## AI IDE 配置

### Claude Code

**1. 配置 MCP Server**

在项目根目录或 `~/.claude/settings.json` 中添加：

```json
{
  "mcpServers": {
    "kimi-webbridge": {
      "type": "http",
      "url": "http://<服务器IP>:8000/mcp",
      "headers": {
        "X-API-Key": "<你的API Key>"
      }
    }
  }
}
```

**2. 加载 Skill 文件**

`kimi-browser.md` 是一个 Claude Code Skill，告诉 AI 如何正确使用浏览器的 17 个工具。加载后 AI 会自动遵循其中的工作流和最佳实践。

```bash
# 下载 skill 文件
curl -O https://raw.githubusercontent.com/molicherry/webbridge/master/kimi-browser.md

# 方式 A：放到当前项目的 .claude/skills/ 目录（仅该项目生效）
mkdir -p .claude/skills/
cp kimi-browser.md .claude/skills/

# 方式 B：放到全局 ~/.claude/skills/ 目录（所有项目生效）
mkdir -p ~/.claude/skills/
cp kimi-browser.md ~/.claude/skills/
```

Skill 文件内容详解见 [kimi-browser.md](kimi-browser.md)。

### Claude Desktop

编辑 `claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "kimi-webbridge": {
      "url": "http://<服务器IP>:8000/mcp",
      "headers": {
        "X-API-Key": "<你的API Key>"
      }
    }
  }
}
```

### Cursor / 其他 MCP 兼容 IDE

参考 IDE 的 MCP 配置文档，添加 Streamable HTTP transport：

- **Endpoint**: `http://<服务器IP>:8000/mcp`
- **Transport**: Streamable HTTP
- **Header**: `X-API-Key: <你的API Key>`

## 可用工具 (17个)

### 页面导航
| 工具 | 用途 |
|------|------|
| `navigate` | 导航到 URL，支持新标签页和标签组命名 |
| `find_tab` | 查找已打开的标签页（按 URL 或活跃状态） |
| `list_tabs` | 列出当前 session 的所有标签页 |
| `close_tab` | 关闭当前标签页 |
| `close_session` | 关闭 session 所有标签页 |

### 页面交互
| 工具 | 用途 |
|------|------|
| `snapshot` | 获取页面无障碍树（含 @e 交互元素引用） |
| `click` | DOM 级点击元素（@e 引用或 CSS 选择器） |
| `mouse_click` | CDP 级鼠标点击，处理 display:none 等边缘情况 |
| `fill` | 填写文本（input / textarea / contenteditable），替换模式 |
| `key_type` | 光标处插入文本（不替换已有内容） |
| `send_keys` | 键盘事件模拟，支持组合键（Mod+A、Enter、Tab 等） |

### 高级能力
| 工具 | 用途 |
|------|------|
| `evaluate` | 执行 JavaScript（支持 async/await） |
| `cdp` | 原始 Chrome DevTools Protocol 命令透传 |
| `network` | 网络请求监控（start / stop / list / detail） |
| `screenshot` | 截图（返回 base64，支持元素级截图） |
| `save_as_pdf` | 页面导出 PDF（返回 base64） |
| `upload` | 上传文件到 file input |

所有工具支持可选的 `session_id` 参数用于标签组隔离。

## 管理面板

设置 `ADMIN_PASSWORD` 环境变量后，访问 `/admin` 可打开管理面板：

- **仪表盘**：总调用数、成功率、今日调用、活跃来源统计
- **调用记录**：按方法/密钥/日期/状态筛选，支持分页查看，显示每笔调用的密钥别名、耗时
- **API Key 管理**：支持创建、改名、启用/禁用、删除多个 API 密钥。默认 `MCP_API_KEY` 环境变量自动导入为初始密钥，可通过面板添加额外密钥
- **Tab 管理**：查看所有打开的浏览器标签页（URL、标题、关联密钥、会话、分组），支持关闭指定标签

### 多密钥鉴权

MCP Server 支持多个 API 密钥，所有密钥存储在 SQLite 的 `api_keys` 表中。启动时 `MCP_API_KEY` 环境变量会被自动导入为"默认密钥"。管理面板支持：

- 创建新密钥（自动生成或手动指定）
- 为密钥设置别名（便于在调用记录中识别来源）
- 启用/禁用密钥（禁用后立即拒绝请求）
- 删除密钥

### Session 追踪

每次 `navigate()` 调用会自动记录 URL → session_id → 密钥别名的映射关系。管理面板的 Tab 管理页面通过 Chrome DevTools Protocol 直接查询浏览器真实标签页，并关联到对应的密钥和会话信息。

调用日志中敏感参数（URL、密码、Token 等）自动脱敏，仅存储类型标识。密钥在仪表盘中以掩码形式展示（前 6 位 + 后 4 位）。

管理面板使用独立的密码认证，与 MCP API Key 鉴权互不干扰。登录后会话保持 24 小时，支持频率限制（5 次/分钟）防止暴力破解。

## 持久化

浏览器数据（Cookie、扩展状态）存储在命名 volume `chrome-data` 中：

```bash
# 查看 volume
docker volume ls | grep chrome-data

# 备份
docker run --rm -v kimi-webbridge_chrome-data:/data -v $(pwd):/backup alpine tar czf /backup/chrome-backup.tar.gz -C /data .

# 恢复
docker run --rm -v kimi-webbridge_chrome-data:/data -v $(pwd):/backup alpine tar xzf /backup/chrome-backup.tar.gz -C /data
```

## 自愈

- 容器配置 `restart: unless-stopped`
- Health monitor 每 10 秒检测 Chrome CDP 和 daemon 状态
- Chrome 崩溃 → 容器自动重启
- Daemon 崩溃 → 自动重启 daemon（最多 5 次，超限后容器重启）
- MCP 服务崩溃 → Docker 重启容器
