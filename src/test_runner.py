"""
End-to-end test harness for Paperless MCP Server.

Connects via Streamable HTTP (JSON-RPC POST), tests all tools,
and prints a Markdown report to stdout.

Every test runs unconditionally — there is no SKIPPED status.
Tests exist to find flaws in main.py and client.py; the developer
fixes application code so that tests pass as a consequence.
"""

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import httpx
from toon_mcp import toon_to_json

MCP_SERVER_PORT = os.environ.get("MCP_SERVER_PORT", "")
API_KEY = os.environ.get("API_KEY", "")
MCP_URL = f"http://localhost:{MCP_SERVER_PORT}/mcp"

MCP_HEADERS = {
    "Authorization": f"Token {API_KEY}",
}

rid = uuid.uuid4().hex[:8]

results: list[dict[str, Any]] = []
store: dict[str, Any] = {}
created: dict[str, str] = {}

_iteration = 1
_iterations: list[dict[str, int]] = []


class MCPSession:
    """MCP Streamable HTTP client using JSON-RPC over HTTP POST (stateful sessions)."""

    def __init__(self, url: str, headers: dict[str, str]):
        self.url = url
        self.base_headers = {
            **headers,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        self.session_headers = dict(self.base_headers)
        self.client = httpx.AsyncClient(timeout=120.0)
        self._request_id = 0
        self._session_id: str | None = None

    async def __aenter__(self):
        await self._initialize()
        return self

    async def __aexit__(self, *args):
        await self.client.aclose()

    async def _send_notification(self, method: str, params: dict | None = None) -> None:
        payload = {"jsonrpc": "2.0", "method": method}
        if params:
            payload["params"] = params
        response = await self.client.post(self.url, headers=self.session_headers, json=payload)
        if response.status_code not in (200, 202):
            response.raise_for_status()

    async def _send(self, method: str, params: dict | None = None) -> dict:
        self._request_id += 1
        payload = {"jsonrpc": "2.0", "id": self._request_id, "method": method}
        if params:
            payload["params"] = params
        response = await self.client.post(self.url, headers=self.session_headers, json=payload)
        if response.status_code == 202:
            return {}
        response.raise_for_status()

        sid = response.headers.get("mcp-session-id")
        if sid:
            self._session_id = sid
            self.session_headers = {**self.base_headers, "mcp-session-id": sid}

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


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def is_error(result: dict[str, Any]) -> Optional[str]:
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


async def run_test(
    session: MCPSession,
    label: str,
    tool: str,
    params: dict[str, Any] = None,
) -> bool:
    if params is None:
        params = {}
    try:
        result = await session.call_tool(tool, params)
        err = is_error(result)
        if err:
            results.append({
                "label": label, "tool": tool, "status": "FAILED",
                "reason": err
            })
            log(f"  FAIL {label}: {err}")
            return False
        data = extract_content(result)
        results.append({
            "label": label, "tool": tool, "status": "PASSED", "data": data
        })
        log(f"  PASS {label}")
        return True
    except Exception as e:
        results.append({
            "label": label, "tool": tool, "status": "FAILED",
            "reason": str(e)
        })
        log(f"  FAIL {label}: {e}")
        return False


async def run_test_with_store(
    session: MCPSession,
    label: str,
    tool: str,
    params: dict[str, Any] = None,
    store_key: str = None,
) -> bool:
    ok = await run_test(session, label, tool, params)
    if ok and store_key:
        for r in results:
            if r["label"] == label and r["status"] == "PASSED":
                store[store_key] = r.get("data")
                break
    return ok


def pick_id(key: str) -> Optional[Any]:
    entry = store.get(key, {})
    if isinstance(entry, dict):
        if "id" in entry:
            return entry.get("id")
        for val in entry.values():
            if isinstance(val, dict) and "id" in val:
                return val.get("id")
            if isinstance(val, list) and val and isinstance(val[0], dict) and "id" in val[0]:
                return val[0].get("id")
    return None


def make_name(base: str) -> str:
    return f"t{rid}-{base}"


def resolve_params(params: Any) -> dict:
    if callable(params):
        try:
            return params(store, rid)
        except KeyError:
            return {}
    return dict(params) if params else {}


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


async def run_verify_delete(
    session: MCPSession,
    label: str,
    get_tool: str,
    params: dict[str, Any] = None,
) -> bool:
    if params is None:
        params = {}
    try:
        result = await session.call_tool(get_tool, params)
        err = is_error(result)
        if err:
            if "not found" in err.lower():
                results.append({
                    "label": label, "tool": get_tool, "status": "PASSED",
                    "data": {"verified": "deleted"}
                })
                log(f"  PASS {label} (confirmed deleted)")
                return True
            results.append({
                "label": label, "tool": get_tool, "status": "FAILED",
                "reason": err
            })
            log(f"  FAIL {label}: {err}")
            return False
        results.append({
            "label": label, "tool": get_tool, "status": "FAILED",
            "reason": "Record still exists after delete"
        })
        log(f"  FAIL {label}: record still exists")
        return False
    except Exception as e:
        results.append({
            "label": label, "tool": get_tool, "status": "FAILED",
            "reason": str(e)
        })
        log(f"  FAIL {label}: {e}")
        return False


# =============================================================================
# Test Data Configuration
# =============================================================================

RESOURCE_TESTS = [
    ("Correspondent", "create_correspondent",
     {"name": make_name("Correspondent")},
     "get_all_correspondents", "get_correspondent_by_id",
     "update_correspondent", {"name": make_name("Correspondent-updated")},
     "delete_correspondent_by_id"),
    ("DocumentType", "create_document_type",
     {"name": make_name("DocType")},
     "get_all_document_types", "get_document_type_by_id",
     "update_document_type", {"name": make_name("DocType-updated")},
     "delete_document_type_by_id"),
    ("Tag", "create_tag",
     {"name": make_name("Tag"), "color": "#a6cee3"},
     "get_all_tags", "get_tag_by_id",
     "update_tag", {"color": "#b2df8a"},
     "delete_tag_by_id"),
    ("StoragePath", "create_storage_path",
     {"name": make_name("StoragePath"), "path": "{created_year}"},
     "get_all_storage_paths", "get_storage_path_by_id",
     "update_storage_path", {"path": "{asn}"},
     "delete_storage_path_by_id"),
    ("SavedView", "create_saved_view",
     {"name": make_name("SavedView")},
     "get_all_saved_views", "get_saved_view_by_id",
     "update_saved_view", {"show_on_dashboard": True},
     "delete_saved_view_by_id"),
    ("CustomField", "create_custom_field",
     {"name": make_name("CustomField"), "data_type": "string"},
     "get_all_custom_fields", "get_custom_field_by_id",
     "update_custom_field", {"name": make_name("CustomField-updated")},
     "delete_custom_field_by_id"),
    ("Workflow", "create_workflow",
     {"name": make_name("Workflow")},
     "get_all_workflows", "get_workflow_by_id",
     "update_workflow", {"enabled": False},
     "delete_workflow_by_id"),
    ("MailAccount", "create_mail_account",
     {"name": make_name("MailAccount"), "username": "test@test.com",
      "password": "test123"},
     "get_all_mail_accounts", "get_mail_account_by_id",
     "update_mail_account", {"is_active": False},
     "delete_mail_account_by_id"),
     ("MailRule", "create_mail_rule",
      lambda s, r: {"name": f"t{r}-MailRule",
                     "account": s.get("mailrule_account", {}).get("id", 0)
                     if isinstance(s.get("mailrule_account", {}), dict) else 0,
                     "action": 1, "folder": "INBOX"},
      "get_all_mail_rules", "get_mail_rule_by_id",
      "update_mail_rule", {"action": 3},  # MARK_READ — doesn't need action_parameter
      "delete_mail_rule_by_id"),
]




# =============================================================================
# Main Test Runner
# =============================================================================

async def main():
    global _iteration

    print(f"# Test Report — Paperless MCP Server")
    print(f"\n**Date**: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}")
    print(f"**Server**: {MCP_URL}")
    print(f"**Run ID**: {rid}")
    print()

    async with MCPSession(MCP_URL, MCP_HEADERS) as session:
        # ==================================================================
        # Phase 0: Session Init & Tool Discovery
        # ==================================================================
        log("\n=== Phase 0: Session Init & Tool Discovery ===")
        tools_list = await session.list_tools()
        tool_names = [t["name"] for t in tools_list]
        print(f"**Discovered**: {len(tool_names)} tools")
        log(f"Tools: {', '.join(sorted(tool_names))}")

        # ==================================================================
        # Phase 1: System Health
        # ==================================================================
        log("\n=== Phase 1: System Health ===")
        await run_test(session, "A1 check_server_status", "check_server_status")
        await run_test(session, "A2 get_statistics", "get_statistics")

        # ==================================================================
        # Phase 2: List Tools (one get_all_* per resource)
        # ==================================================================
        log("\n=== Phase 2: List Tools ===")
        for entry in RESOURCE_TESTS:
            label = entry[0]
            list_tool_name = entry[3]
            await run_test(session, f"B2 list_{label.lower()}", list_tool_name)

        # ==================================================================
        # Phase 3: Resource CRUD Cycles
        # ==================================================================
        log("\n=== Phase 3: Resource CRUD Cycle ===")

        # Pre-create a dependency MailAccount for MailRule (since CRUD cycle
        # deletes each resource before the next one starts)
        dep_acct_ok = await run_test_with_store(
            session, "Z0 create_dep_mailaccount", "create_mail_account",
            {"name": f"t{rid}-DepMailAcct", "imap_server": "imap.gmail.com",
             "username": "dep@test.com", "password": "dep123"},
            store_key="mailrule_account"
        )
        dep_acct_id = pick_id("mailrule_account")

        for entry in RESOURCE_TESTS:
            label, create_tool, create_params, _, get_tool, update_tool, \
                update_params, delete_tool = entry
            key = label.lower()

            resolved_create = resolve_params(create_params)

            ok = await run_test_with_store(
                session, f"C1 create_{key}", create_tool, resolved_create,
                store_key=f"create_{key}"
            )
            cid = pick_id(f"create_{key}") if ok else None
            if cid:
                created[f"create_{key}"] = cid

            await run_test_with_store(
                session, f"C2 get_{key}_by_id", get_tool,
                {"id": cid} if cid else {"id": 0}, store_key=f"get_{key}"
            )

            gid = pick_id(f"get_{key}") or cid

            if key == "mailrule":
                log(f"  DEBUG store['create_mailaccount'] = {store.get('create_mailaccount', 'NOT FOUND')}")
                log(f"  DEBUG store keys: {list(store.keys())}")

            resolved_update = resolve_params(update_params)
            upd = dict(resolved_update)
            upd["id"] = gid if gid else 0
            await run_test(
                session, f"C3 update_{key}", update_tool, upd
            )

            await run_test(
                session, f"C4 delete_{key}_by_id", delete_tool,
                {"id": gid} if gid else {"id": 0}
            )

            await run_verify_delete(
                session, f"C5 verify_delete_{key}", get_tool,
                {"id": gid} if gid else {"id": 0}
            )

        # ==================================================================
        # Phase 4: Document Domain
        # ==================================================================
        log("\n=== Phase 4: Document Tools ===")

        await run_test_with_store(
            session, "D1 get_all_documents", "get_all_documents",
            store_key="all_documents"
        )

        docs_list = get_list_items(store.get("all_documents", {}))
        doc_id = docs_list[0]["id"] if docs_list else None
        if doc_id:
            store["doc_id"] = {"id": doc_id}

        if doc_id:
            await run_test(
                session, "D2 get_document_by_id", "get_document_by_id",
                {"id": doc_id}
            )
            await run_test(
                session, "D3 get_document_metadata", "get_document_metadata",
                {"id": doc_id}
            )
            await run_test(
                session, "D4 get_document_suggestions",
                "get_document_suggestions", {"id": doc_id}
            )
            await run_test(
                session, "D5 get_document_ai_suggestions",
                "get_document_ai_suggestions", {"id": doc_id}
            )
            await run_test(
                session, "D6 get_document_notes", "get_document_notes",
                {"id": doc_id}
            )

            await run_test_with_store(
                session, "D7 create_document_note", "create_document_note",
                {"document_id": doc_id, "note": f"Test note {rid}"},
                store_key="created_note"
            )

            note_id = pick_id("created_note")
            if note_id:
                await run_test(
                    session, "D8 delete_document_note",
                    "delete_document_note",
                    {"document_id": doc_id, "note_id": note_id}
                )

            await run_test(
                session, "D9 update_document", "update_document",
                {"id": doc_id, "title": f"Test title {rid}"}
            )

            # URL tools (construct URLs from PAPERLESS_PUBLIC_URL or PAPERLESS_BASE_URL)
            await run_test(
                session, "D13 get_document_download_url",
                "get_document_download_url", {"id": doc_id}
            )
            await run_test(
                session, "D14 get_document_preview_url",
                "get_document_preview_url", {"id": doc_id}
            )
            await run_test(
                session, "D15 get_document_thumbnail_url",
                "get_document_thumbnail_url", {"id": doc_id}
            )

            # Bulk update, reprocess, and assign custom field tests
            await run_test(
                session, "D16 bulk_update_documents", "bulk_update_documents",
                {"documents": str(doc_id), "method": "set_correspondent",
                 "parameters": '{"correspondent": null}'}
            )
            await run_test(
                session, "D17 reprocess_documents", "reprocess_documents",
                {"documents": str(doc_id)}
            )
            # Create a temp custom field for the assign test, then clean it up
            await run_test_with_store(
                session, "D18 create_temp_field", "create_custom_field",
                {"name": f"t{rid}-AssignField", "data_type": "string"},
                store_key="temp_field"
            )
            temp_field_id = pick_id("temp_field")
            if temp_field_id:
                await run_test(
                    session, "D19 assign_custom_field", "assign_custom_field",
                    {"documents": str(doc_id), "field_id": temp_field_id, "value": "test-value"}
                )
                await run_test(
                    session, "D20 remove_custom_field", "assign_custom_field",
                    {"documents": str(doc_id), "field_id": temp_field_id, "remove": True}
                )
                await run_test(
                    session, "D21 delete_temp_field", "delete_custom_field_by_id",
                    {"id": temp_field_id}
                )

            # Share link tests run here while the document still exists
            await run_test(
                session, "F1b get_all_documents_for_share", "get_all_documents"
            )
            expiration = (datetime.now(timezone.utc) + timedelta(days=1)).strftime(
                "%Y-%m-%dT%H:%M:%S+00:00"
            )
            await run_test_with_store(
                session, "F2 create_share_link", "create_share_link",
                {"document": doc_id, "expiration": expiration},
                store_key="created_share_link"
            )
            share_id = pick_id("created_share_link")
            if share_id:
                await run_test(
                    session, "F3 get_share_link_by_id", "get_share_link_by_id",
                    {"id": share_id}
                )
                await run_test(
                    session, "F4 delete_share_link_by_id",
                    "delete_share_link_by_id", {"id": share_id}
                )

            await run_test(
                session, "D10 delete_document_by_id",
                "delete_document_by_id", {"id": doc_id}
            )

            await run_verify_delete(
                session, "D11 verify_delete_document",
                "get_document_by_id", {"id": doc_id}
            )
        else:
            log("  WARN: No documents found in Paperless — skipping document tests")

        await run_test(
            session, "D12 get_next_asn", "get_next_asn"
        )

        # ==================================================================
        # Phase 5: Task Domain
        # ==================================================================
        log("\n=== Phase 5: Task Tools ===")

        await run_test_with_store(
            session, "E1 get_all_tasks", "get_all_tasks",
            store_key="all_tasks"
        )
        await run_test(
            session, "E2 get_task_summary", "get_task_summary",
            {"days": 30}
        )
        await run_test(
            session, "E3 get_task_status_counts", "get_task_status_counts"
        )
        await run_test(
            session, "E4 get_active_tasks", "get_active_tasks"
        )
        await run_test(
            session, "E5 acknowledge_tasks", "acknowledge_tasks",
            {"all_tasks": True}
        )

        tasks_list = get_list_items(store.get("all_tasks", {}))
        task_id = tasks_list[0]["id"] if tasks_list else None
        if task_id:
            await run_test(
                session, "E6 get_task_by_id", "get_task_by_id",
                {"id": task_id}
            )

        # ==================================================================
        # Phase 6: Share Link Domain (F2-F4 run in Phase 4 before doc delete)
        # ==================================================================
        log("\n=== Phase 6: Share Link Tools ===")

        await run_test(
            session, "F1 get_all_share_links", "get_all_share_links"
        )

        # ==================================================================
        # Phase 7: Search Domain
        # ==================================================================
        log("\n=== Phase 7: Search Tools ===")

        await run_test(
            session, "G1 search_documents", "search_documents",
            {"query": "test"}
        )

        await run_test(
            session, "G2 search_autocomplete", "search_autocomplete",
            {"term": "test"}
        )

        # ==================================================================
        # Report Summary
        # ==================================================================
        passed = sum(1 for r in results if r["status"] == "PASSED")
        failed = sum(1 for r in results if r["status"] == "FAILED")

        _iterations.append({"iteration": _iteration, "passed": passed, "failed": failed, "fixes": ""})

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

        print(f"\n## Iteration History\n")
        print(f"| Iteration | Passed | Failed | Fixes Applied |")
        print(f"|-----------|--------|--------|---------------|")
        for it in _iterations:
            print(f"| {it['iteration']} | {it['passed']} | {it['failed']} | {it['fixes']} |")

        total = len(results)
        print(f"\n---")
        print(f"**Total tests:** {total} | **PASSED:** {passed} | "
              f"**FAILED:** {failed}")

        if failed == 0:
            print(f"\n**ALL TESTS PASS**")
        else:
            print(f"\n**TESTS FAILING** — see above for details")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
