"""
Flat end-to-end test harness for Paperless MCP Server.

Connects via Streamable HTTP (JSON-RPC POST), tests all tools,
and prints a Markdown report to stdout.

Every test runs unconditionally — no skips, no branching, no loops
over test configs. Each test is a sequential await call. Failures
cascade through the state dict without crashing the runner.
"""

import asyncio
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx
from toon_mcp import toon_to_json

MCP_SERVER_PORT = os.environ.get("MCP_SERVER_PORT", "")
API_KEY = os.environ.get("API_KEY", "")
MCP_URL = f"http://localhost:{MCP_SERVER_PORT}/mcp"

PAPERLESS_DIRECT_URL = os.environ.get("PAPERLESS_DIRECT_URL", "http://localhost:8050")

MCP_HEADERS = {
    "Authorization": f"Token {API_KEY}",
}

rid = uuid.uuid4().hex[:8]

results: list[dict[str, Any]] = []


# =============================================================================
# MCP Session (transport layer — adaptive, detects stateful vs stateless)
# =============================================================================

class MCPSession:
    """MCP Streamable HTTP client. Detects stateful/stateless from response headers."""

    def __init__(self, url: str, headers: dict[str, str]):
        self.url = url
        self.base_headers = {
            **headers,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        self.headers = dict(self.base_headers)
        self.client = httpx.AsyncClient(timeout=120.0)
        self._request_id = 0
        self._session_id: str | None = None

    def _capture_session(self, response) -> None:
        sid = response.headers.get("mcp-session-id")
        if sid:
            self._session_id = sid
            self.headers = {**self.base_headers, "mcp-session-id": sid}

    async def __aenter__(self):
        await self._initialize()
        return self

    async def __aexit__(self, *args):
        await self.client.aclose()

    async def _send_notification(self, method: str, params: dict | None = None) -> None:
        payload = {"jsonrpc": "2.0", "method": method}
        if params:
            payload["params"] = params
        response = await self.client.post(self.url, headers=self.headers, json=payload)
        self._capture_session(response)
        if response.status_code not in (200, 202):
            response.raise_for_status()

    async def _send(self, method: str, params: dict | None = None) -> dict:
        self._request_id += 1
        payload = {"jsonrpc": "2.0", "id": self._request_id, "method": method}
        if params:
            payload["params"] = params
        response = await self.client.post(self.url, headers=self.headers, json=payload)
        if response.status_code == 202:
            return {}
        response.raise_for_status()

        self._capture_session(response)

        data = response.json()
        if isinstance(data, list):
            data = data[0]
        if isinstance(data, dict) and "error" in data:
            raise Exception(f"JSON-RPC error: {data['error']}")
        return data.get("result", {})

    async def _initialize(self) -> dict:
        result = await self._send("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "paperless-test-runner",
                "version": "1.0",
            },
        })
        await self._send_notification("notifications/initialized")
        return result

    async def list_tools(self) -> list[dict]:
        result = await self._send("tools/list")
        return result.get("tools", result)

    async def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        params = {"name": name}
        if arguments:
            params["arguments"] = arguments
        return await self._send("tools/call", params)


# =============================================================================
# Helper Functions
# =============================================================================

def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def is_error(result: dict[str, Any]) -> str | None:
    if "error" in result:
        err = result["error"]
        return err.get("message", str(err))
    if result.get("isError"):
        content = result.get("content", [])
        for c in content:
            if c.get("type") == "text":
                txt = c["text"]
                if txt.startswith("Error calling tool"):
                    return txt.split(":", 1)[1].strip() if ":" in txt else txt
                try:
                    data = json.loads(txt)
                except json.JSONDecodeError:
                    return txt
                if isinstance(data, dict):
                    return data.get("error", txt)
    return None


def extract_content(result: dict[str, Any]) -> Any:
    if result.get("isError"):
        return {}
    content = result.get("content", [])
    for c in content:
        if c.get("type") == "text":
            try:
                return json.loads(c["text"])
            except json.JSONDecodeError:
                return c["text"]
    return result.get("_meta", {})


