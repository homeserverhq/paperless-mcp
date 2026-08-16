import os
import re
import time
import asyncio
import datetime as dt
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


COMMON_FIELDS: dict[str, str] = {
    "Documents": "id,title,correspondent,document_type,tags,page_count",
    "Correspondents": "id,name,slug,document_count",
    "DocumentTypes": "id,name,slug,document_count",
    "Tags": "id,name,slug,color,document_count",
    "StoragePaths": "id,name,path,document_count",
    "SavedViews": "id,name,show_on_dashboard,show_in_sidebar,sort_field",
    "CustomFields": "id,name,data_type",
    "Workflows": "id,name,order,enabled",
    "MailAccounts": "id,name,username,imap_server,imap_port,is_active",
    "MailRules": "id,name,account,action,folder,order",
    "Tasks": "id,task_id,task_file_name,date_created,type,status",
    "ShareLinks": "id,slug,document,created,expiration,file_version",
}

# Entities with per-item public web deep-links: (URL field name, path template).
# The template is formatted with the object's `id`. A None template means a
# custom path is built (see _public_path, e.g. share links keyed by slug).
_PUBLIC_ROUTES: dict[str, tuple[str, Optional[str]]] = {
    "document": ("documentUrl", "/documents/{id}/details"),
    "saved_view": ("savedViewUrl", "/view/{id}"),
    "share_link": ("shareLinkUrl", None),
}

# Mapping of entity -> COMMON_FIELDS key used when field-filtering per-item objects.
_ENTITY_FIELDS: dict[str, str] = {
    "document": "Documents",
    "saved_view": "SavedViews",
    "share_link": "ShareLinks",
}

# List-only objects (no per-item deep-link): URL field name -> public list path.
# Injected at the TOP level of the paginated list response, not per item.
_LIST_URLS: dict[str, tuple[str, str]] = {
    "Correspondents": ("correspondentsUrl", "/attributes/correspondents"),
    "DocumentTypes": ("documentTypesUrl", "/attributes/documenttypes"),
    "Tags": ("tagsUrl", "/attributes/tags"),
    "StoragePaths": ("storagePathsUrl", "/attributes/storagepaths"),
    "CustomFields": ("customFieldsUrl", "/attributes/customfields"),
    "Workflows": ("workflowsUrl", "/workflows"),
    "MailAccounts": ("mailAccountsUrl", "/mail"),
    "MailRules": ("mailRulesUrl", "/mail"),
    "Tasks": ("tasksUrl", "/tasks"),
}


