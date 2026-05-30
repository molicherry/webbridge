"""Tests for MCP tool handlers with mocked daemon responses."""

import json

import pytest
from unittest.mock import AsyncMock, patch


@pytest.fixture
def mock_call():
    with patch("src.mcp_server.tools._call", new_callable=AsyncMock) as mock:
        yield mock


@pytest.mark.asyncio
async def test_navigate(mock_call):
    mock_call.return_value = {"success": True, "url": "https://example.com", "tabId": "tab-1"}
    from src.mcp_server.tools import navigate
    result = await navigate("https://example.com", new_tab=True)
    data = json.loads(result)
    assert data["success"] is True
    assert data["url"] == "https://example.com"
    mock_call.assert_called_once_with("navigate", {"url": "https://example.com", "newTab": True}, None)


@pytest.mark.asyncio
async def test_navigate_with_session(mock_call):
    mock_call.return_value = {"success": True, "url": "https://example.com"}
    from src.mcp_server.tools import navigate
    result = await navigate("https://example.com", session_id="my-session")
    data = json.loads(result)
    assert data["success"] is True
    mock_call.assert_called_once_with("navigate", {"url": "https://example.com", "newTab": True}, "my-session")


@pytest.mark.asyncio
async def test_navigate_with_group_title(mock_call):
    mock_call.return_value = {"success": True}
    from src.mcp_server.tools import navigate
    result = await navigate("https://example.com", new_tab=True, group_title="My Group")
    mock_call.assert_called_once_with(
        "navigate",
        {"url": "https://example.com", "newTab": True, "group_title": "My Group"},
        None,
    )


@pytest.mark.asyncio
async def test_navigate_reuse_tab(mock_call):
    mock_call.return_value = {"success": True}
    from src.mcp_server.tools import navigate
    result = await navigate("https://example.com", new_tab=False)
    mock_call.assert_called_once_with("navigate", {"url": "https://example.com", "newTab": False}, None)


@pytest.mark.asyncio
async def test_find_tab(mock_call):
    mock_call.return_value = {"success": True, "url": "https://example.com", "tabId": "tab-1"}
    from src.mcp_server.tools import find_tab
    result = await find_tab(url="https://example.com", active=True)
    data = json.loads(result)
    assert data["success"] is True
    mock_call.assert_called_once_with("find_tab", {"url": "https://example.com", "active": True}, None)


@pytest.mark.asyncio
async def test_find_tab_no_args(mock_call):
    mock_call.return_value = {"success": True}
    from src.mcp_server.tools import find_tab
    result = await find_tab()
    mock_call.assert_called_once_with("find_tab", {"active": False}, None)


@pytest.mark.asyncio
async def test_snapshot(mock_call):
    mock_call.return_value = {"url": "https://example.com", "title": "Example", "tree": "[RootWebArea]"}
    from src.mcp_server.tools import snapshot
    result = await snapshot()
    data = json.loads(result)
    assert data["title"] == "Example"
    assert "[RootWebArea]" in data["tree"]


@pytest.mark.asyncio
async def test_click(mock_call):
    mock_call.return_value = {"success": True, "tag": "button", "text": "Submit"}
    from src.mcp_server.tools import click
    result = await click("@e123")
    data = json.loads(result)
    assert data["success"] is True
    mock_call.assert_called_once_with("click", {"selector": "@e123"}, None)


@pytest.mark.asyncio
async def test_fill(mock_call):
    mock_call.return_value = {"success": True, "mode": "value"}
    from src.mcp_server.tools import fill
    result = await fill("@e456", "hello world")
    data = json.loads(result)
    assert data["success"] is True
    mock_call.assert_called_once_with("fill", {"selector": "@e456", "value": "hello world"}, None)


@pytest.mark.asyncio
async def test_evaluate(mock_call):
    mock_call.return_value = {"type": "string", "value": "result"}
    from src.mcp_server.tools import evaluate
    result = await evaluate("document.title")
    data = json.loads(result)
    assert data["value"] == "result"


