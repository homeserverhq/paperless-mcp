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


# =============================================================================
# Document Tools
# =============================================================================

@mcp.tool()
async def get_all_documents(
    include_all_fields: bool = False,
    page: int = 1,
    page_size: int = 100,
    ctx: Context = None
) -> dict[str, Any]:
    """List all documents.

    Args:
        include_all_fields: When False (default), each document contains only commonly used fields. Set to True to include all fields.
        page: Page number for paginated results. Defaults to 1.
        page_size: Number of results per page. Defaults to 100.
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
        id: The unique ID of the document.
        include_all_fields: When False (default), returns only commonly used fields. Set to True to retrieve all available fields.
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
    tags: Optional[str] = None,
    created: Optional[str] = None,
    archive_serial_number: Optional[int] = None,
    owner: Optional[int] = None,
    remove_inbox_tags: Optional[bool] = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update a document's metadata.

    Args:
        id: The unique ID of the document to update.
        title: New title for the document.
        content: New content/OCR text for the document.
        correspondent: ID of the correspondent to assign (null to unset).
        document_type: ID of the document type to assign (null to unset).
        storage_path: ID of the storage path to assign (null to unset).
        tags: Comma-separated list of tag IDs to assign.
        created: Use ISO 8601 format with explicit UTC offset (2026-06-22T15:00:00-04:00).
        archive_serial_number: Archive serial number to assign (0 to unset).
        owner: ID of the owner user to assign.
        remove_inbox_tags: Set to true to remove inbox tags when setting new tags.
    """
    tag_list = [int(t.strip()) for t in tags.split(",")] if tags else None
    params = UpdateDocumentParam(
        id=id, title=title, content=content,
        correspondent=correspondent, document_type=document_type,
        storage_path=storage_path, tags=tag_list,
        created=created, archive_serial_number=archive_serial_number,
        owner=owner, remove_inbox_tags=remove_inbox_tags,
    )
    return await get_client().update_document(
        id, params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token()
    )


