import json
import os
import sys
from contextvars import ContextVar
from typing import Any, Optional

from fastmcp import FastMCP, Context
from pydantic import BaseModel, Field
from toon_mcp import json_to_toon

from .client import PaperlessClient

_current_user_token: ContextVar[Optional[str]] = ContextVar("current_user_token", default=None)

ALLOW_ALL_AGGREGATE = os.getenv("ALLOW_ALL_AGGREGATE", "false").lower() in ("true", "1", "yes")
PAPERLESS_PUBLIC_URL = os.getenv("PAPERLESS_PUBLIC_URL", "").rstrip("/")

_IMAP_SECURITY_MAP = {"none": 1, "ssl_tls": 2, "starttls": 3}
_MAIL_RULE_ACTION_MAP = {"delete": 1, "mark_read": 2, "flag": 3, "move": 4, "copy": 5}
_WORKFLOW_ACTION_MAP = {"assign": 1, "remove": 2, "email": 3, "webhook": 4, "remove_password": 5, "trash": 6}
_WORKFLOW_TRIGGER_MAP = {"consumption_started": 1, "document_added": 2, "document_updated": 3, "scheduled": 4}
_MATCHING_ALGO_MAP = {"none": 0, "any_word": 1, "all_words": 2, "exact": 3, "regex": 4, "fuzzy": 5, "automatic": 6}
_FILTER_RULE_MAP = {
    "title_contains": 0, "content_contains": 1, "asn_is": 2,
    "correspondent_is": 3, "document_type_is": 4, "is_in_inbox": 5,
    "has_tag": 6, "has_any_tag": 7, "created_before": 8,
    "created_after": 9, "created_year_is": 10, "created_month_is": 11,
    "created_day_is": 12, "added_before": 13, "added_after": 14,
    "modified_before": 15, "modified_after": 16,
    "does_not_have_tag": 17, "does_not_have_asn": 18,
    "title_or_content_contains": 19, "fulltext_query": 20,
    "has_tags_in": 22, "storage_path_is": 25,
    "owner_is": 32, "has_custom_field_value": 36,
}


class AuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            auth_header = headers.get(b"authorization", b"").decode()
            if auth_header.startswith("Bearer ") or auth_header.startswith("Token "):
                token = auth_header.split(" ", 1)[1]
                _current_user_token.set(token)
        await self.app(scope, receive, send)


mcp = FastMCP("Paperless-mcp-server")

_client: Optional[PaperlessClient] = None


def get_client() -> PaperlessClient:
    global _client
    if _client is None:
        _client = PaperlessClient()
    return _client


def get_user_token() -> Optional[str]:
    return _current_user_token.get()


# =============================================================================
# Pydantic Contract Models
# =============================================================================

class CreateCorrespondentParam(BaseModel):
    name: str
    matching_algorithm: int = 1
    is_insensitive: bool = True
    match: str = ""
    owner: Optional[int] = None


class UpdateCorrespondentParam(BaseModel):
    id: int
    name: Optional[str] = None
    matching_algorithm: Optional[int] = None
    is_insensitive: Optional[bool] = None
    match: Optional[str] = None
    owner: Optional[int] = None


class CreateDocumentTypeParam(BaseModel):
    name: str
    matching_algorithm: int = 1
    is_insensitive: bool = True
    match: str = ""
    owner: Optional[int] = None


class UpdateDocumentTypeParam(BaseModel):
    id: int
    name: Optional[str] = None
    matching_algorithm: Optional[int] = None
    is_insensitive: Optional[bool] = None
    match: Optional[str] = None
    owner: Optional[int] = None


class CreateTagParam(BaseModel):
    name: str
    color: str = "#a6cee3"
    is_inbox_tag: bool = False
    matching_algorithm: int = 1
    is_insensitive: bool = True
    match: str = ""
    parent: Optional[int] = None
    owner: Optional[int] = None


class UpdateTagParam(BaseModel):
    id: int
    name: Optional[str] = None
    color: Optional[str] = None
    is_inbox_tag: Optional[bool] = None
    matching_algorithm: Optional[int] = None
    is_insensitive: Optional[bool] = None
    match: Optional[str] = None
    parent: Optional[int] = None
    owner: Optional[int] = None


class CreateStoragePathParam(BaseModel):
    name: str
    path: str
    matching_algorithm: int = 6
    is_insensitive: bool = True
    match: str = ""
    owner: Optional[int] = None


class UpdateStoragePathParam(BaseModel):
    id: int
    name: Optional[str] = None
    path: Optional[str] = None
    matching_algorithm: Optional[int] = None
    is_insensitive: Optional[bool] = None
    match: Optional[str] = None
    owner: Optional[int] = None


class CreateSavedViewParam(BaseModel):
    name: str
    show_on_dashboard: bool = False
    show_in_sidebar: bool = True
    sort_field: str = "created"
    sort_reverse: bool = True
    filter_rules: list[dict[str, Any]] = Field(default_factory=list)
    owner: Optional[int] = None


class UpdateSavedViewParam(BaseModel):
    id: int
    name: Optional[str] = None
    show_on_dashboard: Optional[bool] = None
    show_in_sidebar: Optional[bool] = None
    sort_field: Optional[str] = None
    sort_reverse: Optional[bool] = None
    filter_rules: Optional[list[dict[str, Any]]] = None
    owner: Optional[int] = None


class CreateCustomFieldParam(BaseModel):
    name: str
    data_type: str
    extra_data: dict[str, Any] = Field(default_factory=dict)


class UpdateCustomFieldParam(BaseModel):
    id: int
    name: Optional[str] = None
    data_type: Optional[str] = None
    extra_data: Optional[dict[str, Any]] = None


class UpdateDocumentParam(BaseModel):
    id: int
    title: Optional[str] = None
    content: Optional[str] = None
    correspondent: Optional[int] = None
    document_type: Optional[int] = None
    storage_path: Optional[int] = None
    tags: Optional[list[int]] = None
    created: Optional[str] = None
    created_date: Optional[str] = None
    archive_serial_number: Optional[int] = None
    owner: Optional[int] = None
    remove_inbox_tags: Optional[bool] = None


class CreateNoteParam(BaseModel):
    note: str


class CreateShareLinkParam(BaseModel):
    document: int
    expiration: str
    file_version: str = "archive"


class AcknowledgeTasksParam(BaseModel):
    tasks: Optional[list[int]] = None
    all: Optional[bool] = None


class CreateWorkflowParam(BaseModel):
    name: str
    order: int = 1
    enabled: bool = True
    triggers: str = "[]"
    actions: str = "[]"


class UpdateWorkflowParam(BaseModel):
    id: int
    name: Optional[str] = None
    order: Optional[int] = None
    enabled: Optional[bool] = None
    triggers: Optional[str] = None
    actions: Optional[str] = None


