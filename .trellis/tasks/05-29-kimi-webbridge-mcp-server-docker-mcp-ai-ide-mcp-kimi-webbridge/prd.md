# kimi-webbridge-mcp-server: Docker化MCP服务

## Goal

将 Kimi WebBridge 封装为 MCP (Model Context Protocol) Server，打包为 Docker 镜像部署在 Debian 服务器上。其他机器上的 AI IDE 通过 MCP 协议远程使用 Kimi WebBridge，实现与本地 kimi-webbridge 完全一致的功能。

## Requirements

* Docker 容器部署在 Debian 服务器，基于自定义 Debian + Chrome Stable 镜像
* 容器内运行：Chrome headless（加载 Kimi WebBridge 扩展）+ webbridge daemon
* MCP Server (Python FastMCP) 暴露全部 12 个 kimi-webbridge 工具
* Streamable HTTP 传输模式，API Key 鉴权
* 浏览器 profile 持久化（volume 挂载 Chrome user-data-dir），重启保留 Kimi 登录态
* Chrome/daemon 健康检查 + 自动重启（自愈机制）
* 单用户模式，多用户池化留到下个版本

## Acceptance Criteria

* [ ] Docker 镜像可构建并运行在 Debian 上
* [ ] MCP tools/list 返回全部 12 个 webbridge 工具
* [ ] MCP tools/call 可调用每个工具并返回正确结果
* [ ] API Key 鉴权：无 key / 错误 key 返回 401
* [ ] session_id 参数可选，不传自动生成，传了复用
* [ ] 容器重启后 Chrome 登录态保持
* [ ] Chrome crash / daemon 断开后自动恢复
* [ ] 远程 IDE 可成功连接并执行浏览器操作（截图验证）

## Definition of Done

* Dockerfile + docker-compose.yml + entrypoint.sh 可生产部署
* 12 个 kimi-webbridge 工具通过 MCP 完全可用
* API Key 鉴权中间件生效
* Chrome/daemon 自愈逻辑就绪
* README 包含部署、配置、使用文档
* 核心流程测试覆盖

## Technical Approach

```
┌─────────────────────────────────────────────────┐
│  Docker Container (Debian)                       │
│                                                   │
│  ┌──────────┐    HTTP     ┌──────────────────┐   │
│  │  Chrome   │◄──────────►│ kimi-webbridge   │   │
│  │ (headless│  CDP/WS     │ daemon :10086    │   │
│  │ +ext)     │            └────────┬─────────┘   │
│  └──────────┘                      │ REST API    │
│                                    │             │
│  ┌─────────────────┐    ┌─────────▼──────────┐   │
│  │  Health Monitor  │◄──►│  MCP Server        │   │
│  │  (supervisord)   │    │  (FastMCP :8000)   │───┼──► MCP clients
│  └─────────────────┘    └────────────────────┘   │
│          Streamable HTTP + API Key Auth           │
│          /mcp endpoint                            │
└─────────────────────────────────────────────────┘
   Volumes: chrome-data (user-data-dir)
```

* **MCP Server**: Python FastMCP, `stateless_http=True, json_response=True`
* **Auth**: `BearerAuth` → 验证 `X-API-Key` header
* **Tools**: 12 个 `@mcp.tool()` 装饰函数，内部 `httpx` 调用 webbridge daemon
* **Session**: 每个 tool 增加可选 `session_id` 参数 → 传给 daemon
* **自愈**: Docker healthcheck + restart policy 处理进程崩溃
* **Chrome**: `--headless --no-sandbox --load-extension=... --user-data-dir=/data/chrome`
* **Entrypoint**: 先启动 Chrome，再启动 webbridge daemon，最后启动 MCP server

## Architecture Decisions

1. **Python FastMCP**: REST API 1:1 映射为 MCP tool 最少模板代码，鉴权内置，stateless HTTP 一行开启
2. **API Key 鉴权**: 内网部署场景，BearerAuth 内置，环境变量 `MCP_API_KEY` 配置
3. **显式 session_id 参数**: 与原版 kimi-webbridge 行为一致，可选复用 tab group
4. **Kimi WebBridge 扩展**: `https://kimi-web-img.moonshot.cn/webbridge/latest/extension/kimi-webbridge-extension.zip`
5. **Kimi WebBridge binary**: `curl -fsSL https://cdn.kimi.com/webbridge/install.sh | bash` 自动检测平台
6. **Chrome user-data-dir 持久化**: volume 挂载，重启保留登录态
7. **自愈**: Docker restart policy `unless-stopped` + healthcheck 兜底

## Out of Scope

* 多用户并发（浏览器池管理）— 下个版本
* 多实例负载均衡 — 下个版本
* OAuth 2.1 鉴权 — 后续升级
* CI/CD 集成 / GitHub Action — 下个版本

## Research References

* [`research/mcp-server-patterns.md`](research/mcp-server-patterns.md) — Python FastMCP 推荐，Streamable HTTP + API Key auth
* [`research/docker-browser-automation.md`](research/docker-browser-automation.md) — Chrome headless 132+ 支持扩展加载，自定义 Debian 镜像

## Implementation Plan (PR order)

* **PR1**: `Dockerfile` + `entrypoint.sh` + `docker-compose.yml` — 容器骨架
* **PR2**: MCP Server 核心 — FastMCP 应用 + 12 tool handlers + API Key auth
* **PR3**: 自愈 + healthcheck + 优雅关闭 + README + 测试
