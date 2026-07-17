# Local Supermemory: Executive Summary

Updated: 17 July 2026  
Workspace: `/Users/dev/Documents/SuperMemory`

## Executive overview

Supermemory is a persistent context and retrieval layer for AI applications. The local edition packages its HTTP API, encrypted embedded data store, ingestion queue, document chunking, vector search, profiles, and memory-management workflows into a single self-hosted binary. Applications send text, conversations, URLs, or files to the server; Supermemory extracts content, divides it into chunks, embeds those chunks, and makes them available through semantic or hybrid retrieval. An external or locally hosted LLM performs higher-level operations such as summaries, contextual chunking, profile synthesis, and memory extraction.

The local deployment keeps documents, vectors, metadata, authentication state, and model files on the machine. It does not make every operation offline automatically: the default embedding model is local, but intelligent extraction still requires an LLM provider unless an OpenAI-compatible local model server such as Ollama, LM Studio, vLLM, or llama.cpp is configured.

## Current installation

| Item | Current value |
|---|---|
| Server state | Running and listening |
| Local API | `http://localhost:6767` |
| Listen interface | `*:6767` |
| Process | `supermemory-server` (PID 88073 when checked) |
| Binary | `/Users/dev/.supermemory/bin/supermemory-server` |
| Server version | `0.0.5` |
| Workspace data directory | `/Users/dev/Documents/SuperMemory/.supermemory` |
| Current data size | Approximately 369 MB |
| Embedding cache | `/Users/dev/Documents/SuperMemory/.supermemory/models` (approximately 114 MB) |
| Vector model | `Xenova/bge-base-en-v1.5` |
| Vector dimensions | 768 |
| Embedding execution | Local CPU, one worker and one WASM thread by default |
| LLM provider | Groq |
| Provider credential | Encrypted in `.supermemory/env.enc`; never commit it |
| Telemetry setting | Server launched with `SUPERMEMORY_DISABLE_TELEMETRY=1` |
| API specification | `supermemory-api.json`, OpenAPI 3.1, API version 3.0.0 |

The OpenAPI document identifies `http://localhost:6767` as its server and describes 23 paths with 29 HTTP operations.

### Verified behavior

- The server starts successfully and the local embedding model loads.
- Text documents can be queued, chunked, embedded, stored, and marked `done`.
- Hybrid semantic retrieval works against stored document chunks.
- A smoke query returned the intended chunk with similarity `0.657` in `51 ms`.
- Groq authentication itself was checked directly and returned HTTP 200.
- The Groq credential survives restart through the encrypted local credential store.

### Known issue in this installation

The version 0.0.5 self-hosted memory agent currently fails during its Groq-backed structured memory-extraction step and finalizes tested documents with zero generated memory entries. Raw documents, chunks, local embeddings, and hybrid retrieval continue to work. Consequently:

- `/v4/search` in `hybrid` or `documents` mode can retrieve the ingested content.
- `/v4/memories/list` may contain no extracted memories for documents affected by this failure.
- Profiles and memory-only search will be incomplete until the provider integration is fixed, a different supported LLM provider is configured, or the server is upgraded.

This is an important distinction: a document reporting `status: done` confirms that the ingestion workflow finalized, but does not by itself prove that structured memories were created. Server workflow logs must also be checked.

## How the system works

1. A client sends content to the local HTTP API.
2. The request is validated and stored immediately; ingestion normally returns `queued`.
3. Supermemory extracts text from the submitted content.
4. Text is chunked for retrieval.
5. The local BGE model converts chunks into 768-dimensional vectors.
6. Chunks, vectors, metadata, and document relationships are indexed in the embedded store.
7. The configured LLM may generate summaries, structured memories, relationships, and profile information.
8. Search combines vector relevance with document or memory scope and optional metadata filters.
9. The application supplies retrieved context to its chat model before generating an answer.

Search requests are intended to remain responsive while ingestion is processed through a controlled background queue.

## Core data concepts

### Documents