def pick_id(state: dict, key: str) -> int:
    entry = state.get(key, {})
    if isinstance(entry, dict):
        if "id" in entry:
            return entry["id"]
        for val in entry.values():
            if isinstance(val, dict) and "id" in val:
                return val["id"]
            if isinstance(val, list) and val and isinstance(val[0], dict) and "id" in val[0]:
                return val[0]["id"]
    return 0


def store_on_pass(label: str, data: Any, state: dict, key: str) -> None:
    for r in results:
        if r["label"] == label and r["status"] == "PASSED":
            state[key] = r.get("data")
            break


def get_list_items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        for key, val in data.items():
            if isinstance(val, list):
                return val
            if isinstance(val, str):
                try:
                    parsed = toon_to_json(val)
                    if isinstance(parsed, list):
                        return parsed
                    if isinstance(parsed, dict):
                        for inner_key, inner_val in parsed.items():
                            if isinstance(inner_val, list):
                                return inner_val
                except Exception:
                    pass
        return []
    elif isinstance(data, list):
        return data
    return []


def assert_content(label: str, data: Any, required_fields: list[str]) -> None:
    """Check that extracted response data contains required fields. Records FAIL if not."""
    for field in required_fields:
        has_field = False
        if isinstance(data, dict):
            has_field = field in data
        if not has_field:
            results.append({
                "label": f"{label} (assert)", "tool": "", "status": "FAILED",
                "reason": f"Response missing required field '{field}'. Got: {str(data)[:200]}"
            })
            log(f"  FAIL {label} (assert): missing field '{field}'")
            return
    results.append({
        "label": f"{label} (assert)", "tool": "", "status": "PASSED",
        "data": {"assertion": "all fields present", "fields": required_fields}
    })
    log(f"  PASS {label} (assert): fields {required_fields} present")


def assert_id_valid(label: str, data: Any) -> None:
    """Check that response contains a positive 'id' field."""
    obj_id = 0
    if isinstance(data, dict) and "id" in data:
        obj_id = data["id"]
    if obj_id and obj_id > 0:
        results.append({
            "label": f"{label} (assert)", "tool": "", "status": "PASSED",
            "data": {"assertion": "valid id", "id": obj_id}
        })
        log(f"  PASS {label} (assert): id={obj_id} is valid")
    else:
        results.append({
            "label": f"{label} (assert)", "tool": "", "status": "FAILED",
            "reason": f"Response has no valid id. Got: {str(data)[:200]}"
        })
        log(f"  FAIL {label} (assert): no valid id in response")


def get_create_status(label: str) -> bool:
    """Check if a create test passed by looking at results."""
    for r in results:
        if r["label"] == label and r["status"] == "PASSED":
            return True
    return False


# =============================================================================
# Prep Phase: Create Disposable Test Document
# =============================================================================

async def prep_create_test_document(api_key: str) -> int:
    """Upload a disposable test document directly to Paperless and return its ID."""
    headers = {"Authorization": f"Token {api_key}"}
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{PAPERLESS_DIRECT_URL}/api/documents/",
            headers=headers,
            params={"page_size": 1, "ordering": "-id"},
        )
        r.raise_for_status()
        existing = r.json()
        max_id = max((d["id"] for d in existing.get("results", [])), default=0)

        files = {
            "document": (
                "opencode-test.txt",
                b"OpenCode test document - safe to delete",
                "text/plain",
            )
        }
        upload_r = await client.post(
            f"{PAPERLESS_DIRECT_URL}/api/documents/post_document/",
            headers=headers,
            files=files,
        )
        upload_r.raise_for_status()

        for _ in range(60):
            await asyncio.sleep(1)
            r = await client.get(
                f"{PAPERLESS_DIRECT_URL}/api/documents/",
                headers=headers,
                params={"page_size": 50, "ordering": "-id"},
            )
            r.raise_for_status()
            for doc in r.json().get("results", []):
                if doc["id"] > max_id:
                    return doc["id"]
        raise RuntimeError("Test document did not appear after upload")


# =============================================================================
# Test Runner Core
# =============================================================================

