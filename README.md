# Kimi WebBridge MCP Server

将 Kimi WebBridge 封装为 Docker MCP Server，部署在服务器上供远程 AI IDE 通过 MCP 协议使用。控制真实浏览器，提供网页导航、点击、填表、截图、PDF 导出等功能。

## 架构

```
Docker Container
├── Chromium (Xvfb 虚拟显示器) + Kimi WebBridge 扩展
├── kimi-webbridge daemon (:10086, 内部)
├── MCP Server (FastMCP :8000, 对外)
│   └── API Key 鉴权
└── Health Monitor (自愈)
```

## 快速开始

```bash
# 1. 设置 API Key
export MCP_API_KEY="your-secret-key-here"

# 2. 构建并启动
docker compose up -d --build

# 3. 等待就绪（约 30-60 秒首次启动）
curl http://localhost:8000/health
# → {"status": "ok", "server": "kimi-webbridge-mcp", "version": "1.0.0"}

# 4. 验证扩展连接
docker exec kimi-webbridge-mcp curl -s http://127.0.0.1:10086/status
# → {"extension_connected": true, "extension_id": "hinhmbb...", "extension_version": "1.9.14", "running": true}
```

## 配置

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `MCP_API_KEY` | (必填) | API 鉴权密钥 |
| `MCP_PORT` | 8000 | MCP 服务端口 |
| `CDP_PORT` | 9222 | Chrome DevTools 端口 (内部) |
| `DAEMON_PORT` | 10086 | WebBridge daemon 端口 (内部) |
| `CHROME_BROWSER` | `chromium` | 浏览器二进制 (chromium / google-chrome-stable) |

## AI IDE 配置

### Claude Code

在项目根目录或 `~/.claude/settings.json` 中添加 MCP server：

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

同时加载 `kimi-browser.md` skill 文件以获得最佳浏览器操控体验：

```bash
# 复制 skill 到项目
cp kimi-browser.md .claude/skills/
```

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

## 自定义部署

如需配合 Traefik 反向代理或自定义域名，参考以下 docker-compose 片段：

```yaml
services:
  kimi-webbridge-mcp:
    # ... 基础配置不变 ...
    expose:
      - "8000"           # 用 expose 替代 ports
    networks:
      - proxy            # 加入 Traefik 网络
    labels:
      - traefik.enable=true
      - traefik.http.routers.kimi-webbridge.rule=Host(`your.domain.com`)
      - traefik.http.routers.kimi-webbridge.entrypoints=websecure
      - traefik.http.routers.kimi-webbridge.tls=true
      - traefik.http.services.kimi-webbridge.loadbalancer.server.port=8000

networks:
  proxy:
    external: true
```

## CI 验证

项目包含 GitHub Actions CI（`.github/workflows/docker-build.yml`），每次 push 自动：
- 构建 Docker 镜像
- 启动容器并等待 healthy
- 验证 `/health` 端点
- 验证 daemon `extension_connected: true`
