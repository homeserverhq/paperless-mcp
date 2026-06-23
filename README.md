# Paperless MCP Multitenant Proxy Server

This repository contains a Model Context Protocol (MCP) server that acts
as a secure, multi-tenant proxy between an AI Assistant and the
Paperless backend API. It exposes **76 MCP tools** covering
13 resource domains with full CRUD, search, URL generation, bulk editing, and system operations.

## ✨ Features

- **🔑 Identity Passthrough** — Extracts the `Authorization: Token <token>`
  header from incoming HTTP requests and forwards it to the Paperless
  API without server-side authentication.
- **👥 Multi-Tenancy** — Uses Python `contextvars` to maintain thread-safe
  user identity isolation, ensuring all AI-driven actions are scoped to
  the authenticated user's permissions.
- **📊 Full Paperless Coverage** — 76 tools mapped to Paperless
  API endpoints across 13 resource domains.
- **⚡ TOON Optimization** — Bulk list responses are automatically compressed
  using TOON (Token-Optimized Object Notation) to reduce token consumption
  and maximize context window efficiency.
- **🚀 Efficient Gets** — GET responses return only commonly used fields by
  default. Full objects are available via an `include_all_fields` flag.
- **🧪 Comprehensive Testing** — 82+ automated tests covering all tool domains,
  run via the test runner pipeline.

## 🔧 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `PAPERLESS_BASE_URL` | Yes | Docker-internal URL of the Paperless API (e.g. `http://paperless-app:8000`) |
| `MCP_SERVER_PORT` | Yes | Port number the MCP server listens on |
| `ALLOW_ALL_AGGREGATE` | No | When `true`, aggregate listing tools honor the `include_all_fields` parameter. When `false` (default), the parameter is silently forced to `False` for aggregate list operations. |
| `PAPERLESS_PUBLIC_URL` | No | External-facing URL of your Paperless instance (e.g. `https://paperless.example.com`). When set, `get_document_download_url`, `get_document_preview_url`, and `get_document_thumbnail_url` return this base instead of the internal `PAPERLESS_BASE_URL`. Falls back to `PAPERLESS_BASE_URL` if unset. |

## 📦 Installation & Local Development

1. Ensure you have Python 3.12+ installed.
2. Install dependencies:
   ```bash
   pip install fastmcp httpx pydantic uvicorn toon-mcp-server
   ```
3. Run the server:
   ```bash
   export PAPERLESS_BASE_URL=http://paperless-app:8000
   export MCP_SERVER_PORT=6038
   python -m src.main
   ```

## 🐳 Docker Deployment

Build and run the server using Docker:

```bash
docker build -t paperless-mcp:latest .
docker run -d --name paperless-mcp \
    -e PAPERLESS_BASE_URL="http://paperless-app:8000" \
    -e MCP_SERVER_PORT=6038 \
    paperless-mcp:latest
```

The MCP server serves at `http://paperless-mcp:6038/mcp` (Streamable HTTP).

## ⚠️ Important Notes

- **📋 `include_all_fields`** — The `include_all_fields` parameter (available on all `get_*` and `list_*` tools) controls whether all available fields are included in responses. Defaults to `False` for performance; set to `True` only when additional fields are needed.
- **🔒 `ALLOW_ALL_AGGREGATE`** — Controls whether aggregate listing tools respect the `include_all_fields` parameter. When set to `false` (default), all aggregate list operations silently return only default fields regardless of the caller's request.
- **⚡ TOON Compression** — All bulk list responses are automatically compressed using TOON (Token-Optimized Object Notation) to reduce token consumption by 30-60%.
- **📝 Required Fields & Defaults** — Each `create_*` tool requires specific key fields (e.g. `name` for resources). All other fields default to empty strings or reasonable values.

## 🛠️ API Tool Mapping

The server implements 76 MCP tools organized into the following categories:

