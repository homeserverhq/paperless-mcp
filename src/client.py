import os
import datetime as dt
import re
from typing import Any, Optional

import httpx


def _normalize_datetime(value: str) -> str:
    if re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$', value):
        parsed = dt.datetime.fromisoformat(value)
        parsed = parsed.astimezone(dt.timezone.utc)
        return parsed.strftime('%Y-%m-%d %H:%M:%S')
    if re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', value):
        raise ValueError(
            f"Invalid datetime: {value}. Timezone offset is required. "
            "Must use format: 2026-06-22T15:00:00-04:00"
        )
    return value


DOCUMENT_COMMON_FIELDS = (
    "id,title,correspondent,document_type,storage_path,tags,"
    "created,created_date,modified,added,archive_serial_number,"
    "owner,page_count,mime_type"
)


class PaperlessClient:
    """Client for Paperless API with auth passthrough."""

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or os.getenv("PAPERLESS_BASE_URL", "")).rstrip("/")
        if not self.base_url:
            raise ValueError(
                "Paperless URL required. Set PAPERLESS_BASE_URL env var or pass base_url."
            )

    def _get_headers(self, api_key: Optional[str] = None) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Token {api_key}"
        return headers

    async def request(self, method: str, path: str, api_key: Optional[str] = None, **kwargs: Any) -> Any:
        url = f"{self.base_url}{path}"
        headers = self._get_headers(api_key)
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.request(method, url, headers=headers, **kwargs)
            response.raise_for_status()
            if response.status_code == 204:
                return {}
            if response.headers.get("content-type", "").startswith("application/json"):
                return response.json()
            return {"text": response.text}

    async def get(self, path: str, api_key: Optional[str] = None, **kwargs: Any) -> Any:
        return await self.request("GET", path, api_key, **kwargs)

    async def post(self, path: str, api_key: Optional[str] = None, **kwargs: Any) -> Any:
        return await self.request("POST", path, api_key, **kwargs)

    async def put(self, path: str, api_key: Optional[str] = None, **kwargs: Any) -> Any:
        return await self.request("PUT", path, api_key, **kwargs)

    async def patch(self, path: str, api_key: Optional[str] = None, **kwargs: Any) -> Any:
        return await self.request("PATCH", path, api_key, **kwargs)

    async def delete(self, path: str, api_key: Optional[str] = None, **kwargs: Any) -> Any:
        return await self.request("DELETE", path, api_key, **kwargs)

    def _normalize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {k: _normalize_datetime(v) if isinstance(v, str) else v for k, v in payload.items()}

    # =========================================================================
    # Document Domain Methods
    # =========================================================================

    async def get_all_documents(self, api_key: Optional[str] = None, include_all_fields: bool = False, page: int = 1, page_size: int = 100) -> Any:
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if not include_all_fields:
            params["fields"] = DOCUMENT_COMMON_FIELDS
        return await self.get("/api/documents/", api_key, params=params)

    async def get_document_by_id(self, document_id: int, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        params: dict[str, Any] = {}
        if not include_all_fields:
            params["fields"] = DOCUMENT_COMMON_FIELDS
        return await self.get(f"/api/documents/{document_id}/", api_key, params=params or None)

    async def update_document(self, document_id: int, payload: dict[str, Any], api_key: Optional[str] = None) -> Any:
        payload = self._normalize_payload(payload)
        return await self.patch(f"/api/documents/{document_id}/", api_key, json=payload)

    async def delete_document_by_id(self, document_id: int, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/api/documents/{document_id}/", api_key)

    async def get_document_metadata(self, document_id: int, api_key: Optional[str] = None) -> Any:
        return await self.get(f"/api/documents/{document_id}/metadata/", api_key)

    async def get_document_suggestions(self, document_id: int, api_key: Optional[str] = None) -> Any:
        return await self.get(f"/api/documents/{document_id}/suggestions/", api_key)

    async def get_document_ai_suggestions(self, document_id: int, api_key: Optional[str] = None) -> Any:
        return await self.get(f"/api/documents/{document_id}/ai_suggestions/", api_key)

    async def get_next_asn(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/api/documents/next_asn/", api_key)

    async def get_document_notes(self, document_id: int, api_key: Optional[str] = None) -> Any:
        return await self.get(f"/api/documents/{document_id}/notes/", api_key)

    async def create_document_note(self, document_id: int, payload: dict[str, Any], api_key: Optional[str] = None) -> Any:
        return await self.post(f"/api/documents/{document_id}/notes/", api_key, json=payload)

    async def delete_document_note(self, document_id: int, note_id: int, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/api/documents/{document_id}/notes/", api_key, params={"id": note_id})

    # =========================================================================
    # Correspondent Domain Methods
    # =========================================================================

    async def get_all_correspondents(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        return await self.get("/api/correspondents/", api_key)

    async def get_correspondent_by_id(self, correspondent_id: int, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        return await self.get(f"/api/correspondents/{correspondent_id}/", api_key)

    async def create_correspondent(self, payload: dict[str, Any], api_key: Optional[str] = None) -> Any:
        payload = self._normalize_payload(payload)
        return await self.post("/api/correspondents/", api_key, json=payload)

    async def update_correspondent(self, correspondent_id: int, payload: dict[str, Any], api_key: Optional[str] = None) -> Any:
        payload = self._normalize_payload(payload)
        return await self.patch(f"/api/correspondents/{correspondent_id}/", api_key, json=payload)

    async def delete_correspondent_by_id(self, correspondent_id: int, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/api/correspondents/{correspondent_id}/", api_key)

    # =========================================================================
    # Document Type Domain Methods
    # =========================================================================

    async def get_all_document_types(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        return await self.get("/api/document_types/", api_key)

    async def get_document_type_by_id(self, document_type_id: int, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        return await self.get(f"/api/document_types/{document_type_id}/", api_key)

    async def create_document_type(self, payload: dict[str, Any], api_key: Optional[str] = None) -> Any:
        payload = self._normalize_payload(payload)
        return await self.post("/api/document_types/", api_key, json=payload)

    async def update_document_type(self, document_type_id: int, payload: dict[str, Any], api_key: Optional[str] = None) -> Any:
        payload = self._normalize_payload(payload)
        return await self.patch(f"/api/document_types/{document_type_id}/", api_key, json=payload)

    async def delete_document_type_by_id(self, document_type_id: int, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/api/document_types/{document_type_id}/", api_key)

    # =========================================================================
    # Tag Domain Methods
    # =========================================================================

    async def get_all_tags(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        return await self.get("/api/tags/", api_key)

    async def get_tag_by_id(self, tag_id: int, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        return await self.get(f"/api/tags/{tag_id}/", api_key)

    async def create_tag(self, payload: dict[str, Any], api_key: Optional[str] = None) -> Any:
        payload = self._normalize_payload(payload)
        return await self.post("/api/tags/", api_key, json=payload)

    async def update_tag(self, tag_id: int, payload: dict[str, Any], api_key: Optional[str] = None) -> Any:
        payload = self._normalize_payload(payload)
        return await self.patch(f"/api/tags/{tag_id}/", api_key, json=payload)

    async def delete_tag_by_id(self, tag_id: int, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/api/tags/{tag_id}/", api_key)

    # =========================================================================
    # Storage Path Domain Methods
    # =========================================================================

    async def get_all_storage_paths(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        return await self.get("/api/storage_paths/", api_key)

    async def get_storage_path_by_id(self, storage_path_id: int, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        return await self.get(f"/api/storage_paths/{storage_path_id}/", api_key)

    async def create_storage_path(self, payload: dict[str, Any], api_key: Optional[str] = None) -> Any:
        payload = self._normalize_payload(payload)
        return await self.post("/api/storage_paths/", api_key, json=payload)

    async def update_storage_path(self, storage_path_id: int, payload: dict[str, Any], api_key: Optional[str] = None) -> Any:
        payload = self._normalize_payload(payload)
        return await self.patch(f"/api/storage_paths/{storage_path_id}/", api_key, json=payload)

    async def delete_storage_path_by_id(self, storage_path_id: int, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/api/storage_paths/{storage_path_id}/", api_key)

    # =========================================================================
    # Saved View Domain Methods
    # =========================================================================

    async def get_all_saved_views(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        return await self.get("/api/saved_views/", api_key)

    async def get_saved_view_by_id(self, saved_view_id: int, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        return await self.get(f"/api/saved_views/{saved_view_id}/", api_key)

    async def create_saved_view(self, payload: dict[str, Any], api_key: Optional[str] = None) -> Any:
        payload = self._normalize_payload(payload)
        return await self.post("/api/saved_views/", api_key, json=payload)

    async def update_saved_view(self, saved_view_id: int, payload: dict[str, Any], api_key: Optional[str] = None) -> Any:
        payload = self._normalize_payload(payload)
        return await self.patch(f"/api/saved_views/{saved_view_id}/", api_key, json=payload)

    async def delete_saved_view_by_id(self, saved_view_id: int, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/api/saved_views/{saved_view_id}/", api_key)

    # =========================================================================
    # Custom Field Domain Methods
    # =========================================================================

    async def get_all_custom_fields(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        return await self.get("/api/custom_fields/", api_key)

    async def get_custom_field_by_id(self, custom_field_id: int, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        return await self.get(f"/api/custom_fields/{custom_field_id}/", api_key)

    async def create_custom_field(self, payload: dict[str, Any], api_key: Optional[str] = None) -> Any:
        payload = self._normalize_payload(payload)
        return await self.post("/api/custom_fields/", api_key, json=payload)

    async def update_custom_field(self, custom_field_id: int, payload: dict[str, Any], api_key: Optional[str] = None) -> Any:
        payload = self._normalize_payload(payload)
        return await self.patch(f"/api/custom_fields/{custom_field_id}/", api_key, json=payload)

    async def delete_custom_field_by_id(self, custom_field_id: int, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/api/custom_fields/{custom_field_id}/", api_key)

    # =========================================================================
    # Task Domain Methods
    # =========================================================================

    async def get_all_tasks(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        return await self.get("/api/tasks/", api_key)

    async def get_task_by_id(self, task_id: int, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        return await self.get(f"/api/tasks/{task_id}/", api_key)

    async def get_task_summary(self, api_key: Optional[str] = None, days: int = 30) -> Any:
        return await self.get("/api/tasks/summary/", api_key, params={"days": days})

    async def get_task_status_counts(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/api/tasks/status_counts/", api_key)

    async def get_active_tasks(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/api/tasks/active/", api_key)

    async def acknowledge_tasks(self, payload: dict[str, Any], api_key: Optional[str] = None) -> Any:
        return await self.post("/api/tasks/acknowledge/", api_key, json=payload)

    # =========================================================================
    # Share Link Domain Methods
    # =========================================================================

    async def get_all_share_links(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        return await self.get("/api/share_links/", api_key)

    async def get_share_link_by_id(self, share_link_id: int, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        return await self.get(f"/api/share_links/{share_link_id}/", api_key)

    async def create_share_link(self, payload: dict[str, Any], api_key: Optional[str] = None) -> Any:
        payload = self._normalize_payload(payload)
        return await self.post("/api/share_links/", api_key, json=payload)

    async def delete_share_link_by_id(self, share_link_id: int, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/api/share_links/{share_link_id}/", api_key)

    # =========================================================================
    # Workflow Domain Methods
    # =========================================================================

    async def get_all_workflows(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        return await self.get("/api/workflows/", api_key)

    async def get_workflow_by_id(self, workflow_id: int, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        return await self.get(f"/api/workflows/{workflow_id}/", api_key)

    async def create_workflow(self, payload: dict[str, Any], api_key: Optional[str] = None) -> Any:
        payload = self._normalize_payload(payload)
        return await self.post("/api/workflows/", api_key, json=payload)

    async def update_workflow(self, workflow_id: int, payload: dict[str, Any], api_key: Optional[str] = None) -> Any:
        payload = self._normalize_payload(payload)
        return await self.patch(f"/api/workflows/{workflow_id}/", api_key, json=payload)

    async def delete_workflow_by_id(self, workflow_id: int, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/api/workflows/{workflow_id}/", api_key)

    # =========================================================================
    # Mail Account Domain Methods
    # =========================================================================

    async def get_all_mail_accounts(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        return await self.get("/api/mail_accounts/", api_key)

    async def get_mail_account_by_id(self, mail_account_id: int, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        return await self.get(f"/api/mail_accounts/{mail_account_id}/", api_key)

    async def create_mail_account(self, payload: dict[str, Any], api_key: Optional[str] = None) -> Any:
        payload = self._normalize_payload(payload)
        return await self.post("/api/mail_accounts/", api_key, json=payload)

    async def update_mail_account(self, mail_account_id: int, payload: dict[str, Any], api_key: Optional[str] = None) -> Any:
        payload = self._normalize_payload(payload)
        return await self.patch(f"/api/mail_accounts/{mail_account_id}/", api_key, json=payload)

    async def delete_mail_account_by_id(self, mail_account_id: int, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/api/mail_accounts/{mail_account_id}/", api_key)

    # =========================================================================
    # Mail Rule Domain Methods
    # =========================================================================

    async def get_all_mail_rules(self, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        return await self.get("/api/mail_rules/", api_key)

    async def get_mail_rule_by_id(self, mail_rule_id: int, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        return await self.get(f"/api/mail_rules/{mail_rule_id}/", api_key)

    async def create_mail_rule(self, payload: dict[str, Any], api_key: Optional[str] = None) -> Any:
        payload = self._normalize_payload(payload)
        return await self.post("/api/mail_rules/", api_key, json=payload)

    async def update_mail_rule(self, mail_rule_id: int, payload: dict[str, Any], api_key: Optional[str] = None) -> Any:
        payload = self._normalize_payload(payload)
        return await self.patch(f"/api/mail_rules/{mail_rule_id}/", api_key, json=payload)

    async def delete_mail_rule_by_id(self, mail_rule_id: int, api_key: Optional[str] = None) -> Any:
        return await self.delete(f"/api/mail_rules/{mail_rule_id}/", api_key)

    # =========================================================================
    # Search Domain Methods
    # =========================================================================

    async def search_documents(self, query: str, api_key: Optional[str] = None, limit: int = 50, db_only: bool = False) -> Any:
        params: dict[str, Any] = {"query": query}
        if limit:
            params["limit"] = limit
        if db_only:
            params["db_only"] = "true"
        return await self.get("/api/search/", api_key, params=params)

    async def search_autocomplete(self, term: str, api_key: Optional[str] = None, limit: int = 10) -> Any:
        params: dict[str, Any] = {"term": term, "limit": limit}
        return await self.get("/api/search/autocomplete/", api_key, params=params)

    async def bulk_edit_documents(self, payload: dict[str, Any], api_key: Optional[str] = None) -> Any:
        return await self.post("/api/documents/bulk_edit/", api_key, json=payload)

    async def reprocess_documents(self, payload: dict[str, Any], api_key: Optional[str] = None) -> Any:
        return await self.post("/api/documents/reprocess/", api_key, json=payload)

    # =========================================================================
    # System Domain Methods
    # =========================================================================

    async def get_statistics(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/api/statistics/", api_key)

    async def check_server_status(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/api/status/", api_key)