Documents are the original submitted units: text, conversations, URLs, or uploaded files. They carry a generated ID, optional `customId`, metadata, processing state, source information, task type, timestamps, and one or more container associations.

Use a stable `customId` for deduplication and updates. Reusing it lets Supermemory relate changed or appended content to the same source.

### Chunks

Chunks are retrieval-sized portions of documents. They are embedded and can be returned by hybrid or document search even when structured-memory generation fails.

### Memories

Memories are extracted or directly created facts. They are versioned, searchable, soft-forgettable, and can retain source-document relationships. Direct creation through `/v4/memories` bypasses normal document ingestion and immediately embeds the supplied memory.

### Containers

A `containerTag` is the primary isolation and grouping boundary—for example, a user, project, agent, or tenant. Profiles and searches can be scoped to a container. Container settings can include context and profile bucket definitions. Container tags can also be merged or deleted.

### Profiles and buckets

A profile summarizes stable and changing context for a container and can be returned together with relevant search results. Bucket definitions control how profile information is organized. Effective buckets combine organization-level definitions with container-specific additions.

### Metadata and filters

Metadata values can be strings, numbers, booleans, and—where the operation permits—arrays of strings. Filters support equality, numeric comparisons, array containment, string containment, negation, case handling, and nested `AND`/`OR` expressions. The specification permits logical nesting up to five levels in applicable endpoints.

## Ingestion capabilities

The API accepts:

- Plain text, Markdown, HTML, notes, and transcripts.
- Structured conversation messages.
- Web URLs and other supported remote content.
- Files through multipart upload, including documents, PDFs, images, spreadsheets, and video where the local build and selected provider support extraction.
- Batches of up to 600 documents according to the supplied schema.

Important ingestion controls include:

- `containerTag`: user/project/tenant scope.
- `customId`: external identity for updates and deduplication.
- `metadata`: searchable business attributes.
- `entityContext`: up to 1,500 characters guiding what the extractor should understand about the entity.
- `filterByMetadata`: restricts which existing memories are supplied as context while processing the new item.
- `taskType`: `memory` for the context layer or `superrag` for RAG-oriented processing.
- `filepath`: optional filesystem mapping used by Supermemory filesystem workflows.
- `dreaming`: `dynamic` groups related inputs into coherent processing; `instant` processes the document independently and immediately.

Processing is asynchronous. After adding content, poll `GET /v3/documents/{id}` and inspect both document status and workflow logs when structured memories matter.

## Search and retrieval

The supplied API exposes both `/v3/search` and `/v4/search`. New application work should prefer `/v4/search`, which was successfully exercised locally and is described as low-latency conversational memory search.

Search modes are:

- `memories`: structured memory entries only.
- `hybrid`: structured memories plus document chunks; generally the best default.
- `documents`: document chunks only.

Relevant controls include:

- `q`: required natural-language query.
- `containerTag` or container filters: isolation scope.
- `limit`: maximum result count, up to 100 in the supplied schema.
- `threshold`: similarity cutoff.
- `rerank`: optional relevance rescoring with extra latency.
- `rewriteQuery`: optional LLM query rewriting with additional latency.
- `aggregate`: synthesize information from multiple memories when supported.
- `filters`: metadata and logical filters.
- `include`: optionally return related documents, summaries, related memories, forgotten memories, and compatibility chunk fields.
- `filepath`: exact or prefix filtering for filesystem-oriented content.

The `/v3/search` endpoint remains available for compatibility and document-oriented search. Do not treat semantic search as a complete database export; use the list endpoints when every record must be enumerated.

## API coverage from `supermemory-api.json`

### Documents and files

| Method and path | Purpose |
|---|---|
| `POST /v3/documents` | Add one text, URL, or other content item |
| `POST /v3/documents/batch` | Add multiple documents |
| `GET /v3/documents/{id}` | Get one document and workflow status |
| `PATCH /v3/documents/{id}` | Update document content or metadata |
| `DELETE /v3/documents/{id}` | Delete by server ID or `customId` |
| `POST /v3/documents/file` | Multipart file upload |
| `POST /v3/documents/list` | Paginated document listing and filtering |
| `GET /v3/documents/processing` | List documents currently processing |
| `GET /v3/documents/{id}/chunks` | Return ordered chunks for a document |
| `GET /v3/documents/{id}/file-url` | Create a time-limited file download URL |
| `DELETE /v3/documents/bulk` | Bulk delete by IDs or containers |