@mcp.tool()
async def delete_document_by_id(
    id: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a document by its ID.

    Args:
        id: The unique ID of the document to delete (required).
    """
    return await get_client().delete_document_by_id(id, get_user_token())


@mcp.tool()
async def get_document_metadata(
    id: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Get file metadata for a document.

    Args:
        id: The unique ID of the document (required).
    """
    return await get_client().get_document_metadata(id, get_user_token())


@mcp.tool()
async def get_document_suggestions(
    id: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Get ML-based suggestions for a document (correspondent, tags, document type, etc.).

    Args:
        id: The unique ID of the document (required).
    """
    return await get_client().get_document_suggestions(id, get_user_token())


@mcp.tool()
async def get_document_ai_suggestions(
    id: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Get AI/LLM-based suggestions for a document.

    Args:
        id: The unique ID of the document (required).
    """
    return await get_client().get_document_ai_suggestions(id, get_user_token())


@mcp.tool()
async def get_next_asn(ctx: Context = None) -> dict[str, Any]:
    """Get the next available Archive Serial Number."""
    data = await get_client().get_next_asn(get_user_token())
    return {"next_asn": data}


@mcp.tool()
async def get_document_notes(
    id: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Get all notes for a document.

    Args:
        id: The unique ID of the document (required).
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
        document_id: The unique ID of the document (required).
        note: The note text to add (required).
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
        document_id: The unique ID of the document (required).
        note_id: The ID of the note to delete (required).
    """
    data = await get_client().delete_document_note(document_id, note_id, get_user_token())
    return {"notes": data}


# =============================================================================
# Correspondent Tools
# =============================================================================

@mcp.tool()
async def get_all_correspondents(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """List all correspondents.

    Args:
        include_all_fields: When False (default), returns only commonly used fields. Set to True to include all fields.
    """
    data = await get_client().get_all_correspondents(
        get_user_token(),
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False
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
        id: The unique ID of the correspondent.
        include_all_fields: When False (default), returns only commonly used fields. Set to True to retrieve all available fields.
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
        name: Name of the new correspondent (required).
        matching_algorithm: Matching algorithm ID. Defaults to 1 (any).
        is_insensitive: Whether matching is case-insensitive. Defaults to True.
        match: Match pattern string.
        owner: ID of the owner user.
    """
    params = CreateCorrespondentParam(
        name=name, matching_algorithm=matching_algorithm,
        is_insensitive=is_insensitive, match=match, owner=owner,
    )
    return await get_client().create_correspondent(
        params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token()
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
        id: The unique ID of the correspondent to update (required).
        name: New name for the correspondent.
        matching_algorithm: New matching algorithm ID.
        is_insensitive: Whether matching is case-insensitive.
        match: New match pattern string.
        owner: ID of the owner user.
    """
    params = UpdateCorrespondentParam(
        id=id, name=name, matching_algorithm=matching_algorithm,
        is_insensitive=is_insensitive, match=match, owner=owner,
    )
    return await get_client().update_correspondent(
        id, params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token()
    )


@mcp.tool()
async def delete_correspondent_by_id(
    id: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a correspondent by ID.

    Args:
        id: The unique ID of the correspondent to delete (required).
    """
    return await get_client().delete_correspondent_by_id(id, get_user_token())


# =============================================================================
# Document Type Tools
# =============================================================================

@mcp.tool()
async def get_all_document_types(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """List all document types.

    Args:
        include_all_fields: When False (default), returns only commonly used fields. Set to True to include all fields.
    """
    data = await get_client().get_all_document_types(
        get_user_token(),
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False
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
        id: The unique ID of the document type.
        include_all_fields: When False (default), returns only commonly used fields. Set to True to retrieve all available fields.
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
        name: Name of the new document type (required).
        matching_algorithm: Matching algorithm ID. Defaults to 1 (any).
        is_insensitive: Whether matching is case-insensitive. Defaults to True.
        match: Match pattern string.
        owner: ID of the owner user.
    """
    params = CreateDocumentTypeParam(
        name=name, matching_algorithm=matching_algorithm,
        is_insensitive=is_insensitive, match=match, owner=owner,
    )
    return await get_client().create_document_type(
        params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token()
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
        id: The unique ID of the document type to update (required).
        name: New name for the document type.
        matching_algorithm: New matching algorithm ID.
        is_insensitive: Whether matching is case-insensitive.
        match: New match pattern string.
        owner: ID of the owner user.
    """
    params = UpdateDocumentTypeParam(
        id=id, name=name, matching_algorithm=matching_algorithm,
        is_insensitive=is_insensitive, match=match, owner=owner,
    )
    return await get_client().update_document_type(
        id, params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token()
    )


@mcp.tool()
async def delete_document_type_by_id(
    id: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a document type by ID.

    Args:
        id: The unique ID of the document type to delete (required).
    """
    return await get_client().delete_document_type_by_id(id, get_user_token())


# =============================================================================
# Tag Tools
# =============================================================================

@mcp.tool()
async def get_all_tags(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """List all tags.

    Args:
        include_all_fields: When False (default), returns only commonly used fields. Set to True to include all fields.
    """
    data = await get_client().get_all_tags(
        get_user_token(),
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False
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
        id: The unique ID of the tag.
        include_all_fields: When False (default), returns only commonly used fields. Set to True to retrieve all available fields.
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
        name: Name of the new tag (required).
        color: Hex color code. Defaults to "#a6cee3".
        is_inbox_tag: Whether this is an inbox tag. Defaults to False.
        matching_algorithm: Matching algorithm ID. Defaults to 1 (any).
        is_insensitive: Whether matching is case-insensitive. Defaults to True.
        match: Match pattern string.
        parent: ID of the parent tag.
        owner: ID of the owner user.
    """
    params = CreateTagParam(
        name=name, color=color, is_inbox_tag=is_inbox_tag,
        matching_algorithm=matching_algorithm, is_insensitive=is_insensitive,
        match=match, parent=parent, owner=owner,
    )
    return await get_client().create_tag(
        params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token()
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
        id: The unique ID of the tag to update (required).
        name: New name for the tag.
        color: New hex color code.
        is_inbox_tag: Whether this is an inbox tag.
        matching_algorithm: New matching algorithm ID.
        is_insensitive: Whether matching is case-insensitive.
        match: New match pattern string.
        parent: ID of the parent tag.
        owner: ID of the owner user.
    """
    params = UpdateTagParam(
        id=id, name=name, color=color, is_inbox_tag=is_inbox_tag,
        matching_algorithm=matching_algorithm, is_insensitive=is_insensitive,
        match=match, parent=parent, owner=owner,
    )
    return await get_client().update_tag(
        id, params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token()
    )


@mcp.tool()
async def delete_tag_by_id(
    id: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a tag by ID.

    Args:
        id: The unique ID of the tag to delete (required).
    """
    return await get_client().delete_tag_by_id(id, get_user_token())


# =============================================================================
# Storage Path Tools
# =============================================================================

@mcp.tool()
async def get_all_storage_paths(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """List all storage paths.

    Args:
        include_all_fields: When False (default), returns only commonly used fields. Set to True to include all fields.
    """
    data = await get_client().get_all_storage_paths(
        get_user_token(),
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False
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
        id: The unique ID of the storage path.
        include_all_fields: When False (default), returns only commonly used fields. Set to True to retrieve all available fields.
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
        name: Name of the new storage path (required).
        path: The storage path template (required).
        matching_algorithm: Matching algorithm ID. Defaults to 6 (auto).
        is_insensitive: Whether matching is case-insensitive. Defaults to True.
        match: Match pattern string.
        owner: ID of the owner user.
    """
    params = CreateStoragePathParam(
        name=name, path=path, matching_algorithm=matching_algorithm,
        is_insensitive=is_insensitive, match=match, owner=owner,
    )
    return await get_client().create_storage_path(
        params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token()
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
        id: The unique ID of the storage path to update (required).
        name: New name for the storage path.
        path: New storage path template.
        matching_algorithm: New matching algorithm ID.
        is_insensitive: Whether matching is case-insensitive.
        match: New match pattern string.
        owner: ID of the owner user.
    """
    params = UpdateStoragePathParam(
        id=id, name=name, path=path, matching_algorithm=matching_algorithm,
        is_insensitive=is_insensitive, match=match, owner=owner,
    )
    return await get_client().update_storage_path(
        id, params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token()
    )


@mcp.tool()
async def delete_storage_path_by_id(
    id: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a storage path by ID.

    Args:
        id: The unique ID of the storage path to delete (required).
    """
    return await get_client().delete_storage_path_by_id(id, get_user_token())


# =============================================================================
# Saved View Tools
# =============================================================================

@mcp.tool()
async def get_all_saved_views(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """List all saved views.

    Args:
        include_all_fields: When False (default), returns only commonly used fields. Set to True to include all fields.
    """
    data = await get_client().get_all_saved_views(
        get_user_token(),
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False
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
        id: The unique ID of the saved view.
        include_all_fields: When False (default), returns only commonly used fields. Set to True to retrieve all available fields.
    """
    return await get_client().get_saved_view_by_id(id, get_user_token(), include_all_fields=include_all_fields)


@mcp.tool()
async def create_saved_view(
    name: str,
    show_on_dashboard: bool = False,
    show_in_sidebar: bool = True,
    sort_field: str = "created",
    sort_reverse: bool = True,
    filter_rules: str = "[]",
    owner: Optional[int] = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new saved view.

    Args:
        name: Name of the new saved view (required).
        show_on_dashboard: Show on dashboard. Defaults to False.
        show_in_sidebar: Show in sidebar. Defaults to True.
        sort_field: Field to sort by. Defaults to "created".
        sort_reverse: Reverse sort order. Defaults to True.
        filter_rules: JSON string of filter rules. Defaults to "[]".
        owner: ID of the owner user.
    """
    import json as _json
    parsed_rules = _json.loads(filter_rules)
    params = CreateSavedViewParam(
        name=name, show_on_dashboard=show_on_dashboard,
        show_in_sidebar=show_in_sidebar, sort_field=sort_field,
        sort_reverse=sort_reverse, filter_rules=parsed_rules, owner=owner,
    )
    return await get_client().create_saved_view(
        params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token()
    )


@mcp.tool()
async def update_saved_view(
    id: int,
    name: Optional[str] = None,
    show_on_dashboard: Optional[bool] = None,
    show_in_sidebar: Optional[bool] = None,
    sort_field: Optional[str] = None,
    sort_reverse: Optional[bool] = None,
    filter_rules: Optional[str] = None,
    owner: Optional[int] = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing saved view.

    Args:
        id: The unique ID of the saved view to update (required).
        name: New name for the saved view.
        show_on_dashboard: Show on dashboard.
        show_in_sidebar: Show in sidebar.
        sort_field: Field to sort by.
        sort_reverse: Reverse sort order.
        filter_rules: JSON string of filter rules.
        owner: ID of the owner user.
    """
    import json as _json
    parsed_rules = _json.loads(filter_rules) if filter_rules else None
    params = UpdateSavedViewParam(
        id=id, name=name, show_on_dashboard=show_on_dashboard,
        show_in_sidebar=show_in_sidebar, sort_field=sort_field,
        sort_reverse=sort_reverse, filter_rules=parsed_rules, owner=owner,
    )
    return await get_client().update_saved_view(
        id, params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token()
    )


@mcp.tool()
async def delete_saved_view_by_id(
    id: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a saved view by ID.

    Args:
        id: The unique ID of the saved view to delete (required).
    """
    return await get_client().delete_saved_view_by_id(id, get_user_token())


# =============================================================================
# Custom Field Tools
# =============================================================================

@mcp.tool()
async def get_all_custom_fields(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """List all custom fields.

    Args:
        include_all_fields: When False (default), returns only commonly used fields. Set to True to include all fields.
    """
    data = await get_client().get_all_custom_fields(
        get_user_token(),
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False
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
        id: The unique ID of the custom field.
        include_all_fields: When False (default), returns only commonly used fields. Set to True to retrieve all available fields.
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
        name: Name of the new custom field (required).
        data_type: Data type (string, number, boolean, date, documentlink, select, monetary) (required).
        extra_data: JSON string of extra configuration data. Defaults to "{}".
    """
    import json as _json
    parsed_extra = _json.loads(extra_data)
    params = CreateCustomFieldParam(name=name, data_type=data_type, extra_data=parsed_extra)
    return await get_client().create_custom_field(
        params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token()
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
        id: The unique ID of the custom field to update (required).
        name: New name for the custom field.
        data_type: New data type.
        extra_data: JSON string of extra configuration data.
    """
    import json as _json
    parsed_extra = _json.loads(extra_data) if extra_data else None
    params = UpdateCustomFieldParam(
        id=id, name=name, data_type=data_type, extra_data=parsed_extra,
    )
    return await get_client().update_custom_field(
        id, params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token()
    )


@mcp.tool()
async def delete_custom_field_by_id(
    id: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a custom field by ID.

    Args:
        id: The unique ID of the custom field to delete (required).
    """
    return await get_client().delete_custom_field_by_id(id, get_user_token())


# =============================================================================
# Task Tools
# =============================================================================

@mcp.tool()
async def get_all_tasks(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """List all tasks.

    Args:
        include_all_fields: When False (default), returns only commonly used fields. Set to True to include all fields.
    """
    data = await get_client().get_all_tasks(
        get_user_token(),
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False
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
        id: The unique ID of the task.
        include_all_fields: When False (default), returns only commonly used fields. Set to True to retrieve all available fields.
    """
    return await get_client().get_task_by_id(id, get_user_token(), include_all_fields=include_all_fields)


@mcp.tool()
async def get_task_summary(
    days: int = 30,
    ctx: Context = None
) -> dict[str, Any]:
    """Get aggregated task statistics.

    Args:
        days: Number of days to look back. Defaults to 30.
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
    tasks: Optional[str] = None,
    all_tasks: Optional[bool] = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Acknowledge one or more tasks.

    Args:
        tasks: Comma-separated list of task IDs to acknowledge.
        all_tasks: Set to true to acknowledge all tasks.
    """
    task_list = [int(t.strip()) for t in tasks.split(",")] if tasks else None
    params = AcknowledgeTasksParam(tasks=task_list, all=all_tasks)
    return await get_client().acknowledge_tasks(
        params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token()
    )


# =============================================================================
# Share Link Tools
# =============================================================================

@mcp.tool()
async def get_all_share_links(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """List all share links.

    Args:
        include_all_fields: When False (default), returns only commonly used fields. Set to True to include all fields.
    """
    data = await get_client().get_all_share_links(
        get_user_token(),
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False
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
        id: The unique ID of the share link.
        include_all_fields: When False (default), returns only commonly used fields. Set to True to retrieve all available fields.
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
        document: The ID of the document to share (required).
        expiration: Use ISO 8601 format with explicit UTC offset (2026-06-22T15:00:00-04:00).
        file_version: File version to share. Defaults to "archive".
    """
    params = CreateShareLinkParam(
        document=document, expiration=expiration, file_version=file_version,
    )
    return await get_client().create_share_link(
        params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token()
    )


@mcp.tool()
async def delete_share_link_by_id(
    id: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a share link by ID.

    Args:
        id: The unique ID of the share link to delete (required).
    """
    return await get_client().delete_share_link_by_id(id, get_user_token())


# =============================================================================
# Workflow Tools
# =============================================================================

@mcp.tool()
async def get_all_workflows(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """List all workflows.

    Args:
        include_all_fields: When False (default), returns only commonly used fields. Set to True to include all fields.
    """
    data = await get_client().get_all_workflows(
        get_user_token(),
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False
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
        id: The unique ID of the workflow.
        include_all_fields: When False (default), returns only commonly used fields. Set to True to retrieve all available fields.
    """
    return await get_client().get_workflow_by_id(id, get_user_token(), include_all_fields=include_all_fields)


@mcp.tool()
async def create_workflow(
    name: str,
    triggers: str = "[{\"type\": 1, \"filter_path\": \"/*\"}]",
    actions: str = "[{\"type\": 1}]",
    order: int = 1,
    enabled: bool = True,
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new workflow.

    Args:
        name: Name of the new workflow (required).
        triggers: JSON string of trigger definitions. Defaults to a basic file-watching trigger.
        actions: JSON string of action definitions. Defaults to a basic action.
        order: Display order. Defaults to 1.
        enabled: Whether the workflow is enabled. Defaults to True.
    """
    import json as _json
    parsed_triggers = _json.loads(triggers)
    parsed_actions = _json.loads(actions)
    params = CreateWorkflowParam(
        name=name, order=order, enabled=enabled,
        triggers=triggers, actions=actions,
    )
    payload = params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True)
    payload["triggers"] = parsed_triggers
    payload["actions"] = parsed_actions
    return await get_client().create_workflow(
        payload, get_user_token()
    )


@mcp.tool()
async def update_workflow(
    id: int,
    name: Optional[str] = None,
    triggers: Optional[str] = None,
    actions: Optional[str] = None,
    order: Optional[int] = None,
    enabled: Optional[bool] = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing workflow.

    Args:
        id: The unique ID of the workflow to update (required).
        name: New name for the workflow.
        triggers: JSON string of trigger definitions.
        actions: JSON string of action definitions.
        order: New display order.
        enabled: Whether the workflow is enabled.
    """
    import json as _json
    parsed_triggers = _json.loads(triggers) if triggers else None
    parsed_actions = _json.loads(actions) if actions else None
    params = UpdateWorkflowParam(
        id=id, name=name, order=order, enabled=enabled,
        triggers=triggers, actions=actions,
    )
    payload = params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True)
    if parsed_triggers is not None:
        payload["triggers"] = parsed_triggers
    if parsed_actions is not None:
        payload["actions"] = parsed_actions
    return await get_client().update_workflow(
        id, payload, get_user_token()
    )


@mcp.tool()
async def delete_workflow_by_id(
    id: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a workflow by ID.

    Args:
        id: The unique ID of the workflow to delete (required).
    """
    return await get_client().delete_workflow_by_id(id, get_user_token())


# =============================================================================
# Mail Account Tools
# =============================================================================

@mcp.tool()
async def get_all_mail_accounts(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """List all mail accounts.

    Args:
        include_all_fields: When False (default), returns only commonly used fields. Set to True to include all fields.
    """
    data = await get_client().get_all_mail_accounts(
        get_user_token(),
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False
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
        id: The unique ID of the mail account.
        include_all_fields: When False (default), returns only commonly used fields. Set to True to retrieve all available fields.
    """
    return await get_client().get_mail_account_by_id(id, get_user_token(), include_all_fields=include_all_fields)


@mcp.tool()
async def create_mail_account(
    name: str,
    username: str,
    password: str,
    imap_server: str = "imap.gmail.com",
    imap_port: int = 993,
    imap_security: int = 2,
    character_set: str = "UTF-8",
    folder: str = "INBOX",
    is_active: bool = True,
    ctx: Context = None
) -> dict[str, Any]:
    """Create a new mail account.

    Args:
        name: Name of the new mail account (required).
        username: Username for the mail account (required).
        password: Password for the mail account (required).
        imap_server: IMAP server hostname. Defaults to "imap.gmail.com".
        imap_port: IMAP server port. Defaults to 993.
        imap_security: IMAP security type (1=None, 2=SSL/TLS, 3=STARTTLS). Defaults to 2.
        character_set: Character set. Defaults to "UTF-8".
        folder: Mail folder to monitor. Defaults to "INBOX".
        is_active: Whether the account is active. Defaults to True.
    """
    params = CreateMailAccountParam(
        name=name, username=username, password=password,
        imap_server=imap_server, imap_port=imap_port,
        imap_security=imap_security, character_set=character_set,
        folder=folder, is_active=is_active,
    )
    return await get_client().create_mail_account(
        params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token()
    )


@mcp.tool()
async def update_mail_account(
    id: int,
    name: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    imap_server: Optional[str] = None,
    imap_port: Optional[int] = None,
    imap_security: Optional[int] = None,
    character_set: Optional[str] = None,
    folder: Optional[str] = None,
    is_active: Optional[bool] = None,
    ctx: Context = None
) -> dict[str, Any]:
    """Update an existing mail account.

    Args:
        id: The unique ID of the mail account to update (required).
        name: New name for the mail account.
        username: New username.
        password: New password.
        imap_server: New IMAP server hostname.
        imap_port: New IMAP server port.
        imap_security: New IMAP security type.
        character_set: New character set.
        folder: New mail folder.
        is_active: Whether the account is active.
    """
    params = UpdateMailAccountParam(
        id=id, name=name, username=username, password=password,
        imap_server=imap_server, imap_port=imap_port,
        imap_security=imap_security, character_set=character_set,
        folder=folder, is_active=is_active,
    )
    return await get_client().update_mail_account(
        id, params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token()
    )


@mcp.tool()
async def delete_mail_account_by_id(
    id: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a mail account by ID.

    Args:
        id: The unique ID of the mail account to delete (required).
    """
    return await get_client().delete_mail_account_by_id(id, get_user_token())


# =============================================================================
# Mail Rule Tools
# =============================================================================

@mcp.tool()
async def get_all_mail_rules(
    include_all_fields: bool = False,
    ctx: Context = None
) -> dict[str, Any]:
    """List all mail rules.

    Args:
        include_all_fields: When False (default), returns only commonly used fields. Set to True to include all fields.
    """
    data = await get_client().get_all_mail_rules(
        get_user_token(),
        include_all_fields=include_all_fields if ALLOW_ALL_AGGREGATE else False
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
        id: The unique ID of the mail rule.
        include_all_fields: When False (default), returns only commonly used fields. Set to True to retrieve all available fields.
    """
    return await get_client().get_mail_rule_by_id(id, get_user_token(), include_all_fields=include_all_fields)


@mcp.tool()
async def create_mail_rule(
    name: str,
    account: int,
    action: int,
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
        name: Name of the new mail rule (required).
        account: ID of the mail account (required).
        action: Action type (1=delete, 2=mark_read, 3=flag, 4=move, 5=copy) (required).
        folder: Folder to apply rule to (required).
        filter_to: Filter by To address. Defaults to "*".
        filter_from: Filter by From address. Defaults to "*".
        filter_subject: Filter by subject. Defaults to "*".
        filter_attachment_filename: Filter by attachment filename. Defaults to "*".
        maximum_age: Maximum age of messages in days. Defaults to 30.
        order: Rule order. Defaults to 0.
        assign_title: Title template to assign.
        assign_tags: Comma-separated list of tag IDs to assign.
        assign_correspondent: ID of correspondent to assign.
        assign_document_type: ID of document type to assign.
        assign_storage_path: ID of storage path to assign.
        assign_owner: ID of owner user to assign.
    """
    tag_list = [int(t.strip()) for t in assign_tags.split(",")] if assign_tags else None
    params = CreateMailRuleParam(
        name=name, account=account, action=action, folder=folder,
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
        params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token()
    )


@mcp.tool()
async def update_mail_rule(
    id: int,
    name: Optional[str] = None,
    account: Optional[int] = None,
    action: Optional[int] = None,
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
        id: The unique ID of the mail rule to update (required).
        name: New name.
        account: New mail account ID.
        action: New action type.
        folder: New folder.
        filter_to: Filter by To address.
        filter_from: Filter by From address.
        filter_subject: Filter by subject.
        filter_attachment_filename: Filter by attachment filename.
        maximum_age: Maximum age of messages in days.
        order: New rule order.
        assign_title: Title template to assign.
        assign_tags: Comma-separated list of tag IDs to assign.
        assign_correspondent: ID of correspondent to assign.
        assign_document_type: ID of document type to assign.
        assign_storage_path: ID of storage path to assign.
        assign_owner: ID of owner user to assign.
    """
    tag_list = [int(t.strip()) for t in assign_tags.split(",")] if assign_tags else None
    params = UpdateMailRuleParam(
        id=id, name=name, account=account, action=action, folder=folder,
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
        id, params.model_dump(exclude_unset=True, exclude={"id"}, exclude_none=True), get_user_token()
    )


@mcp.tool()
async def delete_mail_rule_by_id(
    id: int,
    ctx: Context = None
) -> dict[str, Any]:
    """Delete a mail rule by ID.

    Args:
        id: The unique ID of the mail rule to delete (required).
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
        query: Search keyword or phrase (required).
        limit: Maximum number of results. Defaults to 50.
        db_only: When True, search database only (no full-text index). Defaults to False.
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
        term: The search term prefix (required).
        limit: Maximum number of suggestions. Defaults to 10.
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