### 📄 Documents (17 tools)
- `get_all_documents` — List all documents
- `get_document_by_id` — Get a single document by ID
- `update_document` — Update a document's metadata
- `delete_document_by_id` — Delete a document by ID
- `get_document_metadata` — Get document file metadata
- `get_document_suggestions` — Get ML suggestions for a document
- `get_document_ai_suggestions` — Get AI suggestions for a document
- `get_next_asn` — Get next available archive serial number
- `get_document_notes` — List notes on a document
- `create_document_note` — Add a note to a document
- `delete_document_note` — Delete a note from a document
- `get_document_download_url` — Get download URL for a document
- `get_document_preview_url` — Get preview URL for a document
- `get_document_thumbnail_url` — Get thumbnail URL for a document
- `bulk_update_documents` — Update multiple documents at once
- `reprocess_documents` — Re-run OCR/processing on documents
- `assign_custom_field` — Assign or remove a custom field value on documents

### 👤 Correspondents (5 tools)
- `get_all_correspondents` — List all correspondents
- `get_correspondent_by_id` — Get a single correspondent
- `create_correspondent` — Create a new correspondent
- `update_correspondent` — Update a correspondent
- `delete_correspondent_by_id` — Delete a correspondent

### 📋 Document Types (5 tools)
- `get_all_document_types` — List all document types
- `get_document_type_by_id` — Get a single document type
- `create_document_type` — Create a new document type
- `update_document_type` — Update a document type
- `delete_document_type_by_id` — Delete a document type

### 🔖 Tags (5 tools)
- `get_all_tags` — List all tags
- `get_tag_by_id` — Get a single tag
- `create_tag` — Create a new tag
- `update_tag` — Update a tag
- `delete_tag_by_id` — Delete a tag

### 📂 Storage Paths (5 tools)
- `get_all_storage_paths` — List all storage paths
- `get_storage_path_by_id` — Get a single storage path
- `create_storage_path` — Create a new storage path
- `update_storage_path` — Update a storage path
- `delete_storage_path_by_id` — Delete a storage path

### 👁️ Saved Views (5 tools)
- `get_all_saved_views` — List all saved views
- `get_saved_view_by_id` — Get a single saved view
- `create_saved_view` — Create a new saved view
- `update_saved_view` — Update a saved view
- `delete_saved_view_by_id` — Delete a saved view

### ✏️ Custom Fields (5 tools)
- `get_all_custom_fields` — List all custom fields
- `get_custom_field_by_id` — Get a single custom field
- `create_custom_field` — Create a new custom field
- `update_custom_field` — Update a custom field
- `delete_custom_field_by_id` — Delete a custom field

### ⚙️ Tasks (6 tools)
- `get_all_tasks` — List all tasks
- `get_task_by_id` — Get a single task
- `get_task_summary` — Get aggregated task statistics
- `get_task_status_counts` — Get counts of tasks by status
- `get_active_tasks` — Get currently running tasks
- `acknowledge_tasks` — Acknowledge one or more tasks

### 🔗 Share Links (4 tools)
- `get_all_share_links` — List all share links
- `get_share_link_by_id` — Get a single share link
- `create_share_link` — Create a new share link
- `delete_share_link_by_id` — Delete a share link

### 🔄 Workflows (5 tools)
- `get_all_workflows` — List all workflows
- `get_workflow_by_id` — Get a single workflow
- `create_workflow` — Create a new workflow
- `update_workflow` — Update a workflow
- `delete_workflow_by_id` — Delete a workflow

### 📧 Mail Accounts (5 tools)
- `get_all_mail_accounts` — List all mail accounts
- `get_mail_account_by_id` — Get a single mail account
- `create_mail_account` — Create a new mail account
- `update_mail_account` — Update a mail account
- `delete_mail_account_by_id` — Delete a mail account

### 📨 Mail Rules (5 tools)
- `get_all_mail_rules` — List all mail rules
- `get_mail_rule_by_id` — Get a single mail rule
- `create_mail_rule` — Create a new mail rule
- `update_mail_rule` — Update a mail rule
- `delete_mail_rule_by_id` — Delete a mail rule

### 🛠️ Domain-Specific Tools (4 tools)
- `search_documents` — Global search across documents
- `search_autocomplete` — Get search autocomplete suggestions
- `get_statistics` — Get document/statistics counts
- `check_server_status` — Check system status
