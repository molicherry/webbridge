# Kimi WebBridge MCP Server

将 Kimi WebBridge 封装为 Docker MCP Server，部署在服务器上供远程 AI IDE 通过 MCP 协议使用。控制真实浏览器（含你的 Kimi 登录会话），提供网页导航、点击、填表、截图、PDF 导出等功能。

## 架构

```
Docker Container
├── Chrome (headless) + Kimi WebBridge 扩展
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
curl -H "X-API-Key: $MCP_API_KEY" http://localhost:8000/health
# → {"status": "ok", "server": "kimi-webbridge-mcp", "version": "1.0.0"}
```

## 配置

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `MCP_API_KEY` | (必填) | API 鉴权密钥 |
| `MCP_PORT` | 8000 | MCP 服务端口 |
| `CDP_PORT` | 9222 | Chrome DevTools 端口 (内部) |
| `DAEMON_PORT` | 10086 | WebBridge daemon 端口 (内部) |

## AI IDE 配置

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

## 可用工具 (13个)

| 工具 | 用途 |
|------|------|
| `navigate` | 导航到 URL，支持新标签页和标签组命名 |
| `find_tab` | 查找已打开的标签页（按 URL 或活跃状态） |
| `snapshot` | 获取页面无障碍树（含 @e 交互元素引用） |
| `click` | 点击元素（@e 引用或 CSS 选择器） |
| `fill` | 填写文本（input / textarea / contenteditable） |
| `screenshot` | 截图（返回 base64，支持元素截图） |
| `evaluate` | 执行 JavaScript（支持 async/await） |
| `network` | 网络请求监控（start / stop / list / detail） |
| `upload` | 上传文件到 file input |
| `save_as_pdf` | 页面导出 PDF（返回 base64） |
| `list_tabs` | 列出当前 session 的所有标签页 |
| `close_tab` | 关闭当前标签页 |
| `close_session` | 关闭 session 所有标签页 |

所有工具支持可选的 `session_id` 参数用于标签组隔离。

## Kimi 登录

容器首次启动后，你需要登录 Kimi：

1. 通过 MCP `navigate` 打开 `https://www.kimi.com`
2. 使用 `snapshot` + `click` + `fill` 完成登录
3. 登录态持久化在 `chrome-data` volume 中，重启不丢失

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
- Daemon 崩溃 → 自动重启 daemon
- MCP 服务崩溃 → Docker 重启容器