The specification uses `POST /v3/documents/list` for authoritative listing. A bare `GET /v3/documents` should not be assumed to list content unless a particular server release documents or implements that convenience route.

### Search, direct memories, and conversations

| Method and path | Purpose |
|---|---|
| `POST /v3/search` | Compatibility/advanced document-memory search |
| `POST /v4/search` | Low-latency search across memories and/or chunks |
| `POST /v4/memories` | Create a memory directly, bypassing ingestion |
| `PATCH /v4/memories` | Create a new version of a memory |
| `DELETE /v4/memories` | Soft-forget one memory |
| `POST /v4/memories/list` | List current memories with history and sources |
| `POST /v4/memories/forget-matching` | Agentic mass-forget, with dry-run support |
| `POST /v4/conversations` | Ingest or update a conversation with user, assistant, system, and tool messages |

Conversation content can be text or supported multimodal message parts such as image URLs. A stable `conversationId` is required, and metadata may be attached.

### Profiles and containers

| Method and path | Purpose |
|---|---|
| `POST /v4/profile` | Return a container profile, optionally with search results |
| `POST /v4/profile/buckets` | Return effective profile bucket definitions |
| `GET /v3/container-tags/{containerTag}` | Read container settings |
| `PATCH /v3/container-tags/{containerTag}` | Update container settings |
| `DELETE /v3/container-tags/{containerTag}` | Delete a container and its content |
| `POST /v3/container-tags/merge` | Queue merging source tags into a target |
| `GET /v3/container-tags/merge/{mergeId}` | Check merge status |

Container deletion is destructive. Container merging updates document associations and removes successfully merged source tags.

### Organization settings

| Method and path | Purpose |
|---|---|
| `GET /v3/settings` | Read organization settings |
| `PATCH /v3/settings` | Update organization settings |
| `POST /v3/settings/suggest-buckets` | Generate 3–6 profile-bucket suggestions from an organization context prompt |
| `POST /v3/settings/reset` | Reset organization content and settings while preserving organization identity, members, and billing records where applicable |

Reset, bulk delete, container delete, and forget-matching operations require special care. Run dry-run modes where available and back up the local data directory before destructive administration.

## Authentication and security

At first boot the local server creates a local organization and API key. The current build auto-applies that identity to unauthenticated localhost requests. Remote callers should use:

```http
Authorization: Bearer sm_...
```

Operational security requirements:

- Do not commit `.supermemory`, `env.enc`, Groq keys, or the generated Supermemory bearer token.
- The Groq key shared during setup should be rotated because it appeared in conversation history.
- Although the service is locally addressed as `localhost`, the current process is listening on all interfaces (`*:6767`). Use the host firewall or bind/reverse-proxy configuration before treating it as private on an untrusted network.
- Use TLS and authenticated access if exposing the server outside the machine.
- Keep different users or tenants in distinct container tags and enforce that mapping in the application; container tags are an organizational boundary, not a substitute for application authorization.
- Back up the full data directory consistently while the server is stopped, or use a storage-consistent snapshot.

## Models and embeddings

The current embedding model is `Xenova/bge-base-en-v1.5`, a local English-oriented 768-dimensional model. Its vectors are computed without a cloud embedding API key.

Supported documented embedding choices include:

- Built-in local English embeddings.
- Local multilingual embeddings selected during first boot.
- OpenAI embeddings.
- Google Gemini embeddings.
- OpenAI-compatible embedding endpoints.

Embedding identity and dimensions are locked once data is ingested because vectors from different models are not comparable. To change models, use a fresh `SUPERMEMORY_DATA_DIR` and re-ingest, or deliberately wipe and rebuild after backing up. Never point a different model or dimension at an existing vector store.