class PaperlessClient:
    """Client for Paperless API with auth passthrough."""

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or os.getenv("PAPERLESS_BASE_URL", "")).rstrip("/")
        if not self.base_url:
            raise ValueError(
                "Paperless URL required. Set PAPERLESS_BASE_URL env var or pass base_url."
            )
        self.public_url = os.getenv("PAPERLESS_PUBLIC_URL", "").rstrip("/") or self.base_url

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

    def _filter_fields(self, item: dict, fields_str: str) -> dict:
        allowed = set(f.strip() for f in fields_str.split(","))
        return {k: v for k, v in item.items() if k in allowed}

    def _filter_list_response(self, response: Any, fields_str: str) -> Any:
        if isinstance(response, dict) and "results" in response:
            response["results"] = [self._filter_fields(item, fields_str) for item in response["results"]]
        elif isinstance(response, list):
            response = [self._filter_fields(item, fields_str) for item in response]
        return response

    def _public_path(self, entity: str, obj: dict) -> Optional[str]:
        template = _PUBLIC_ROUTES[entity][1]
        if entity == "share_link":
            slug = obj.get("slug")
            return f"/share/{slug}" if slug else None
        if template and obj.get("id"):
            return template.format(id=obj["id"])
        return None

    def _augment_urls(self, data: Any, entity: str, public_url: Optional[str]) -> Any:
        if not public_url or entity not in _PUBLIC_ROUTES:
            return data
        field = _PUBLIC_ROUTES[entity][0]
        if isinstance(data, list):
            return [self._augment_urls(item, entity, public_url) for item in data]
        if isinstance(data, dict):
            path = self._public_path(entity, data)
            if path:
                data[field] = public_url + path
        return data

    def _process(self, data: Any, entity: str, include_all_fields: bool, public_url: Optional[str]) -> Any:
        fields = COMMON_FIELDS[_ENTITY_FIELDS[entity]] if not include_all_fields else None
        if isinstance(data, dict) and "results" in data:
            items = data["results"]
            if fields:
                items = [self._filter_fields(item, fields) for item in items]
            data["results"] = self._augment_urls(items, entity, public_url)
            return data
        if fields:
            data = self._filter_fields(data, fields)
        return self._augment_urls(data, entity, public_url)

    def _add_list_url(self, data: Any, key: str) -> Any:
        routes = _LIST_URLS.get(key)
        if routes and self.public_url and isinstance(data, dict):
            data[routes[0]] = self.public_url + routes[1]
        return data

    # =========================================================================
    # Document Domain Methods
    # =========================================================================

    async def list_all_documents(self, api_key: Optional[str] = None, include_all_fields: bool = False, page: int = 1, page_size: int = 500) -> Any:
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if not include_all_fields:
            params["fields"] = COMMON_FIELDS["Documents"]
        data = await self.get("/api/documents/", api_key, params=params)
        return self._process(data, "document", include_all_fields, self.public_url)

    async def get_document(self, document_id: int, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        params: dict[str, Any] = {}
        if not include_all_fields:
            params["fields"] = COMMON_FIELDS["Documents"]
        data = await self.get(f"/api/documents/{document_id}/", api_key, params=params or None)
        return self._process(data, "document", include_all_fields, self.public_url)

    async def update_document(self, document_id: int, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        payload = self._normalize_payload(payload)
        data = await self.patch(f"/api/documents/{document_id}/", api_key, json=payload)
        return self._process(data, "document", include_all_fields, self.public_url)

    async def upload_document(self, title: str, content: str, api_key: Optional[str] = None, include_all_fields: bool = False, timeout: int = 60) -> Any:
        filename = re.sub(r"[^\w.\-]+", "_", title).rstrip("._") + ".txt"
        url = f"{self.base_url}/api/documents/post_document/"
        headers = {"Authorization": f"Token {api_key}"} if api_key else {}
        deadline = time.monotonic() + timeout
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                url,
                headers=headers,
                files={"document": (filename, content.encode("utf-8"), "text/plain")},
                data={"title": title},
            )
            response.raise_for_status()
            while time.monotonic() < deadline:
                await asyncio.sleep(1)
                r = await client.get(
                    f"{self.base_url}/api/documents/",
                    headers=headers,
                    params={"page_size": 50, "ordering": "-id"},
                )
                r.raise_for_status()
                for doc in r.json().get("results", []):
                    if doc.get("title") == title:
                        return self._process(doc, "document", include_all_fields, self.public_url)
        raise TimeoutError(f"Uploaded document was not created within {timeout}s")

    async def delete_document(self, document_id: int, api_key: Optional[str] = None) -> Any:
        await self.delete(f"/api/documents/{document_id}/", api_key)
        return {"message": "Document successfully deleted."}

    async def get_document_metadata(self, document_id: int, api_key: Optional[str] = None) -> Any:
        return await self.get(f"/api/documents/{document_id}/metadata/", api_key)

    async def get_document_suggestions(self, document_id: int, api_key: Optional[str] = None) -> Any:
        return await self.get(f"/api/documents/{document_id}/suggestions/", api_key)

    async def get_document_ai_suggestions(self, document_id: int, api_key: Optional[str] = None) -> Any:
        return await self.get(f"/api/documents/{document_id}/ai_suggestions/", api_key)

    async def get_next_asn(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/api/documents/next_asn/", api_key)

    async def list_notes_by_document(self, document_id: int, api_key: Optional[str] = None) -> Any:
        return await self.get(f"/api/documents/{document_id}/notes/", api_key)

    async def create_document_note(self, document_id: int, payload: dict[str, Any], api_key: Optional[str] = None) -> Any:
        return await self.post(f"/api/documents/{document_id}/notes/", api_key, json=payload)

    async def delete_document_note(self, document_id: int, note_id: int, api_key: Optional[str] = None) -> Any:
        await self.delete(f"/api/documents/{document_id}/notes/", api_key, params={"id": note_id})
        return {"message": "Note successfully deleted."}

    # =========================================================================
    # Correspondent Domain Methods
    # =========================================================================

    async def list_all_correspondents(self, api_key: Optional[str] = None, include_all_fields: bool = False, page_size: int = 500) -> Any:
        data = await self.get("/api/correspondents/", api_key, params={"page_size": page_size})
        if not include_all_fields:
            data = self._filter_list_response(data, COMMON_FIELDS["Correspondents"])
        return self._add_list_url(data, "Correspondents")

    async def get_correspondent(self, correspondent_id: int, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/correspondents/{correspondent_id}/", api_key)
        if not include_all_fields:
            data = self._filter_fields(data, COMMON_FIELDS["Correspondents"])
        return data

    async def create_correspondent(self, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        payload = self._normalize_payload(payload)
        data = await self.post("/api/correspondents/", api_key, json=payload)
        if not include_all_fields:
            data = self._filter_fields(data, COMMON_FIELDS["Correspondents"])
        return data

    async def update_correspondent(self, correspondent_id: int, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        payload = self._normalize_payload(payload)
        data = await self.patch(f"/api/correspondents/{correspondent_id}/", api_key, json=payload)
        if not include_all_fields:
            data = self._filter_fields(data, COMMON_FIELDS["Correspondents"])
        return data

    async def delete_correspondent(self, correspondent_id: int, api_key: Optional[str] = None) -> Any:
        await self.delete(f"/api/correspondents/{correspondent_id}/", api_key)
        return {"message": "Correspondent successfully deleted."}

    # =========================================================================
    # Document Type Domain Methods
    # =========================================================================

    async def list_all_document_types(self, api_key: Optional[str] = None, include_all_fields: bool = False, page_size: int = 500) -> Any:
        data = await self.get("/api/document_types/", api_key, params={"page_size": page_size})
        if not include_all_fields:
            data = self._filter_list_response(data, COMMON_FIELDS["DocumentTypes"])
        return self._add_list_url(data, "DocumentTypes")

    async def get_document_type(self, document_type_id: int, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/document_types/{document_type_id}/", api_key)
        if not include_all_fields:
            data = self._filter_fields(data, COMMON_FIELDS["DocumentTypes"])
        return data

    async def create_document_type(self, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        payload = self._normalize_payload(payload)
        data = await self.post("/api/document_types/", api_key, json=payload)
        if not include_all_fields:
            data = self._filter_fields(data, COMMON_FIELDS["DocumentTypes"])
        return data

    async def update_document_type(self, document_type_id: int, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        payload = self._normalize_payload(payload)
        data = await self.patch(f"/api/document_types/{document_type_id}/", api_key, json=payload)
        if not include_all_fields:
            data = self._filter_fields(data, COMMON_FIELDS["DocumentTypes"])
        return data

    async def delete_document_type(self, document_type_id: int, api_key: Optional[str] = None) -> Any:
        await self.delete(f"/api/document_types/{document_type_id}/", api_key)
        return {"message": "Document type successfully deleted."}

    # =========================================================================
    # Tag Domain Methods
    # =========================================================================

    async def list_all_tags(self, api_key: Optional[str] = None, include_all_fields: bool = False, page_size: int = 500) -> Any:
        data = await self.get("/api/tags/", api_key, params={"page_size": page_size})
        if not include_all_fields:
            data = self._filter_list_response(data, COMMON_FIELDS["Tags"])
        return self._add_list_url(data, "Tags")

    async def get_tag(self, tag_id: int, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/tags/{tag_id}/", api_key)
        if not include_all_fields:
            data = self._filter_fields(data, COMMON_FIELDS["Tags"])
        return data

    async def create_tag(self, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        payload = self._normalize_payload(payload)
        data = await self.post("/api/tags/", api_key, json=payload)
        if not include_all_fields:
            data = self._filter_fields(data, COMMON_FIELDS["Tags"])
        return data

    async def update_tag(self, tag_id: int, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        payload = self._normalize_payload(payload)
        data = await self.patch(f"/api/tags/{tag_id}/", api_key, json=payload)
        if not include_all_fields:
            data = self._filter_fields(data, COMMON_FIELDS["Tags"])
        return data

    async def delete_tag(self, tag_id: int, api_key: Optional[str] = None) -> Any:
        await self.delete(f"/api/tags/{tag_id}/", api_key)
        return {"message": "Tag successfully deleted."}

    # =========================================================================
    # Storage Path Domain Methods
    # =========================================================================

    async def list_all_storage_paths(self, api_key: Optional[str] = None, include_all_fields: bool = False, page_size: int = 500) -> Any:
        data = await self.get("/api/storage_paths/", api_key, params={"page_size": page_size})
        if not include_all_fields:
            data = self._filter_list_response(data, COMMON_FIELDS["StoragePaths"])
        return self._add_list_url(data, "StoragePaths")

    async def get_storage_path(self, storage_path_id: int, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/storage_paths/{storage_path_id}/", api_key)
        if not include_all_fields:
            data = self._filter_fields(data, COMMON_FIELDS["StoragePaths"])
        return data

    async def create_storage_path(self, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        payload = self._normalize_payload(payload)
        data = await self.post("/api/storage_paths/", api_key, json=payload)
        if not include_all_fields:
            data = self._filter_fields(data, COMMON_FIELDS["StoragePaths"])
        return data

    async def update_storage_path(self, storage_path_id: int, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        payload = self._normalize_payload(payload)
        data = await self.patch(f"/api/storage_paths/{storage_path_id}/", api_key, json=payload)
        if not include_all_fields:
            data = self._filter_fields(data, COMMON_FIELDS["StoragePaths"])
        return data

    async def delete_storage_path(self, storage_path_id: int, api_key: Optional[str] = None) -> Any:
        await self.delete(f"/api/storage_paths/{storage_path_id}/", api_key)
        return {"message": "Storage path successfully deleted."}

    # =========================================================================
    # Saved View Domain Methods
    # =========================================================================

    async def list_all_saved_views(self, api_key: Optional[str] = None, include_all_fields: bool = False, page_size: int = 500) -> Any:
        data = await self.get("/api/saved_views/", api_key, params={"page_size": page_size})
        return self._process(data, "saved_view", include_all_fields, self.public_url)

    async def get_saved_view(self, saved_view_id: int, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/saved_views/{saved_view_id}/", api_key)
        return self._process(data, "saved_view", include_all_fields, self.public_url)

    async def create_saved_view(self, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        payload = self._normalize_payload(payload)
        data = await self.post("/api/saved_views/", api_key, json=payload)
        return self._process(data, "saved_view", include_all_fields, self.public_url)

    async def update_saved_view(self, saved_view_id: int, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        payload = self._normalize_payload(payload)
        data = await self.patch(f"/api/saved_views/{saved_view_id}/", api_key, json=payload)
        return self._process(data, "saved_view", include_all_fields, self.public_url)

    async def delete_saved_view(self, saved_view_id: int, api_key: Optional[str] = None) -> Any:
        await self.delete(f"/api/saved_views/{saved_view_id}/", api_key)
        return {"message": "Saved view successfully deleted."}

    # =========================================================================
    # Custom Field Domain Methods
    # =========================================================================

    async def list_all_custom_fields(self, api_key: Optional[str] = None, include_all_fields: bool = False, page_size: int = 500) -> Any:
        data = await self.get("/api/custom_fields/", api_key, params={"page_size": page_size})
        if not include_all_fields:
            data = self._filter_list_response(data, COMMON_FIELDS["CustomFields"])
        return self._add_list_url(data, "CustomFields")

    async def get_custom_field(self, custom_field_id: int, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/custom_fields/{custom_field_id}/", api_key)
        if not include_all_fields:
            data = self._filter_fields(data, COMMON_FIELDS["CustomFields"])
        return data

    async def create_custom_field(self, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        payload = self._normalize_payload(payload)
        data = await self.post("/api/custom_fields/", api_key, json=payload)
        if not include_all_fields:
            data = self._filter_fields(data, COMMON_FIELDS["CustomFields"])
        return data

    async def update_custom_field(self, custom_field_id: int, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        payload = self._normalize_payload(payload)
        data = await self.patch(f"/api/custom_fields/{custom_field_id}/", api_key, json=payload)
        if not include_all_fields:
            data = self._filter_fields(data, COMMON_FIELDS["CustomFields"])
        return data

    async def delete_custom_field(self, custom_field_id: int, api_key: Optional[str] = None) -> Any:
        await self.delete(f"/api/custom_fields/{custom_field_id}/", api_key)
        return {"message": "Custom field successfully deleted."}

    # =========================================================================
    # Task Domain Methods
    # =========================================================================

    async def list_all_tasks(self, api_key: Optional[str] = None, include_all_fields: bool = False, page_size: int = 500) -> Any:
        data = await self.get("/api/tasks/", api_key, params={"page_size": page_size})
        if not include_all_fields:
            data = self._filter_list_response(data, COMMON_FIELDS["Tasks"])
        return self._add_list_url(data, "Tasks")

    async def get_task(self, task_id: int, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/tasks/{task_id}/", api_key)
        if not include_all_fields:
            data = self._filter_fields(data, COMMON_FIELDS["Tasks"])
        return data

    async def get_task_summary(self, api_key: Optional[str] = None, days: int = 30) -> Any:
        return await self.get("/api/tasks/summary/", api_key, params={"days": days})

    async def get_task_status_counts(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/api/tasks/status_counts/", api_key)

    async def list_active_tasks(self, api_key: Optional[str] = None) -> Any:
        return await self.get("/api/tasks/active/", api_key)

    async def acknowledge_tasks(self, payload: dict[str, Any], api_key: Optional[str] = None) -> Any:
        return await self.post("/api/tasks/acknowledge/", api_key, json=payload)

    # =========================================================================
    # Share Link Domain Methods
    # =========================================================================

    async def list_all_share_links(self, api_key: Optional[str] = None, include_all_fields: bool = False, page_size: int = 500) -> Any:
        data = await self.get("/api/share_links/", api_key, params={"page_size": page_size})
        return self._process(data, "share_link", include_all_fields, self.public_url)

    async def get_share_link(self, share_link_id: int, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/share_links/{share_link_id}/", api_key)
        return self._process(data, "share_link", include_all_fields, self.public_url)

    async def create_share_link(self, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        payload = self._normalize_payload(payload)
        data = await self.post("/api/share_links/", api_key, json=payload)
        return self._process(data, "share_link", include_all_fields, self.public_url)

    async def delete_share_link(self, share_link_id: int, api_key: Optional[str] = None) -> Any:
        await self.delete(f"/api/share_links/{share_link_id}/", api_key)
        return {"message": "Share link successfully deleted."}

    # =========================================================================
    # Workflow Domain Methods
    # =========================================================================

    async def list_all_workflows(self, api_key: Optional[str] = None, include_all_fields: bool = False, page_size: int = 500) -> Any:
        data = await self.get("/api/workflows/", api_key, params={"page_size": page_size})
        if not include_all_fields:
            data = self._filter_list_response(data, COMMON_FIELDS["Workflows"])
        return self._add_list_url(data, "Workflows")

    async def get_workflow(self, workflow_id: int, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/workflows/{workflow_id}/", api_key)
        if not include_all_fields:
            data = self._filter_fields(data, COMMON_FIELDS["Workflows"])
        return data

    async def create_workflow(self, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        payload = self._normalize_payload(payload)
        data = await self.post("/api/workflows/", api_key, json=payload)
        if not include_all_fields:
            data = self._filter_fields(data, COMMON_FIELDS["Workflows"])
        return data

    async def update_workflow(self, workflow_id: int, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        payload = self._normalize_payload(payload)
        data = await self.patch(f"/api/workflows/{workflow_id}/", api_key, json=payload)
        if not include_all_fields:
            data = self._filter_fields(data, COMMON_FIELDS["Workflows"])
        return data

    async def delete_workflow(self, workflow_id: int, api_key: Optional[str] = None) -> Any:
        await self.delete(f"/api/workflows/{workflow_id}/", api_key)
        return {"message": "Workflow successfully deleted."}

    # =========================================================================
    # Mail Account Domain Methods
    # =========================================================================

    async def list_all_mail_accounts(self, api_key: Optional[str] = None, include_all_fields: bool = False, page_size: int = 500) -> Any:
        data = await self.get("/api/mail_accounts/", api_key, params={"page_size": page_size})
        if not include_all_fields:
            data = self._filter_list_response(data, COMMON_FIELDS["MailAccounts"])
        return self._add_list_url(data, "MailAccounts")

    async def get_mail_account(self, mail_account_id: int, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/mail_accounts/{mail_account_id}/", api_key)
        if not include_all_fields:
            data = self._filter_fields(data, COMMON_FIELDS["MailAccounts"])
        return data

    async def create_mail_account(self, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        payload = self._normalize_payload(payload)
        data = await self.post("/api/mail_accounts/", api_key, json=payload)
        if not include_all_fields:
            data = self._filter_fields(data, COMMON_FIELDS["MailAccounts"])
        return data

    async def update_mail_account(self, mail_account_id: int, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        payload = self._normalize_payload(payload)
        data = await self.patch(f"/api/mail_accounts/{mail_account_id}/", api_key, json=payload)
        if not include_all_fields:
            data = self._filter_fields(data, COMMON_FIELDS["MailAccounts"])
        return data

    async def delete_mail_account(self, mail_account_id: int, api_key: Optional[str] = None) -> Any:
        await self.delete(f"/api/mail_accounts/{mail_account_id}/", api_key)
        return {"message": "Mail account successfully deleted."}

    # =========================================================================
    # Mail Rule Domain Methods
    # =========================================================================

    async def list_all_mail_rules(self, api_key: Optional[str] = None, include_all_fields: bool = False, page_size: int = 500) -> Any:
        data = await self.get("/api/mail_rules/", api_key, params={"page_size": page_size})
        if not include_all_fields:
            data = self._filter_list_response(data, COMMON_FIELDS["MailRules"])
        return self._add_list_url(data, "MailRules")

    async def get_mail_rule(self, mail_rule_id: int, api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        data = await self.get(f"/api/mail_rules/{mail_rule_id}/", api_key)
        if not include_all_fields:
            data = self._filter_fields(data, COMMON_FIELDS["MailRules"])
        return data

    async def create_mail_rule(self, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        payload = self._normalize_payload(payload)
        data = await self.post("/api/mail_rules/", api_key, json=payload)
        if not include_all_fields:
            data = self._filter_fields(data, COMMON_FIELDS["MailRules"])
        return data

    async def update_mail_rule(self, mail_rule_id: int, payload: dict[str, Any], api_key: Optional[str] = None, include_all_fields: bool = False) -> Any:
        payload = self._normalize_payload(payload)
        data = await self.patch(f"/api/mail_rules/{mail_rule_id}/", api_key, json=payload)
        if not include_all_fields:
            data = self._filter_fields(data, COMMON_FIELDS["MailRules"])
        return data

    async def delete_mail_rule(self, mail_rule_id: int, api_key: Optional[str] = None) -> Any:
        await self.delete(f"/api/mail_rules/{mail_rule_id}/", api_key)
        return {"message": "Mail rule successfully deleted."}

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