@pytest.mark.asyncio
async def test_network_start(mock_call):
    mock_call.return_value = {"success": True}
    from src.mcp_server.tools import network
    result = await network(cmd="start", url_filter="*.js")
    data = json.loads(result)
    assert data["success"] is True
    mock_call.assert_called_once_with("network", {"cmd": "start", "filter": "*.js"}, None)


@pytest.mark.asyncio
async def test_network_detail(mock_call):
    mock_call.return_value = {"success": True, "data": {}}
    from src.mcp_server.tools import network
    result = await network(cmd="detail", request_id="req-1")
    mock_call.assert_called_once_with("network", {"cmd": "detail", "requestId": "req-1"}, None)


@pytest.mark.asyncio
async def test_upload(mock_call):
    mock_call.return_value = {"success": True, "fileCount": 2}
    from src.mcp_server.tools import upload
    result = await upload("@e789", "/tmp/a.txt, /tmp/b.txt")
    data = json.loads(result)
    assert data["success"] is True
    assert data["fileCount"] == 2


@pytest.mark.asyncio
async def test_list_tabs(mock_call):
    mock_call.return_value = {"success": True, "tabs": [{"tabId": "1", "url": "https://example.com"}]}
    from src.mcp_server.tools import list_tabs
    result = await list_tabs()
    data = json.loads(result)
    assert data["success"] is True
    assert len(data["tabs"]) == 1


@pytest.mark.asyncio
async def test_close_tab(mock_call):
    mock_call.return_value = {"success": True, "closed": True}
    from src.mcp_server.tools import close_tab
    result = await close_tab()
    data = json.loads(result)
    assert data["success"] is True
    assert data["closed"] is True


@pytest.mark.asyncio
async def test_close_session(mock_call):
    mock_call.return_value = {"success": True, "closed": 3}
    from src.mcp_server.tools import close_session
    result = await close_session()
    data = json.loads(result)
    assert data["success"] is True
    assert data["closed"] == 3


@pytest.mark.asyncio
async def test_screenshot_with_file(mock_call):
    mock_call.return_value = {"path": "/tmp/screenshot.png", "format": "png", "sizeBytes": 1024, "mimeType": "image/png"}
    with patch("src.mcp_server.tools._read_file_b64", return_value="aW1hZ2VkYXRh"):
        from src.mcp_server.tools import screenshot
        result = await screenshot(session_id="s1")
    data = json.loads(result)
    assert data["data"] == "aW1hZ2VkYXRh"
    assert data["mimeType"] == "image/png"


@pytest.mark.asyncio
async def test_save_as_pdf_with_file(mock_call):
    mock_call.return_value = {"path": "/tmp/page.pdf", "sizeBytes": 2048, "pageTitle": "My Page"}
    with patch("src.mcp_server.tools._read_file_b64", return_value="cGRmZGF0YQ=="):
        from src.mcp_server.tools import save_as_pdf
        result = await save_as_pdf(paper_format="a4", session_id="s1")
    data = json.loads(result)
    assert data["data"] == "cGRmZGF0YQ=="
    assert data["mimeType"] == "application/pdf"
    assert data["pageTitle"] == "My Page"


@pytest.mark.asyncio
async def test_screenshot_no_file(mock_call):
    mock_call.return_value = {"format": "png", "success": True}
    from src.mcp_server.tools import screenshot
    result = await screenshot()
    data = json.loads(result)
    assert data["success"] is True


def test_all_tools_registered():
    from src.mcp_server.tools import TOOL_REGISTRY
    tool_names = {handler.__name__ for handler, _ in TOOL_REGISTRY}
    expected = {
        "navigate", "find_tab", "snapshot", "click", "fill",
        "screenshot", "evaluate", "network", "upload", "save_as_pdf",
        "list_tabs", "close_tab", "close_session",
    }
    assert tool_names == expected
    assert len(TOOL_REGISTRY) == 13


def test_tool_descriptions():
    from src.mcp_server.tools import TOOL_REGISTRY
    for handler, description in TOOL_REGISTRY:
        assert isinstance(description, str)
        assert len(description) > 20
        assert handler.__doc__ is not None