Configuration variables include:

- `SUPERMEMORY_EMBEDDING_PROVIDER`
- `SUPERMEMORY_EMBEDDING_MODEL`
- `SUPERMEMORY_EMBEDDING_DIMENSIONS`
- `SUPERMEMORY_EMBEDDING_BASE_URL`
- `SUPERMEMORY_LOCAL_EMBEDDING_POOL_SIZE`
- `SUPERMEMORY_LOCAL_EMBEDDING_WASM_THREADS`
- `SUPERMEMORY_LOCAL_EMBEDDING_BATCH_SIZE`
- `SUPERMEMORY_LOCAL_EMBEDDING_IDLE_TIMEOUT_MS`
- `SUPERMEMORY_SKIP_EMBEDDING_PREWARM`

Cloud embeddings can improve multilingual or domain coverage and move compute off the host, but introduce network latency, provider cost, data transfer, and credential management.

## LLM provider configuration

Self-hosting supports OpenAI, Anthropic, Gemini, Groq, Cloudflare Workers AI, Vertex AI, and OpenAI-compatible local or hosted endpoints, subject to the server version. Provider selection is separate from embedding selection.

Documented environment variables include:

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`
- `OPENAI_FAST_MODEL`
- `OPENAI_TEXT_MODEL`
- `ANTHROPIC_API_KEY`
- `GEMINI_API_KEY`
- `GROQ_API_KEY`
- `WORKERS_AI_API_KEY` with `CLOUDFLARE_ACCOUNT_ID`
- `GOOGLE_VERTEX_PROJECT_ID` with `GOOGLE_VERTEX_LOCATION`

For fully local inference, expose Ollama, LM Studio, vLLM, or llama.cpp through an OpenAI-compatible endpoint and set `OPENAI_BASE_URL`, a non-empty placeholder `OPENAI_API_KEY`, and the exact local model name. The official example recommends a capable model such as `gpt-oss:20b`; practical CPU performance depends heavily on available RAM, quantization, and core count.

When multiple provider credentials are configured, documented precedence determines which provider performs extraction. Avoid adding an embedding provider key without confirming whether it also changes the selected extraction LLM.

## Runtime and performance controls

Core variables:

- `PORT` or `SUPERMEMORY_PORT`: HTTP port, default `6767`.
- `SUPERMEMORY_DATA_DIR`: location of database, authentication state, and model cache; default `./.supermemory` relative to the launch directory.
- `SUPERMEMORY_DISABLE_TELEMETRY=1`: disables internal AI SDK telemetry instrumentation.
- `SUPERMEMORY_EMBEDDING_RAM_LIMIT`: ingestion memory allowance above the post-boot baseline; default approximately 1 GB.
- `SUPERMEMORY_INGEST_CONCURRENCY`: simultaneous ingestion tasks; default 2.

The local embedding runtime uses a significant fixed memory baseline. Increase worker counts and ingestion concurrency only when the machine has enough headroom. On a CPU-only GCP VM, choose an x64 or arm64 Linux binary matching the VM, keep concurrency conservative, place `SUPERMEMORY_DATA_DIR` on persistent disk, and use a service manager such as systemd. Cloud embeddings can reduce local CPU and memory pressure.

## Local versus hosted/enterprise functionality

The local binary covers the core API, embedded storage, ingestion, file handling, local or pluggable embeddings, document and memory search, profiles, container organization, and application-managed integrations.

The official hosted platform adds managed operational scale and provider-specific services. The self-hosted binary does not include hosted background connectors such as Google Drive, Notion, Gmail, or OneDrive; managed Supermemory MCP endpoints; the hosted proprietary optimized extraction pipeline; or globally distributed managed scaling. A local application can still build its own importers and connect an MCP layer to the local HTTP API.

## Common local commands

Start the server from this workspace:

```bash
cd /Users/dev/Documents/SuperMemory
SUPERMEMORY_DISABLE_TELEMETRY=1 /Users/dev/.supermemory/bin/supermemory-server
```

Add content:

```bash
curl -X POST http://localhost:6767/v3/documents \
  -H 'Content-Type: application/json' \
  -d '{
    "content": "I prefer TypeScript and PostgreSQL.",
    "containerTag": "user-demo",
    "customId": "preference-001",
    "dreaming": "instant"
  }'