class CreateMailAccountParam(BaseModel):
    name: str
    username: str
    password: str
    imap_server: str = "imap.gmail.com"
    imap_port: int = 993
    imap_security: int = 2
    character_set: str = "UTF-8"
    folder: str = "INBOX"
    is_active: bool = True


class UpdateMailAccountParam(BaseModel):
    id: int
    name: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    imap_server: Optional[str] = None
    imap_port: Optional[int] = None
    imap_security: Optional[int] = None
    character_set: Optional[str] = None
    folder: Optional[str] = None
    is_active: Optional[bool] = None


class CreateMailRuleParam(BaseModel):
    name: str
    account: int
    action: int
    folder: str
    filter_to: str = "*"
    filter_from: str = "*"
    filter_subject: str = "*"
    filter_attachment_filename: str = "*"
    maximum_age: int = 30
    order: int = 0
    assign_title: Optional[str] = None
    assign_tags: Optional[list[int]] = None
    assign_correspondent: Optional[int] = None
    assign_document_type: Optional[int] = None
    assign_storage_path: Optional[int] = None
    assign_owner: Optional[int] = None


class UpdateMailRuleParam(BaseModel):
    id: int
    name: Optional[str] = None
    account: Optional[int] = None
    action: Optional[int] = None
    folder: Optional[str] = None
    filter_to: Optional[str] = None
    filter_from: Optional[str] = None
    filter_subject: Optional[str] = None
    filter_attachment_filename: Optional[str] = None
    maximum_age: Optional[int] = None
    order: Optional[int] = None
    assign_title: Optional[str] = None
    assign_tags: Optional[list[int]] = None
    assign_correspondent: Optional[int] = None
    assign_document_type: Optional[int] = None
    assign_storage_path: Optional[int] = None
    assign_owner: Optional[int] = None


class WorkflowTrigger(BaseModel):
    """A workflow trigger that activates the workflow."""
    type: str = Field(default="consumption_started", description="consumption_started, document_added, document_updated, or scheduled.")
    filter_path: str = Field(default="/*", description="Glob pattern for file paths to match.")


class FilterRule(BaseModel):
    """A filter rule for a saved view."""
    rule_type: str = Field(description="title_contains, content_contains, correspondent_is, document_type_is, has_tag, created_before, created_after, added_before, added_after, storage_path_is, owner_is, or fulltext_query.")
    value: str = Field(description="Value to filter by, e.g. \"my title\", \"5\", or \"2026-01-15\".")
    type: str = Field(default="", description="Rule type identifier string, e.g. \"title\" or \"\". Usually leave empty.")


class BulkEditParams(BaseModel):
    """Parameters for bulk document editing. Provide only the fields relevant to the chosen method."""
    correspondent: Optional[int] = Field(default=None, description="Correspondent ID. Used with 'set_correspondent'.")
    document_type: Optional[int] = Field(default=None, description="Document type ID. Used with 'set_document_type'.")
    storage_path: Optional[int] = Field(default=None, description="Storage path ID. Used with 'set_storage_path'.")
    tag: Optional[int] = Field(default=None, description="Tag ID. Used with 'add_tag' and 'remove_tag'.")
    add: Optional[list[int]] = Field(default=None, description="Tag IDs to add. Used with 'modify_tags'.")
    remove: Optional[list[int]] = Field(default=None, description="Tag IDs to remove. Used with 'modify_tags'.")
    add_custom_fields: Optional[dict[str, str]] = Field(default=None, description="Custom field ID-value pairs to add. Used with 'modify_custom_fields'.")
    remove_custom_fields: Optional[list[int]] = Field(default=None, description="Custom field IDs to remove. Used with 'modify_custom_fields'.")


class DocumentFilter(BaseModel):
    """Filter criteria for bulk document operations. All fields are optional and combined with AND logic."""
    title__icontains: Optional[str] = Field(default=None, description="Title contains (case-insensitive).")
    title__contains: Optional[str] = Field(default=None, description="Title contains (case-sensitive).")
    correspondent__id: Optional[int] = Field(default=None, description="Correspondent ID.")
    document_type__id: Optional[int] = Field(default=None, description="Document type ID.")
    storage_path__id: Optional[int] = Field(default=None, description="Storage path ID.")
    tags__id__in: Optional[list[int]] = Field(default=None, description="Document must have any of these tag IDs.")
    created__date__gte: Optional[str] = Field(default=None, description="Created on or after. ISO 8601 format (2026-06-22T15:00:00-04:00).")
    created__date__lte: Optional[str] = Field(default=None, description="Created on or before. ISO 8601 format (2026-06-22T15:00:00-04:00).")
    added__date__gte: Optional[str] = Field(default=None, description="Added to system on or after. ISO 8601 format (2026-06-22T15:00:00-04:00).")
    added__date__lte: Optional[str] = Field(default=None, description="Added to system on or before. ISO 8601 format (2026-06-22T15:00:00-04:00).")
    owner__id: Optional[int] = Field(default=None, description="Owner user ID.")
    is_archived: Optional[bool] = Field(default=None, description="Filter by archived status.")


class CustomFieldExtraData(BaseModel):
    """Extra configuration for a custom field. Shape depends on data_type."""
    options: Optional[list[str]] = Field(default=None, description="Select options. Used when data_type is 'select'.")
    currency: Optional[str] = Field(default=None, description="Currency code. Used when data_type is 'monetary'.")


# =============================================================================
# Document Tools
# =============================================================================

@mcp.tool()
async def get_all_documents(
    include_all_fields: bool = False,
    page: int = 1,
    page_size: int = 500,
    ctx: Context = None
) -> dict[str, Any]:
    """List all documents.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
        page: Page number for paginated results.
        page_size: Number of results per page.
    """
    data = await get_client().get_all_documents(
        get_user_token(),
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
        page=page,
        page_size=page_size,
    )
    return {"documents": json_to_toon(data)}