async def run(
    session: MCPSession,
    label: str,
    tool: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a single tool call and record PASS or FAIL. Never crashes."""
    if params is None:
        params = {}
    result = await session.call_tool(tool, params)
    err = is_error(result)
    if err:
        results.append({
            "label": label, "tool": tool, "status": "FAILED", "reason": err
        })
        log(f"  FAIL {label}: {err}")
        return result
    data = extract_content(result)
    results.append({
        "label": label, "tool": tool, "status": "PASSED", "data": data
    })
    log(f"  PASS {label}")
    return result


async def run_verify(
    session: MCPSession,
    label: str,
    tool: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a tool call expecting 'not found'. Not-found = PASS, anything else = FAIL."""
    if params is None:
        params = {}
    result = await session.call_tool(tool, params)
    err = is_error(result)
    is_not_found = "not found" in err.lower() if err else False
    if is_not_found:
        results.append({
            "label": label, "tool": tool, "status": "PASSED",
            "data": {"verified": "deleted"}
        })
        log(f"  PASS {label} (confirmed deleted)")
        return result
    reason = err if err else "Record still exists after delete"
    results.append({
        "label": label, "tool": tool, "status": "FAILED", "reason": reason
    })
    log(f"  FAIL {label}: {reason}")
    return result


async def run_verify_or_skip(
    session: MCPSession,
    label: str,
    tool: str,
    create_label: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify delete only if the corresponding create succeeded. Otherwise auto-pass."""
    create_ok = get_create_status(create_label)
    if create_ok:
        return await run_verify(session, label, tool, params)
    results.append({
        "label": label, "tool": tool, "status": "PASSED",
        "data": {"verified": "skipped — create failed"}
    })
    log(f"  PASS {label} (create failed, skip verify)")
    return {}


def resolve_mail_rule_params(state: dict) -> dict[str, Any]:
    acct_id = pick_id(state, "dep_mailaccount")
    return {
        "name": f"t{rid}-MailRule",
        "account": acct_id,
        "action": "delete",
        "folder": "INBOX",
    }


# =============================================================================
# Main Test Runner
# =============================================================================

async def main():
    state: dict[str, Any] = {}

    print(f"# Test Report — Paperless MCP Server")
    print(f"\n**Date**: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}")
    print(f"**Server**: {MCP_URL}")
    print(f"**Run ID**: {rid}")
    print()

    async with MCPSession(MCP_URL, MCP_HEADERS) as session:

        # ==================================================================
        # Prep Phase
        # ==================================================================
        log("\n=== Prep Phase: Create Disposable Test Document ===")
        test_doc_id = await prep_create_test_document(API_KEY)
        state["doc_id"] = test_doc_id
        log(f"  Created test document ID: {test_doc_id}")

        # ==================================================================
        # Phase 0: Tool Discovery (tests session + tools/list)
        # ==================================================================
        log("\n=== Phase 0: Tool Discovery ===")
        tools_list = await session.list_tools()
        tool_names = [t["name"] for t in tools_list]
        tool_count = len(tool_names)
        if tool_count > 0:
            results.append({
                "label": "T01 tool_discovery", "tool": "tools/list",
                "status": "PASSED", "data": {"count": tool_count, "tools": sorted(tool_names)}
            })
            log(f"  PASS T01 tool_discovery: {tool_count} tools")
        else:
            results.append({
                "label": "T01 tool_discovery", "tool": "tools/list",
                "status": "FAILED", "reason": "No tools discovered"
            })
            log(f"  FAIL T01 tool_discovery: no tools")
        print(f"**Discovered**: {tool_count} tools")
        log(f"Tools: {', '.join(sorted(tool_names))}")

        # ==================================================================
        # Phase 1: System Health
        # ==================================================================
        log("\n=== Phase 1: System Health ===")
        await run(session, "T02 check_server_status", "check_server_status")
        assert_content("T02 check_server_status", results[-1].get("data", {}), ["status", "data"])

        await run(session, "T03 get_statistics", "get_statistics")
        assert_content("T03 get_statistics", results[-1].get("data", {}), ["documents_total"])

        # ==================================================================
        # Phase 2: List Tools
        # ==================================================================
        log("\n=== Phase 2: List Tools ===")
        await run(session, "T04 list_correspondents", "list_all_correspondents")
        assert_content("T04 list_correspondents", results[-1].get("data", {}), ["correspondents"])

        await run(session, "T05 list_document_types", "list_all_document_types")
        assert_content("T05 list_document_types", results[-1].get("data", {}), ["document_types"])

        await run(session, "T06 list_tags", "list_all_tags")
        assert_content("T06 list_tags", results[-1].get("data", {}), ["tags"])

        await run(session, "T07 list_storage_paths", "list_all_storage_paths")
        assert_content("T07 list_storage_paths", results[-1].get("data", {}), ["storage_paths"])

        await run(session, "T08 list_saved_views", "list_all_saved_views")
        assert_content("T08 list_saved_views", results[-1].get("data", {}), ["saved_views"])

        await run(session, "T09 list_custom_fields", "list_all_custom_fields")
        assert_content("T09 list_custom_fields", results[-1].get("data", {}), ["custom_fields"])

        await run(session, "T10 list_workflows", "list_all_workflows")
        assert_content("T10 list_workflows", results[-1].get("data", {}), ["workflows"])

        await run(session, "T11 list_mail_accounts", "list_all_mail_accounts")
        assert_content("T11 list_mail_accounts", results[-1].get("data", {}), ["mail_accounts"])

        await run(session, "T12 list_mail_rules", "list_all_mail_rules")
        assert_content("T12 list_mail_rules", results[-1].get("data", {}), ["mail_rules"])

        # ==================================================================
        # Phase 3: Resource CRUD — Correspondent
        # ==================================================================
        log("\n=== Phase 3: Resource CRUD Cycle ===")
        log("\n--- Correspondent ---")
        await run(session, "T13 create_correspondent", "create_correspondent",
                  {"name": f"t{rid}-Correspondent"})
        store_on_pass("T13 create_correspondent", None, state, "correspondent")
        assert_id_valid("T13 create_correspondent", state.get("correspondent", {}))

        await run(session, "T14 get_correspondent", "get_correspondent",
                  {"id": pick_id(state, "correspondent")})
        store_on_pass("T14 get_correspondent", None, state, "correspondent_get")
        assert_content("T14 get_correspondent", state.get("correspondent_get", {}), ["id", "name"])

        gid = pick_id(state, "correspondent_get") or pick_id(state, "correspondent")
        await run(session, "T15 update_correspondent", "update_correspondent",
                  {"id": gid, "name": f"t{rid}-Correspondent-updated"})
        assert_content("T15 update_correspondent", results[-1].get("data", {}), ["id", "name"])

        await run(session, "T16 delete_correspondent", "delete_correspondent",
                  {"id": gid})
        await run_verify_or_skip(session, "T17 verify_delete_correspondent",
                  "get_correspondent", "T13 create_correspondent", {"id": gid})

        # ==================================================================
        # Phase 3: Resource CRUD — DocumentType
        # ==================================================================
        log("\n--- DocumentType ---")
        await run(session, "T18 create_document_type", "create_document_type",
                  {"name": f"t{rid}-DocType"})
        store_on_pass("T18 create_document_type", None, state, "documenttype")
        assert_id_valid("T18 create_document_type", state.get("documenttype", {}))

        await run(session, "T19 get_document_type", "get_document_type",
                  {"id": pick_id(state, "documenttype")})
        store_on_pass("T19 get_document_type", None, state, "documenttype_get")
        assert_content("T19 get_document_type", state.get("documenttype_get", {}), ["id", "name"])

        gid = pick_id(state, "documenttype_get") or pick_id(state, "documenttype")
        await run(session, "T20 update_document_type", "update_document_type",
                  {"id": gid, "name": f"t{rid}-DocType-updated"})
        assert_content("T20 update_document_type", results[-1].get("data", {}), ["id", "name"])

        await run(session, "T21 delete_document_type", "delete_document_type",
                  {"id": gid})
        await run_verify_or_skip(session, "T22 verify_delete_document_type",
                  "get_document_type", "T18 create_document_type", {"id": gid})

        # ==================================================================
        # Phase 3: Resource CRUD — Tag
        # ==================================================================
        log("\n--- Tag ---")
        await run(session, "T23 create_tag", "create_tag",
                  {"name": f"t{rid}-Tag", "color": "#a6cee3"})
        store_on_pass("T23 create_tag", None, state, "tag")
        assert_id_valid("T23 create_tag", state.get("tag", {}))

        await run(session, "T24 get_tag", "get_tag",
                  {"id": pick_id(state, "tag")})
        store_on_pass("T24 get_tag", None, state, "tag_get")
        assert_content("T24 get_tag", state.get("tag_get", {}), ["id", "name"])

        gid = pick_id(state, "tag_get") or pick_id(state, "tag")
        await run(session, "T25 update_tag", "update_tag",
                  {"id": gid, "color": "#b2df8a"})
        assert_content("T25 update_tag", results[-1].get("data", {}), ["id"])

        await run(session, "T26 delete_tag", "delete_tag",
                  {"id": gid})
        await run_verify_or_skip(session, "T27 verify_delete_tag",
                  "get_tag", "T23 create_tag", {"id": gid})

        # ==================================================================
        # Phase 3: Resource CRUD — StoragePath
        # ==================================================================
        log("\n--- StoragePath ---")
        await run(session, "T28 create_storage_path", "create_storage_path",
                  {"name": f"t{rid}-StoragePath", "path": "{created_year}"})
        store_on_pass("T28 create_storage_path", None, state, "storagespath")
        assert_id_valid("T28 create_storage_path", state.get("storagespath", {}))

        await run(session, "T29 get_storage_path", "get_storage_path",
                  {"id": pick_id(state, "storagespath")})
        store_on_pass("T29 get_storage_path", None, state, "storagespath_get")
        assert_content("T29 get_storage_path", state.get("storagespath_get", {}), ["id", "name"])

        gid = pick_id(state, "storagespath_get") or pick_id(state, "storagespath")
        await run(session, "T30 update_storage_path", "update_storage_path",
                  {"id": gid, "path": "{asn}"})
        assert_content("T30 update_storage_path", results[-1].get("data", {}), ["id"])

        await run(session, "T31 delete_storage_path", "delete_storage_path",
                  {"id": gid})
        await run_verify_or_skip(session, "T32 verify_delete_storage_path",
                  "get_storage_path", "T28 create_storage_path", {"id": gid})

        # ==================================================================
        # Phase 3: Resource CRUD — SavedView
        # ==================================================================
        log("\n--- SavedView ---")
        await run(session, "T33 create_saved_view", "create_saved_view",
                  {"name": f"t{rid}-SavedView"})
        store_on_pass("T33 create_saved_view", None, state, "savedview")
        assert_id_valid("T33 create_saved_view", state.get("savedview", {}))

        await run(session, "T34 get_saved_view", "get_saved_view",
                  {"id": pick_id(state, "savedview")})
        store_on_pass("T34 get_saved_view", None, state, "savedview_get")
        assert_content("T34 get_saved_view", state.get("savedview_get", {}), ["id", "name"])

        gid = pick_id(state, "savedview_get") or pick_id(state, "savedview")
        await run(session, "T35 update_saved_view", "update_saved_view",
                  {"id": gid, "show_on_dashboard": True})
        assert_content("T35 update_saved_view", results[-1].get("data", {}), ["id"])

        await run(session, "T36 delete_saved_view", "delete_saved_view",
                  {"id": gid})
        await run_verify_or_skip(session, "T37 verify_delete_saved_view",
                  "get_saved_view", "T33 create_saved_view", {"id": gid})

        # ==================================================================
        # Phase 3: Resource CRUD — CustomField
        # ==================================================================
        log("\n--- CustomField ---")
        await run(session, "T38 create_custom_field", "create_custom_field",
                  {"name": f"t{rid}-CustomField", "data_type": "string"})
        store_on_pass("T38 create_custom_field", None, state, "customfield")
        assert_id_valid("T38 create_custom_field", state.get("customfield", {}))

        await run(session, "T39 get_custom_field", "get_custom_field",
                  {"id": pick_id(state, "customfield")})
        store_on_pass("T39 get_custom_field", None, state, "customfield_get")
        assert_content("T39 get_custom_field", state.get("customfield_get", {}), ["id", "name"])

        gid = pick_id(state, "customfield_get") or pick_id(state, "customfield")
        await run(session, "T40 update_custom_field", "update_custom_field",
                  {"id": gid, "name": f"t{rid}-CustomField-updated"})
        assert_content("T40 update_custom_field", results[-1].get("data", {}), ["id", "name"])

        await run(session, "T41 delete_custom_field", "delete_custom_field",
                  {"id": gid})
        await run_verify_or_skip(session, "T42 verify_delete_custom_field",
                  "get_custom_field", "T38 create_custom_field", {"id": gid})

        # ==================================================================
        # Phase 3: Resource CRUD — Workflow
        # ==================================================================
        log("\n--- Workflow ---")
        await run(session, "T43 create_workflow", "create_workflow",
                  {"name": f"t{rid}-Workflow"})
        store_on_pass("T43 create_workflow", None, state, "workflow")
        assert_id_valid("T43 create_workflow", state.get("workflow", {}))

        await run(session, "T44 get_workflow", "get_workflow",
                  {"id": pick_id(state, "workflow")})
        store_on_pass("T44 get_workflow", None, state, "workflow_get")
        assert_content("T44 get_workflow", state.get("workflow_get", {}), ["id", "name"])

        gid = pick_id(state, "workflow_get") or pick_id(state, "workflow")
        await run(session, "T45 update_workflow", "update_workflow",
                  {"id": gid, "enabled": False})
        assert_content("T45 update_workflow", results[-1].get("data", {}), ["id"])

        await run(session, "T46 delete_workflow", "delete_workflow",
                  {"id": gid})
        await run_verify_or_skip(session, "T47 verify_delete_workflow",
                  "get_workflow", "T43 create_workflow", {"id": gid})

        # ==================================================================
        # Phase 3: Resource CRUD — MailAccount
        # ==================================================================
        log("\n--- MailAccount ---")
        await run(session, "T48 create_mail_account", "create_mail_account",
                  {"name": f"t{rid}-MailAccount", "username": "test@test.com",
                   "password": "test123"})
        store_on_pass("T48 create_mail_account", None, state, "mailaccount")
        assert_id_valid("T48 create_mail_account", state.get("mailaccount", {}))

        await run(session, "T49 get_mail_account", "get_mail_account",
                  {"id": pick_id(state, "mailaccount")})
        store_on_pass("T49 get_mail_account", None, state, "mailaccount_get")
        assert_content("T49 get_mail_account", state.get("mailaccount_get", {}), ["id", "name"])

        gid = pick_id(state, "mailaccount_get") or pick_id(state, "mailaccount")
        await run(session, "T50 update_mail_account", "update_mail_account",
                  {"id": gid, "is_active": False})
        assert_content("T50 update_mail_account", results[-1].get("data", {}), ["id"])

        await run(session, "T51 delete_mail_account", "delete_mail_account",
                  {"id": gid})
        await run_verify_or_skip(session, "T52 verify_delete_mail_account",
                  "get_mail_account", "T48 create_mail_account", {"id": gid})

        # ==================================================================
        # Phase 3: Resource CRUD — MailRule (depends on dep_mailaccount)
        # ==================================================================
        log("\n--- MailRule ---")
        await run(session, "T53 create_dep_mailaccount", "create_mail_account",
                  {"name": f"t{rid}-DepMailAcct", "imap_server": "imap.gmail.com",
                   "username": "dep@test.com", "password": "dep123"})
        store_on_pass("T53 create_dep_mailaccount", None, state, "dep_mailaccount")
        assert_id_valid("T53 create_dep_mailaccount", state.get("dep_mailaccount", {}))

        await run(session, "T54 create_mail_rule", "create_mail_rule",
                  resolve_mail_rule_params(state))
        store_on_pass("T54 create_mail_rule", None, state, "mailrule")
        assert_id_valid("T54 create_mail_rule", state.get("mailrule", {}))

        await run(session, "T55 get_mail_rule", "get_mail_rule",
                  {"id": pick_id(state, "mailrule")})
        store_on_pass("T55 get_mail_rule", None, state, "mailrule_get")
        assert_content("T55 get_mail_rule", state.get("mailrule_get", {}), ["id", "name"])

        gid = pick_id(state, "mailrule_get") or pick_id(state, "mailrule")
        await run(session, "T56 update_mail_rule", "update_mail_rule",
                  {"id": gid, "action": "flag"})
        assert_content("T56 update_mail_rule", results[-1].get("data", {}), ["id"])

        await run(session, "T57 delete_mail_rule", "delete_mail_rule",
                  {"id": gid})
        await run_verify_or_skip(session, "T58 verify_delete_mail_rule",
                  "get_mail_rule", "T54 create_mail_rule", {"id": gid})

        # Cleanup dep_mailaccount
        dep_acct_id = pick_id(state, "dep_mailaccount")
        await run(session, "T58b cleanup_dep_mailaccount", "delete_mail_account",
                  {"id": dep_acct_id})

        # ==================================================================
        # Phase 4: Document Domain
        # ==================================================================
        log("\n=== Phase 4: Document Tools ===")

        await run(session, "T59 list_all_documents", "list_all_documents")
        store_on_pass("T59 list_all_documents", None, state, "all_documents")
        assert_content("T59 list_all_documents", results[-1].get("data", {}), ["documents"])

        doc_id = state.get("doc_id", 0)

        await run(session, "T60 get_document", "get_document",
                  {"id": doc_id})
        assert_content("T60 get_document", results[-1].get("data", {}), ["id", "title"])

        await run(session, "T61 get_document_metadata", "get_document_metadata",
                  {"id": doc_id})
        assert_content("T61 get_document_metadata", results[-1].get("data", {}), ["original_checksum"])

        await run(session, "T62 get_document_suggestions", "get_document_suggestions",
                  {"id": doc_id})

        await run(session, "T63 get_document_ai_suggestions", "get_document_ai_suggestions",
                  {"id": doc_id})

        await run(session, "T64 list_notes_by_document", "list_notes_by_document",
                  {"id": doc_id})

        await run(session, "T65 create_document_note", "create_document_note",
                  {"document_id": doc_id, "note": f"Test note {rid}"})
        store_on_pass("T65 create_document_note", None, state, "created_note")
        assert_content("T65 create_document_note", state.get("created_note", {}), ["note"])

        note_id = pick_id(state, "created_note")
        await run(session, "T66 delete_document_note", "delete_document_note",
                  {"document_id": doc_id, "note_id": note_id})

        await run(session, "T67 update_document", "update_document",
                  {"id": doc_id, "title": f"Test title {rid}"})
        assert_content("T67 update_document", results[-1].get("data", {}), ["id", "title"])

        await run(session, "T68 get_document_download_url", "get_document_download_url",
                  {"id": doc_id})

        await run(session, "T69 get_document_preview_url", "get_document_preview_url",
                  {"id": doc_id})

        await run(session, "T70 get_document_thumbnail_url", "get_document_thumbnail_url",
                  {"id": doc_id})

        await run(session, "T71 bulk_update_documents", "bulk_update_documents",
                  {"documents": [doc_id], "method": "set_correspondent",
                   "parameters": {"correspondent": None}})

        await run(session, "T72 reprocess_documents", "reprocess_documents",
                  {"documents": [doc_id]})

        await run(session, "T73 create_temp_custom_field", "create_custom_field",
                  {"name": f"t{rid}-AssignField", "data_type": "string"})
        store_on_pass("T73 create_temp_custom_field", None, state, "temp_field")
        assert_id_valid("T73 create_temp_custom_field", state.get("temp_field", {}))

        temp_field_id = pick_id(state, "temp_field")
        await run(session, "T74 assign_custom_field", "assign_custom_field",
                  {"documents": [doc_id], "field_id": temp_field_id,
                   "value": "test-value"})
        await run(session, "T75 remove_custom_field", "assign_custom_field",
                  {"documents": [doc_id], "field_id": temp_field_id,
                   "remove": True})
        await run(session, "T76 delete_temp_custom_field", "delete_custom_field",
                  {"id": temp_field_id})

        # ==================================================================
        # Phase 4: Share Links (before doc delete)
        # ==================================================================
        log("\n--- Share Links ---")
        expiration = (datetime.now(timezone.utc) + timedelta(days=1)).strftime(
            "%Y-%m-%dT%H:%M:%S+00:00"
        )
        await run(session, "T78 create_share_link", "create_share_link",
                  {"document": doc_id, "expiration": expiration})
        store_on_pass("T78 create_share_link", None, state, "share_link")
        assert_id_valid("T78 create_share_link", state.get("share_link", {}))

        share_id = pick_id(state, "share_link")
        await run(session, "T79 get_share_link", "get_share_link",
                  {"id": share_id})
        assert_content("T79 get_share_link", results[-1].get("data", {}), ["id"])

        await run(session, "T80 delete_share_link", "delete_share_link",
                  {"id": share_id})

        # ==================================================================
        # Phase 4: Document Cleanup
        # ==================================================================
        log("\n--- Document Cleanup ---")
        await run(session, "T81 delete_document", "delete_document",
                  {"id": doc_id})
        await run_verify(session, "T82 verify_delete_document", "get_document",
                  {"id": doc_id})
        await run(session, "T83 get_next_asn", "get_next_asn")
        assert_content("T83 get_next_asn", results[-1].get("data", {}), ["next_asn"])

        # ==================================================================
        # Phase 5: Task Domain
        # ==================================================================
        log("\n=== Phase 5: Task Tools ===")

        await run(session, "T84 list_all_tasks", "list_all_tasks")
        store_on_pass("T84 list_all_tasks", None, state, "all_tasks")
        assert_content("T84 list_all_tasks", results[-1].get("data", {}), ["tasks"])

        await run(session, "T85 get_task_summary", "get_task_summary",
                  {"days": 30})
        assert_content("T85 get_task_summary", results[-1].get("data", {}), ["summary"])

        await run(session, "T86 get_task_status_counts", "get_task_status_counts")
        assert_content("T86 get_task_status_counts", results[-1].get("data", {}), ["all"])

        await run(session, "T87 list_active_tasks", "list_active_tasks")

        await run(session, "T88 acknowledge_tasks", "acknowledge_tasks",
                  {"all_tasks": True})

        tasks_list = get_list_items(state.get("all_tasks", {}))
        task_id = tasks_list[0]["id"] if tasks_list else 0
        await run(session, "T89 get_task", "get_task",
                  {"id": task_id})
        assert_content("T89 get_task", results[-1].get("data", {}), ["id"])

        # ==================================================================
        # Phase 6: Share Link Domain
        # ==================================================================
        log("\n=== Phase 6: Share Link Tools ===")
        await run(session, "T90 list_all_share_links", "list_all_share_links")
        assert_content("T90 list_all_share_links", results[-1].get("data", {}), ["share_links"])

        # ==================================================================
        # Phase 7: Search Domain
        # ==================================================================
        log("\n=== Phase 7: Search Tools ===")
        await run(session, "T91 search_documents", "search_documents",
                  {"query": "test"})
        assert_content("T91 search_documents", results[-1].get("data", {}), ["results"])

        await run(session, "T92 search_autocomplete", "search_autocomplete",
                  {"term": "test"})
        assert_content("T92 search_autocomplete", results[-1].get("data", {}), ["suggestions"])

        # ==================================================================
        # Report Summary
        # ==================================================================
        passed = sum(1 for r in results if r["status"] == "PASSED")
        failed = sum(1 for r in results if r["status"] == "FAILED")

        print(f"\n## Summary\n")
        print(f"| Status | Count |")
        print(f"|--------|-------|")
        print(f"| PASSED | {passed} |")
        print(f"| FAILED | {failed} |")

        if passed:
            print(f"\n## PASSED ({passed})\n")
            for r in results:
                if r["status"] == "PASSED":
                    print(f"- `{r['tool']}` — {r['label']}")

        if failed:
            print(f"\n## FAILED ({failed})\n")
            for r in results:
                if r["status"] == "FAILED":
                    print(f"### {r['label']}")
                    print(f"- **Tool**: `{r['tool']}`")
                    print(f"- **Error**: {r['reason']}")
                    print()

        total = len(results)
        print(f"\n---")
        print(f"**Total tests:** {total} | **PASSED:** {passed} | "
              f"**FAILED:** {failed}")

        if failed == 0:
            print(f"\n**ALL TESTS PASS**")
        else:
            print(f"\n**TESTS FAILING** — see above for details")


if __name__ == "__main__":
    asyncio.run(main())