```

Check a document:

```bash
curl -s http://localhost:6767/v3/documents/DOCUMENT_ID | jq
```

List documents using the specification-defined route:

```bash
curl -s -X POST http://localhost:6767/v3/documents/list \
  -H 'Content-Type: application/json' \
  -d '{"containerTags":["user-demo"],"limit":100}' | jq
```

List actual structured memories:

```bash
curl -s -X POST http://localhost:6767/v4/memories/list \
  -H 'Content-Type: application/json' \
  -d '{"containerTags":["user-demo"]}' | jq
```

Hybrid search:

```bash
curl -s -X POST http://localhost:6767/v4/search \
  -H 'Content-Type: application/json' \
  -d '{
    "q":"What technology does the user prefer?",
    "containerTag":"user-demo",
    "searchMode":"hybrid",
    "threshold":0.2,
    "limit":10
  }' | jq
```

Upload a file:

```bash
curl -X POST http://localhost:6767/v3/documents/file \
  -F 'file=@/absolute/path/to/document.pdf' \
  -F 'containerTag=user-demo'
```

## Recommended MVP architecture

1. Keep Supermemory as a private backend service; do not call it directly from an untrusted browser.
2. Put a small application API in front of it for user authentication, container mapping, validation, quotas, and audit logging.
3. On every user message, query `/v4/search` with `searchMode: hybrid`, a modest threshold, and a small limit.
4. Add retrieved chunks to the chat model's system/context message with source IDs.
5. Generate the answer with the chosen LLM.
6. Ingest the conversation asynchronously through `/v4/conversations` or `/v3/documents` with a stable conversation ID.
7. Poll ingestion status and expose failures separately from chat success.
8. Use direct `/v4/memories` creation for explicit, user-approved facts when automatic extraction is unreliable.
9. Provide user controls to view documents, view memories, correct/update versions, forget memories, and delete containers.

For the present installation, use hybrid/document retrieval and direct memory creation until Groq-backed automatic extraction is repaired.

## Operational recommendations

- Rotate the exposed Groq key, then update the encrypted credential store.
- Upgrade Supermemory when a release newer than 0.0.5 is available and repeat the extraction smoke test.
- If the extraction bug persists, test OpenAI, Anthropic, Gemini, or a supported OpenAI-compatible model.
- Add a repeatable health/smoke script that inserts a unique fact, waits for completion, checks `/v4/memories/list`, and searches for it.
- Use a dedicated persistent data directory in production rather than relying on the process working directory.
- Back up data and encrypted configuration together; test restore procedures.
- Keep port 6767 firewalled and proxy it through authenticated TLS for remote use.
- Track ingestion queue depth, processing failures, latency, memory use, disk size, and provider errors.
- Use stable `customId`, `conversationId`, and container naming conventions from the beginning.
- Prefer `POST /v3/documents/list` and `POST /v4/memories/list` for enumeration; use search only for relevance-based retrieval.
- Preview agentic mass-forget with `dryRun` and require explicit confirmation for reset, container deletion, and bulk deletion.

## Source basis and scope

This summary combines:

- The supplied `/Users/dev/Documents/SuperMemory/supermemory-api.json` (OpenAPI 3.1.0, API version 3.0.0).
- The official Supermemory self-hosting quickstart, configuration, embeddings, ingestion, search, profile, and API documentation available on 17 July 2026.
- Direct inspection and smoke testing of the current local server.

The OpenAPI file is the most precise source for endpoint shape. Official self-hosting documentation is the source for installation, model providers, embeddings, runtime tuning, and local-versus-hosted scope. Direct tests are the source for statements about this machine's current state and the Groq extraction failure.