@mcp.tool()
async def get_document_by_id(
    id: int,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single document by its ID.

    Args:
        id: ID of the document.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_document_by_id(id, get_user_token(), include_all_fields=include_all_fields)


@mcp.tool()
async def update_document(
    id: int,
    title: Optional[str] = None,
    content: Optional[str] = None,
    correspondent: Optional[int] = None,
    document_type: Optional[int] = None,
    storage_path: Optional[int] = None,
    tags: Optional[list[int]] = None,
    created: Optional[str] = None,
    archive_serial_number: Optional[int] = None,
    owner: Optional[int] = None,
    remove_inbox_tags: Optional[bool] = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update a document's metadata.

    Args:
        id: ID of the document.
        title: Title of the document.
        content: Content/OCR text of the document.
        correspondent: Correspondent ID to assign. Null to unset.
        document_type: Document type ID to assign. Null to unset.
        storage_path: Storage path ID to assign. Null to unset.
        tags: Tag IDs to assign.
        created: ISO 8601 format (2026-06-22T15:00:00-04:00).
        archive_serial_number: Archive serial number to assign. 0 to unset.
        owner: Owner user ID to assign.
        remove_inbox_tags: Remove inbox tags when setting new tags.
    """
    params = UpdateDocumentParam(
        id=id, title=title, content=content,
        correspondent=correspondent, document_type=document_type,
        storage_path=storage_path, tags=tags,
        created=created, archive_serial_number=archive_serial_number,
        owner=owner, remove_inbox_tags=remove_inbox_tags,
    )
    return await get_client().update_document(
        id, params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )


@mcp.tool()
async def delete_document_by_id(
    id: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a document by its ID.

    Args:
        id: ID of the document.
    """
    return await get_client().delete_document_by_id(id, get_user_token())


@mcp.tool()
async def get_document_metadata(
    id: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Get file metadata for a document.

    Args:
        id: ID of the document.
    """
    return await get_client().get_document_metadata(id, get_user_token())


@mcp.tool()
async def get_document_suggestions(
    id: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Get ML-based suggestions for a document (correspondent, tags, document type, etc.).

    Args:
        id: ID of the document.
    """
    return await get_client().get_document_suggestions(id, get_user_token())


@mcp.tool()
async def get_document_ai_suggestions(
    id: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Get AI/LLM-based suggestions for a document.

    Args:
        id: ID of the document.
    """
    return await get_client().get_document_ai_suggestions(id, get_user_token())


@mcp.tool()
async def get_next_asn(ctx: Context = None) -> dict[str, Any]:
    """Get the next available Archive Serial Number."""
    data = await get_client().get_next_asn(get_user_token())
    return {"next_asn": data}


@mcp.tool()
async def get_document_download_url(
    id: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Get the download URL for a document's original file.

    Args:
        id: ID of the document.
    """
    public_url = PAPERLESS_PUBLIC_URL or os.getenv("PAPERLESS_BASE_URL", "").rstrip("/")
    return {"download_url": f"{public_url}/api/documents/{id}/download/"}


@mcp.tool()
async def get_document_preview_url(
    id: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Get the preview URL for a document.

    Args:
        id: ID of the document.
    """
    public_url = PAPERLESS_PUBLIC_URL or os.getenv("PAPERLESS_BASE_URL", "").rstrip("/")
    return {"preview_url": f"{public_url}/api/documents/{id}/preview/"}


@mcp.tool()
async def get_document_thumbnail_url(
    id: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Get the thumbnail URL for a document.

    Args:
        id: ID of the document.
    """
    public_url = PAPERLESS_PUBLIC_URL or os.getenv("PAPERLESS_BASE_URL", "").rstrip("/")
    return {"thumbnail_url": f"{public_url}/api/documents/{id}/thumb/"}


@mcp.tool()
async def bulk_update_documents(
    documents: list[int],
    method: str,
    parameters: BulkEditParams = BulkEditParams(),
    all: bool = False,
    filters: DocumentFilter = DocumentFilter(),
    ctx: Context = None
) -> dict[str, Any]:
    """Update multiple documents at once using a bulk edit method.

    Args:
        documents: Document IDs to update.
        method: set_correspondent, set_document_type, set_storage_path, add_tag, remove_tag, modify_tags, modify_custom_fields, or delete.
        parameters: Method-specific params, e.g. {"correspondent": 5} for set_correspondent or {"tag": 10} for add_tag.
        all: Apply to all documents matching filters instead of the documents list.
        filters: Filter criteria for bulk operations.
    """
    payload: dict[str, Any] = {
        "method": method,
        "parameters": parameters.model_dump(exclude_unset=True),
        "documents": documents,
    }
    if all:
        payload["all"] = True
    parsed_filters = filters.model_dump(exclude_none=True)
    if parsed_filters:
        payload["filters"] = parsed_filters
    data = await get_client().bulk_edit_documents(payload, get_user_token())
    return {"result": data}


@mcp.tool()
async def reprocess_documents(
    documents: list[int] = [],
    all: bool = False,
    filters: DocumentFilter = DocumentFilter(),
    ctx: Context = None
) -> dict[str, Any]:
    """Reprocess one or more documents.

    Args:
        documents: Document IDs to reprocess. Ignored when all is true.
        all: Reprocess all documents matching filters instead of the documents list.
        filters: Filter criteria for bulk operations.
    """
    payload: dict[str, Any] = {
        "documents": documents,
    }
    if all:
        payload["all"] = True
    parsed_filters = filters.model_dump(exclude_none=True)
    if parsed_filters:
        payload["filters"] = parsed_filters
    data = await get_client().reprocess_documents(payload, get_user_token())
    return {"result": data}


@mcp.tool()
async def assign_custom_field(
    documents: list[int],
    field_id: int,
    value: str = "",
    remove: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Assign or remove a custom field value on one or more documents.

    Args:
        documents: Document IDs to update.
        field_id: ID of the custom field definition.
        value: Value to assign as a string, e.g. "true", "2026-01-15", "42".
        remove: Remove the custom field from the documents instead of assigning a value.
    """
    doc_ids = documents
    if remove:
        params: dict[str, Any] = {"add_custom_fields": [], "remove_custom_fields": [field_id]}
    else:
        params = {"add_custom_fields": {str(field_id): value}, "remove_custom_fields": []}
    payload: dict[str, Any] = {
        "documents": doc_ids,
        "method": "modify_custom_fields",
        "parameters": params,
    }
    data = await get_client().bulk_edit_documents(payload, get_user_token())
    return {"result": data}


@mcp.tool()
async def get_document_notes(
    id: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Get all notes for a document.

    Args:
        id: ID of the document.
    """
    data = await get_client().get_document_notes(id, get_user_token())
    return {"notes": data}


@mcp.tool()
async def create_document_note(
    document_id: int,
    note: str,
    ctx: Context = None
) -> dict[str, Any]:
    """Add a note to a document.

    Args:
        document_id: ID of the document.
        note: The note text to add.
    """
    params = CreateNoteParam(note=note)
    data = await get_client().create_document_note(
        document_id, params.model_dump(exclude_unset=True), get_user_token()
    )
    return {"note": data}


@mcp.tool()
async def delete_document_note(
    document_id: int,
    note_id: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a note from a document.

    Args:
        document_id: ID of the document.
        note_id: The ID of the note to delete.
    """
    data = await get_client().delete_document_note(document_id, note_id, get_user_token())
    return {"notes": data}


# =============================================================================
# Correspondent Tools
# =============================================================================

@mcp.tool()
async def get_all_correspondents(
    include_all_fields: bool = False,
    page_size: int = 500,
    ctx: Context = None
) -> dict[str, Any]:
    """List all correspondents.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
        page_size: Number of results per page.
    """
    data = await get_client().get_all_correspondents(
        get_user_token(),
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
        page_size=page_size,
    )
    return {"correspondents": json_to_toon(data)}


@mcp.tool()
async def get_correspondent_by_id(
    id: int,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single correspondent by ID.

    Args:
        id: ID of the correspondent.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_correspondent_by_id(id, get_user_token(), include_all_fields=include_all_fields)


@mcp.tool()
async def create_correspondent(
    name: str,
    matching_algorithm: int = 1,
    is_insensitive: bool = True,
    match: str = "",
    owner: Optional[int] = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new correspondent.

    Args:
        name: Name of the correspondent.
        matching_algorithm: none, any_word, all_words, exact, regex, fuzzy, or automatic.
        is_insensitive: Case-insensitive matching.
        match: Pattern to match against. Used with matching_algorithm. Leave empty to disable.
        owner: Owner user ID.
    """
    matching_algo_int = _MATCHING_ALGO_MAP.get(matching_algorithm, matching_algorithm)
    params = CreateCorrespondentParam(
        name=name, matching_algorithm=matching_algo_int,
        is_insensitive=is_insensitive, match=match, owner=owner,
    )
    return await get_client().create_correspondent(
        params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )


@mcp.tool()
async def update_correspondent(
    id: int,
    name: Optional[str] = None,
    matching_algorithm: Optional[int] = None,
    is_insensitive: Optional[bool] = None,
    match: Optional[str] = None,
    owner: Optional[int] = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing correspondent.

    Args:
        id: ID of the correspondent.
        name: Name of the correspondent.
        matching_algorithm: none, any_word, all_words, exact, regex, fuzzy, or automatic.
        is_insensitive: Case-insensitive matching.
        match: Pattern to match against. Used with matching_algorithm. Leave empty to disable.
        owner: Owner user ID.
    """
    matching_algo_int = _MATCHING_ALGO_MAP.get(matching_algorithm, matching_algorithm)
    params = UpdateCorrespondentParam(
        id=id,         name=name, matching_algorithm=matching_algo_int,
        is_insensitive=is_insensitive, match=match, owner=owner,
    )
    return await get_client().update_correspondent(
        id, params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )


@mcp.tool()
async def delete_correspondent_by_id(
    id: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a correspondent by ID.

    Args:
        id: ID of the correspondent.
    """
    return await get_client().delete_correspondent_by_id(id, get_user_token())


# =============================================================================
# Document Type Tools
# =============================================================================

@mcp.tool()
async def get_all_document_types(
    include_all_fields: bool = False,
    page_size: int = 500,
    ctx: Context = None
) -> dict[str, Any]:
    """List all document types.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
        page_size: Number of results per page.
    """
    data = await get_client().get_all_document_types(
        get_user_token(),
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
        page_size=page_size,
    )
    return {"document_types": json_to_toon(data)}


@mcp.tool()
async def get_document_type_by_id(
    id: int,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single document type by ID.

    Args:
        id: ID of the document type.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_document_type_by_id(id, get_user_token(), include_all_fields=include_all_fields)


@mcp.tool()
async def create_document_type(
    name: str,
    matching_algorithm: int = 1,
    is_insensitive: bool = True,
    match: str = "",
    owner: Optional[int] = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new document type.

    Args:
        name: Name of the document type.
        matching_algorithm: none, any_word, all_words, exact, regex, fuzzy, or automatic.
        is_insensitive: Case-insensitive matching.
        match: Pattern to match against. Used with matching_algorithm. Leave empty to disable.
        owner: Owner user ID.
    """
    matching_algo_int = _MATCHING_ALGO_MAP.get(matching_algorithm, matching_algorithm)
    params = CreateDocumentTypeParam(
        name=name, matching_algorithm=matching_algo_int,
        is_insensitive=is_insensitive, match=match, owner=owner,
    )
    return await get_client().create_document_type(
        params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )


@mcp.tool()
async def update_document_type(
    id: int,
    name: Optional[str] = None,
    matching_algorithm: Optional[int] = None,
    is_insensitive: Optional[bool] = None,
    match: Optional[str] = None,
    owner: Optional[int] = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing document type.

    Args:
        id: ID of the document type.
        name: Name of the document type.
        matching_algorithm: none, any_word, all_words, exact, regex, fuzzy, or automatic.
        is_insensitive: Case-insensitive matching.
        match: Pattern to match against. Used with matching_algorithm. Leave empty to disable.
        owner: Owner user ID.
    """
    matching_algo_int = _MATCHING_ALGO_MAP.get(matching_algorithm, matching_algorithm)
    params = UpdateDocumentTypeParam(
        id=id,         name=name, matching_algorithm=matching_algo_int,
        is_insensitive=is_insensitive, match=match, owner=owner,
    )
    return await get_client().update_document_type(
        id, params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )


@mcp.tool()
async def delete_document_type_by_id(
    id: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a document type by ID.

    Args:
        id: ID of the document type.
    """
    return await get_client().delete_document_type_by_id(id, get_user_token())


# =============================================================================
# Tag Tools
# =============================================================================

@mcp.tool()
async def get_all_tags(
    include_all_fields: bool = False,
    page_size: int = 500,
    ctx: Context = None
) -> dict[str, Any]:
    """List all tags.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
        page_size: Number of results per page.
    """
    data = await get_client().get_all_tags(
        get_user_token(),
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
        page_size=page_size,
    )
    return {"tags": json_to_toon(data)}


@mcp.tool()
async def get_tag_by_id(
    id: int,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single tag by ID.

    Args:
        id: ID of the tag.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_tag_by_id(id, get_user_token(), include_all_fields=include_all_fields)


@mcp.tool()
async def create_tag(
    name: str,
    color: str = "#a6cee3",
    is_inbox_tag: bool = False,
    matching_algorithm: int = 1,
    is_insensitive: bool = True,
    match: str = "",
    parent: Optional[int] = None,
    owner: Optional[int] = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new tag.

    Args:
        name: Name of the tag.
        color: Hex color code, e.g. "#a6cee3".
        is_inbox_tag: Inbox tag.
        matching_algorithm: none, any_word, all_words, exact, regex, fuzzy, or automatic.
        is_insensitive: Case-insensitive matching.
        match: Pattern to match against. Used with matching_algorithm. Leave empty to disable.
        parent: Parent tag ID.
        owner: Owner user ID.
    """
    matching_algo_int = _MATCHING_ALGO_MAP.get(matching_algorithm, matching_algorithm)
    params = CreateTagParam(
        name=name, color=color, is_inbox_tag=is_inbox_tag,
        matching_algorithm=matching_algo_int, is_insensitive=is_insensitive,
        match=match, parent=parent, owner=owner,
    )
    return await get_client().create_tag(
        params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )


@mcp.tool()
async def update_tag(
    id: int,
    name: Optional[str] = None,
    color: Optional[str] = None,
    is_inbox_tag: Optional[bool] = None,
    matching_algorithm: Optional[int] = None,
    is_insensitive: Optional[bool] = None,
    match: Optional[str] = None,
    parent: Optional[int] = None,
    owner: Optional[int] = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing tag.

    Args:
        id: ID of the tag.
        name: Name of the tag.
        color: Hex color code, e.g. "#a6cee3".
        is_inbox_tag: Inbox tag.
        matching_algorithm: none, any_word, all_words, exact, regex, fuzzy, or automatic.
        is_insensitive: Case-insensitive matching.
        match: Pattern to match against. Used with matching_algorithm. Leave empty to disable.
        parent: Parent tag ID.
        owner: Owner user ID.
    """
    matching_algo_int = _MATCHING_ALGO_MAP.get(matching_algorithm, matching_algorithm)
    params = UpdateTagParam(
        id=id, name=name, color=color, is_inbox_tag=is_inbox_tag,
        matching_algorithm=matching_algo_int, is_insensitive=is_insensitive,
        match=match, parent=parent, owner=owner,
    )
    return await get_client().update_tag(
        id, params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )


@mcp.tool()
async def delete_tag_by_id(
    id: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a tag by ID.

    Args:
        id: ID of the tag.
    """
    return await get_client().delete_tag_by_id(id, get_user_token())


# =============================================================================
# Storage Path Tools
# =============================================================================

@mcp.tool()
async def get_all_storage_paths(
    include_all_fields: bool = False,
    page_size: int = 500,
    ctx: Context = None
) -> dict[str, Any]:
    """List all storage paths.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
        page_size: Number of results per page.
    """
    data = await get_client().get_all_storage_paths(
        get_user_token(),
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
        page_size=page_size,
    )
    return {"storage_paths": json_to_toon(data)}


@mcp.tool()
async def get_storage_path_by_id(
    id: int,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single storage path by ID.

    Args:
        id: ID of the storage path.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_storage_path_by_id(id, get_user_token(), include_all_fields=include_all_fields)


@mcp.tool()
async def create_storage_path(
    name: str,
    path: str,
    matching_algorithm: int = 6,
    is_insensitive: bool = True,
    match: str = "",
    owner: Optional[int] = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new storage path.

    Args:
        name: Name of the storage path.
        path: Storage path template, e.g. "{created_year}/{correspondent}/{title}".
        matching_algorithm: none, any_word, all_words, exact, regex, fuzzy, or automatic.
        is_insensitive: Case-insensitive matching.
        match: Pattern to match against. Used with matching_algorithm. Leave empty to disable.
        owner: Owner user ID.
    """
    matching_algo_int = _MATCHING_ALGO_MAP.get(matching_algorithm, matching_algorithm)
    params = CreateStoragePathParam(
        name=name, path=path, matching_algorithm=matching_algo_int,
        is_insensitive=is_insensitive, match=match, owner=owner,
    )
    return await get_client().create_storage_path(
        params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )


@mcp.tool()
async def update_storage_path(
    id: int,
    name: Optional[str] = None,
    path: Optional[str] = None,
    matching_algorithm: Optional[int] = None,
    is_insensitive: Optional[bool] = None,
    match: Optional[str] = None,
    owner: Optional[int] = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing storage path.

    Args:
        id: ID of the storage path.
        name: Name of the storage path.
        path: Storage path template, e.g. "{created_year}/{correspondent}/{title}".
        matching_algorithm: none, any_word, all_words, exact, regex, fuzzy, or automatic.
        is_insensitive: Case-insensitive matching.
        match: Pattern to match against. Used with matching_algorithm. Leave empty to disable.
        owner: Owner user ID.
    """
    matching_algo_int = _MATCHING_ALGO_MAP.get(matching_algorithm, matching_algorithm)
    params = UpdateStoragePathParam(
        id=id, name=name, path=path, matching_algorithm=matching_algo_int,
        is_insensitive=is_insensitive, match=match, owner=owner,
    )
    return await get_client().update_storage_path(
        id, params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )


@mcp.tool()
async def delete_storage_path_by_id(
    id: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a storage path by ID.

    Args:
        id: ID of the storage path.
    """
    return await get_client().delete_storage_path_by_id(id, get_user_token())


# =============================================================================
# Saved View Tools
# =============================================================================

@mcp.tool()
async def get_all_saved_views(
    include_all_fields: bool = False,
    page_size: int = 500,
    ctx: Context = None
) -> dict[str, Any]:
    """List all saved views.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
        page_size: Number of results per page.
    """
    data = await get_client().get_all_saved_views(
        get_user_token(),
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
        page_size=page_size,
    )
    return {"saved_views": json_to_toon(data)}


@mcp.tool()
async def get_saved_view_by_id(
    id: int,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single saved view by ID.

    Args:
        id: ID of the saved view.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_saved_view_by_id(id, get_user_token(), include_all_fields=include_all_fields)


@mcp.tool()
async def create_saved_view(
    name: str,
    show_on_dashboard: bool = False,
    show_in_sidebar: bool = True,
    sort_field: str = "created",
    sort_reverse: bool = True,
    filter_rules: list[FilterRule] = [],
    owner: Optional[int] = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new saved view.

    Args:
        name: Name of the saved view.
        show_on_dashboard: Show on dashboard.
        show_in_sidebar: Show in sidebar.
        sort_field: created, added, modified, archive_serial_number, title, correspondent, document_type, storage_path, owner, page_count, or num_notes.
        sort_reverse: Reverse sort order.
        filter_rules: List of filter rules, each with rule_type, value, and type.
        owner: Owner user ID.
    """
    parsed_rules = [{"rule_type": _FILTER_RULE_MAP.get(r.rule_type, r.rule_type), "value": r.value, "type": r.type} for r in filter_rules]
    params = CreateSavedViewParam(
        name=name, show_on_dashboard=show_on_dashboard,
        show_in_sidebar=show_in_sidebar, sort_field=sort_field,
        sort_reverse=sort_reverse, filter_rules=parsed_rules, owner=owner,
    )
    return await get_client().create_saved_view(
        params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )


@mcp.tool()
async def update_saved_view(
    id: int,
    name: Optional[str] = None,
    show_on_dashboard: Optional[bool] = None,
    show_in_sidebar: Optional[bool] = None,
    sort_field: Optional[str] = None,
    sort_reverse: Optional[bool] = None,
    filter_rules: Optional[list[FilterRule]] = None,
    owner: Optional[int] = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing saved view.

    Args:
        id: ID of the saved view.
        name: Name of the saved view.
        show_on_dashboard: Show on dashboard.
        show_in_sidebar: Show in sidebar.
        sort_field: created, added, modified, archive_serial_number, title, correspondent, document_type, storage_path, owner, page_count, or num_notes.
        sort_reverse: Reverse sort order.
        filter_rules: List of filter rules, each with rule_type, value, and type.
        owner: Owner user ID.
    """
    parsed_rules = [{"rule_type": _FILTER_RULE_MAP.get(r.rule_type, r.rule_type), "value": r.value, "type": r.type} for r in filter_rules] if filter_rules else None
    params = UpdateSavedViewParam(
        id=id, name=name, show_on_dashboard=show_on_dashboard,
        show_in_sidebar=show_in_sidebar, sort_field=sort_field,
        sort_reverse=sort_reverse, filter_rules=parsed_rules, owner=owner,
    )
    return await get_client().update_saved_view(
        id, params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )


@mcp.tool()
async def delete_saved_view_by_id(
    id: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a saved view by ID.

    Args:
        id: ID of the saved view.
    """
    return await get_client().delete_saved_view_by_id(id, get_user_token())


# =============================================================================
# Custom Field Tools
# =============================================================================

@mcp.tool()
async def get_all_custom_fields(
    include_all_fields: bool = False,
    page_size: int = 500,
    ctx: Context = None
) -> dict[str, Any]:
    """List all custom fields.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
        page_size: Number of results per page.
    """
    data = await get_client().get_all_custom_fields(
        get_user_token(),
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
        page_size=page_size,
    )
    return {"custom_fields": json_to_toon(data)}


@mcp.tool()
async def get_custom_field_by_id(
    id: int,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single custom field by ID.

    Args:
        id: ID of the custom field.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_custom_field_by_id(id, get_user_token(), include_all_fields=include_all_fields)


@mcp.tool()
async def create_custom_field(
    name: str,
    data_type: str,
    extra_data: str = "{}",
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new custom field.

    Args:
        name: Name of the custom field.
        data_type: string, url, date, boolean, integer, float, monetary, documentlink, select, or longtext.
        extra_data: JSON string with extra config, e.g. {"options": ["opt1", "opt2"]} for select or {"currency": "USD"} for monetary.
    """
    parsed_extra = json.loads(extra_data)
    params = CreateCustomFieldParam(name=name, data_type=data_type, extra_data=parsed_extra)
    return await get_client().create_custom_field(
        params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )


@mcp.tool()
async def update_custom_field(
    id: int,
    name: Optional[str] = None,
    data_type: Optional[str] = None,
    extra_data: Optional[str] = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing custom field.

    Args:
        id: ID of the custom field.
        name: Name of the custom field.
        data_type: string, url, date, boolean, integer, float, monetary, documentlink, select, or longtext.
        extra_data: JSON string with extra config, e.g. {"options": ["opt1", "opt2"]} for select or {"currency": "USD"} for monetary.
    """
    parsed_extra = json.loads(extra_data) if extra_data else None
    params = UpdateCustomFieldParam(
        id=id, name=name, data_type=data_type, extra_data=parsed_extra,
    )
    return await get_client().update_custom_field(
        id, params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )


@mcp.tool()
async def delete_custom_field_by_id(
    id: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a custom field by ID.

    Args:
        id: ID of the custom field.
    """
    return await get_client().delete_custom_field_by_id(id, get_user_token())


# =============================================================================
# Task Tools
# =============================================================================

@mcp.tool()
async def get_all_tasks(
    include_all_fields: bool = False,
    page_size: int = 500,
    ctx: Context = None
) -> dict[str, Any]:
    """List all tasks.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
        page_size: Number of results per page.
    """
    data = await get_client().get_all_tasks(
        get_user_token(),
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
        page_size=page_size,
    )
    return {"tasks": json_to_toon(data)}


@mcp.tool()
async def get_task_by_id(
    id: int,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single task by ID.

    Args:
        id: ID of the task.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_task_by_id(id, get_user_token(), include_all_fields=include_all_fields)


@mcp.tool()
async def get_task_summary(
    days: int = 30,
    ctx: Context = None
) -> dict[str, Any]:
    """Get aggregated task statistics.

    Args:
        days: Number of days to look back.
    """
    data = await get_client().get_task_summary(get_user_token(), days=days)
    return {"summary": data}


@mcp.tool()
async def get_task_status_counts(ctx: Context = None) -> dict[str, Any]:
    """Get counts of tasks by status."""
    return await get_client().get_task_status_counts(get_user_token())


@mcp.tool()
async def get_active_tasks(ctx: Context = None) -> dict[str, Any]:
    """Get currently pending or running tasks."""
    data = await get_client().get_active_tasks(get_user_token())
    return {"active_tasks": data}


@mcp.tool()
async def acknowledge_tasks(
    tasks: Optional[list[int]] = None,
    all_tasks: Optional[bool] = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Acknowledge one or more tasks.

    Args:
        tasks: Task IDs to acknowledge.
        all_tasks: Acknowledge all tasks.
    """
    params = AcknowledgeTasksParam(tasks=tasks, all=all_tasks)
    return await get_client().acknowledge_tasks(
        params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token()
    )


# =============================================================================
# Share Link Tools
# =============================================================================

@mcp.tool()
async def get_all_share_links(
    include_all_fields: bool = False,
    page_size: int = 500,
    ctx: Context = None
) -> dict[str, Any]:
    """List all share links.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
        page_size: Number of results per page.
    """
    data = await get_client().get_all_share_links(
        get_user_token(),
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
        page_size=page_size,
    )
    return {"share_links": json_to_toon(data)}


@mcp.tool()
async def get_share_link_by_id(
    id: int,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single share link by ID.

    Args:
        id: ID of the share link.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_share_link_by_id(id, get_user_token(), include_all_fields=include_all_fields)


@mcp.tool()
async def create_share_link(
    document: int,
    expiration: str,
    file_version: str = "archive",
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new share link.

    Args:
        document: ID of the document to share.
        expiration: ISO 8601 format (2026-06-22T15:00:00-04:00).
        file_version: archive or original.
    """
    params = CreateShareLinkParam(
        document=document, expiration=expiration, file_version=file_version,
    )
    return await get_client().create_share_link(
        params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )


@mcp.tool()
async def delete_share_link_by_id(
    id: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a share link by ID.

    Args:
        id: ID of the share link.
    """
    return await get_client().delete_share_link_by_id(id, get_user_token())


# =============================================================================
# Workflow Tools
# =============================================================================

@mcp.tool()
async def get_all_workflows(
    include_all_fields: bool = False,
    page_size: int = 500,
    ctx: Context = None
) -> dict[str, Any]:
    """List all workflows.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
        page_size: Number of results per page.
    """
    data = await get_client().get_all_workflows(
        get_user_token(),
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
        page_size=page_size,
    )
    return {"workflows": json_to_toon(data)}


@mcp.tool()
async def get_workflow_by_id(
    id: int,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single workflow by ID.

    Args:
        id: ID of the workflow.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_workflow_by_id(id, get_user_token(), include_all_fields=include_all_fields)


@mcp.tool()
async def create_workflow(
    name: str,
    triggers: list[WorkflowTrigger] = [WorkflowTrigger()],
    actions: list[str] = ["assign"],
    order: int = 1,
    enabled: bool = True,
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new workflow.

    Args:
        name: Name of the workflow.
        triggers: List of triggers, each with type and filter_path.
        actions: assign, remove, email, webhook, remove_password, or trash.
        order: Display order.
        enabled: Workflow is enabled.
    """
    parsed_triggers = [{"type": _WORKFLOW_TRIGGER_MAP.get(t.type, t.type), "filter_path": t.filter_path} for t in triggers]
    parsed_actions = [{"type": _WORKFLOW_ACTION_MAP.get(a, a)} for a in actions]
    params = CreateWorkflowParam(
        name=name, order=order, enabled=enabled,
    )
    payload = params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True)
    payload["triggers"] = parsed_triggers
    payload["actions"] = parsed_actions
    return await get_client().create_workflow(
        payload, get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )


@mcp.tool()
async def update_workflow(
    id: int,
    name: Optional[str] = None,
    triggers: Optional[list[WorkflowTrigger]] = None,
    actions: Optional[list[str]] = None,
    order: Optional[int] = None,
    enabled: Optional[bool] = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing workflow.

    Args:
        id: ID of the workflow.
        name: Name of the workflow.
        triggers: List of triggers, each with type and filter_path.
        actions: assign, remove, email, webhook, remove_password, or trash.
        order: Display order.
        enabled: Workflow is enabled.
    """
    parsed_triggers = [{"type": _WORKFLOW_TRIGGER_MAP.get(t.type, t.type), "filter_path": t.filter_path} for t in triggers] if triggers else None
    parsed_actions = [{"type": _WORKFLOW_ACTION_MAP.get(a, a)} for a in actions] if actions else None
    params = UpdateWorkflowParam(
        id=id, name=name, order=order, enabled=enabled,
    )
    payload = params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True)
    if parsed_triggers is not None:
        payload["triggers"] = parsed_triggers
    if parsed_actions is not None:
        payload["actions"] = parsed_actions
    return await get_client().update_workflow(
        id, payload, get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )


@mcp.tool()
async def delete_workflow_by_id(
    id: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a workflow by ID.

    Args:
        id: ID of the workflow.
    """
    return await get_client().delete_workflow_by_id(id, get_user_token())


# =============================================================================
# Mail Account Tools
# =============================================================================

@mcp.tool()
async def get_all_mail_accounts(
    include_all_fields: bool = False,
    page_size: int = 500,
    ctx: Context = None
) -> dict[str, Any]:
    """List all mail accounts.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
        page_size: Number of results per page.
    """
    data = await get_client().get_all_mail_accounts(
        get_user_token(),
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
        page_size=page_size,
    )
    return {"mail_accounts": json_to_toon(data)}


@mcp.tool()
async def get_mail_account_by_id(
    id: int,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single mail account by ID.

    Args:
        id: ID of the mail account.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_mail_account_by_id(id, get_user_token(), include_all_fields=include_all_fields)


@mcp.tool()
async def create_mail_account(
    name: str,
    username: str,
    password: str,
    imap_server: str = "imap.gmail.com",
    imap_port: int = 993,
    imap_security: str = "ssl_tls",
    character_set: str = "UTF-8",
    folder: str = "INBOX",
    is_active: bool = True,
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new mail account.

    Args:
        name: Name of the mail account.
        username: Username for the mail account.
        password: Password for the mail account.
        imap_server: IMAP server hostname.
        imap_port: IMAP server port.
        imap_security: none, ssl_tls, or starttls.
        character_set: IMAP character set, e.g. "UTF-8".
        folder: Mail folder to monitor.
        is_active: Account is active.
    """
    imap_security_int = _IMAP_SECURITY_MAP.get(imap_security, imap_security)
    params = CreateMailAccountParam(
        name=name, username=username, password=password,
        imap_server=imap_server, imap_port=imap_port,
        imap_security=imap_security_int, character_set=character_set,
        folder=folder, is_active=is_active,
    )
    return await get_client().create_mail_account(
        params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )


@mcp.tool()
async def update_mail_account(
    id: int,
    name: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    imap_server: Optional[str] = None,
    imap_port: Optional[int] = None,
    imap_security: Optional[str] = None,
    character_set: Optional[str] = None,
    folder: Optional[str] = None,
    is_active: Optional[bool] = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing mail account.

    Args:
        id: ID of the mail account.
        name: Name of the mail account.
        username: Username.
        password: Password.
        imap_server: IMAP server hostname.
        imap_port: IMAP server port.
        imap_security: none, ssl_tls, or starttls.
        character_set: IMAP character set, e.g. "UTF-8".
        folder: Mail folder.
        is_active: Account is active.
    """
    imap_security_int = _IMAP_SECURITY_MAP.get(imap_security, imap_security) if imap_security is not None else None
    params = UpdateMailAccountParam(
        id=id, name=name, username=username, password=password,
        imap_server=imap_server, imap_port=imap_port,
        imap_security=imap_security_int, character_set=character_set,
        folder=folder, is_active=is_active,
    )
    return await get_client().update_mail_account(
        id, params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )


@mcp.tool()
async def delete_mail_account_by_id(
    id: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a mail account by ID.

    Args:
        id: ID of the mail account.
    """
    return await get_client().delete_mail_account_by_id(id, get_user_token())


# =============================================================================
# Mail Rule Tools
# =============================================================================

@mcp.tool()
async def get_all_mail_rules(
    include_all_fields: bool = False,
    page_size: int = 500,
    ctx: Context = None
) -> dict[str, Any]:
    """List all mail rules.

    Args:
        include_all_fields: Default False (common fields only). Set True for all fields.
        page_size: Number of results per page.
    """
    data = await get_client().get_all_mail_rules(
        get_user_token(),
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False,
        page_size=page_size,
    )
    return {"mail_rules": json_to_toon(data)}


@mcp.tool()
async def get_mail_rule_by_id(
    id: int,
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Get a single mail rule by ID.

    Args:
        id: ID of the mail rule.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    return await get_client().get_mail_rule_by_id(id, get_user_token(), include_all_fields=include_all_fields)


@mcp.tool()
async def create_mail_rule(
    name: str,
    account: int,
    action: str,
    folder: str,
    filter_to: str = "*",
    filter_from: str = "*",
    filter_subject: str = "*",
    filter_attachment_filename: str = "*",
    maximum_age: int = 30,
    order: int = 0,
    assign_title: Optional[str] = None,
    assign_tags: Optional[str] = None,
    assign_correspondent: Optional[int] = None,
    assign_document_type: Optional[int] = None,
    assign_storage_path: Optional[int] = None,
    assign_owner: Optional[int] = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new mail rule.

    Args:
        name: Name of the mail rule.
        account: ID of the mail account.
        action: delete, mark_read, flag, move, or copy.
        folder: Folder to apply rule to.
        filter_to: Filter by To address. Use "*" for all.
        filter_from: Filter by From address. Use "*" for all.
        filter_subject: Filter by subject. Use "*" for all.
        filter_attachment_filename: Filter by attachment filename. Use "*" for all.
        maximum_age: Maximum age of messages in days.
        order: Rule order.
        assign_title: Title template to assign.
        assign_tags: Comma-separated tag IDs, e.g. "1,2,3".
        assign_correspondent: Correspondent ID to assign.
        assign_document_type: Document type ID to assign.
        assign_storage_path: Storage path ID to assign.
        assign_owner: Owner user ID to assign.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    action_int = _MAIL_RULE_ACTION_MAP.get(action, action)
    tag_list = [int(t.strip()) for t in assign_tags.split(",")] if assign_tags is not None else None
    params = CreateMailRuleParam(
        name=name, account=account, action=action_int, folder=folder,
        filter_to=filter_to, filter_from=filter_from,
        filter_subject=filter_subject,
        filter_attachment_filename=filter_attachment_filename,
        maximum_age=maximum_age, order=order,
        assign_title=assign_title, assign_tags=tag_list,
        assign_correspondent=assign_correspondent,
        assign_document_type=assign_document_type,
        assign_storage_path=assign_storage_path,
        assign_owner=assign_owner,
    )
    return await get_client().create_mail_rule(
        params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )


@mcp.tool()
async def update_mail_rule(
    id: int,
    name: Optional[str] = None,
    account: Optional[int] = None,
    action: Optional[str] = None,
    folder: Optional[str] = None,
    filter_to: Optional[str] = None,
    filter_from: Optional[str] = None,
    filter_subject: Optional[str] = None,
    filter_attachment_filename: Optional[str] = None,
    maximum_age: Optional[int] = None,
    order: Optional[int] = None,
    assign_title: Optional[str] = None,
    assign_tags: Optional[str] = None,
    assign_correspondent: Optional[int] = None,
    assign_document_type: Optional[int] = None,
    assign_storage_path: Optional[int] = None,
    assign_owner: Optional[int] = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing mail rule.

    Args:
        id: ID of the mail rule.
        name: Name of the mail rule.
        account: Mail account ID.
        action: delete, mark_read, flag, move, or copy.
        folder: Folder to apply rule to.
        filter_to: Filter by To address. Use "*" for all.
        filter_from: Filter by From address. Use "*" for all.
        filter_subject: Filter by subject. Use "*" for all.
        filter_attachment_filename: Filter by attachment filename. Use "*" for all.
        maximum_age: Maximum age of messages in days.
        order: Rule order.
        assign_title: Title template to assign.
        assign_tags: Comma-separated tag IDs, e.g. "1,2,3".
        assign_correspondent: Correspondent ID to assign.
        assign_document_type: Document type ID to assign.
        assign_storage_path: Storage path ID to assign.
        assign_owner: Owner user ID to assign.
        include_all_fields: Default False (common fields only). Set True for all fields.
    """
    action_int = _MAIL_RULE_ACTION_MAP.get(action, action) if action is not None else None
    tag_list = [int(t.strip()) for t in assign_tags.split(",")] if assign_tags is not None else None
    params = UpdateMailRuleParam(
        id=id, name=name, account=account, action=action_int, folder=folder,
        filter_to=filter_to, filter_from=filter_from,
        filter_subject=filter_subject,
        filter_attachment_filename=filter_attachment_filename,
        maximum_age=maximum_age, order=order,
        assign_title=assign_title, assign_tags=tag_list,
        assign_correspondent=assign_correspondent,
        assign_document_type=assign_document_type,
        assign_storage_path=assign_storage_path,
        assign_owner=assign_owner,
    )
    return await get_client().update_mail_rule(
        id, params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token(),
        include_all_fields=ALLOW_ALL_AGGREGATE
    )


@mcp.tool()
async def delete_mail_rule_by_id(
    id: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a mail rule by ID.

    Args:
        id: ID of the mail rule.
    """
    return await get_client().delete_mail_rule_by_id(id, get_user_token())


# =============================================================================
# Search Tools
# =============================================================================

@mcp.tool()
async def search_documents(
    query: str,
    limit: int = 50,
    db_only: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """Search across documents.

    Args:
        query: Search keyword or phrase.
        limit: Maximum number of results.
        db_only: Search database only (no full-text index).
    """
    data = await get_client().search_documents(query, get_user_token(), limit=limit, db_only=db_only)
    return {"results": json_to_toon(data)}


@mcp.tool()
async def search_autocomplete(
    term: str,
    limit: int = 10,
    ctx: Context = None
) -> dict[str, Any]:
    """Get search autocomplete suggestions.

    Args:
        term: The search term prefix.
        limit: Maximum number of suggestions.
    """
    data = await get_client().search_autocomplete(term, get_user_token(), limit=limit)
    return {"suggestions": data}


# =============================================================================
# System Tools
# =============================================================================

@mcp.tool()
async def get_statistics(ctx: Context = None) -> dict[str, Any]:
    """Get document and statistics counts for the current user."""
    return await get_client().get_statistics(get_user_token())


@mcp.tool()
async def check_server_status(ctx: Context = None) -> dict[str, Any]:
    """Check connectivity and status of the Paperless backend."""
    try:
        data = await get_client().check_server_status(get_user_token())
        return {"status": "connected", "data": data}
    except Exception as e:
        return {"status": "disconnected", "error": str(e)}


# =============================================================================
# Entry Point
# =============================================================================

def main():
    if not os.getenv("PAPERLESS_BASE_URL"):
        print("ERROR: PAPERLESS_BASE_URL environment variable is required", file=sys.stderr)
        print("Example: export PAPERLESS_BASE_URL=http://paperless-app:8000", file=sys.stderr)
        sys.exit(1)

    port_env = os.getenv("MCP_SERVER_PORT")
    if not port_env:
        print("ERROR: MCP_SERVER_PORT environment variable is required", file=sys.stderr)
        print("Example: export MCP_SERVER_PORT=6038", file=sys.stderr)
        sys.exit(1)

    host = "0.0.0.0"
    port = int(port_env)
    path = "/mcp"
    app = mcp.http_app(path=path, json_response=True, stateless_http=True)
    app = AuthMiddleware(app)
    print(f"Starting Paperless MCP server on http://{host}:{port}{path}")
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
