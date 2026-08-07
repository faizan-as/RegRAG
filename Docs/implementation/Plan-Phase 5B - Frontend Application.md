# Plan: Phase 5B - Frontend Application

## Goal

Build the MVP research interface in `apps/web` with Next.js 15, TypeScript, and
shadcn/ui. The application must make FDA research fast to scan and easy to
verify: users can search guidance, ask citation-grounded questions, inspect the
exact source passage behind every citation, generate grounded summaries, export
durable results, and review guidance-update alerts.

This is an authenticated operational application, not a marketing site. The
first screen after sign-in is the research workspace. The frontend consumes the
existing Phase 5 FastAPI contracts and must preserve their citation-first,
fail-closed, ownership, refusal, and audit semantics.

## Scope

### In Scope

- Next.js 15 App Router application under `apps/web`.
- TypeScript strict mode, Tailwind CSS, and shadcn/ui components.
- Supabase browser and server-side authentication using `@supabase/ssr`.
- Researcher and admin navigation derived from authenticated user metadata.
- Typed FastAPI client generated from the backend OpenAPI schema.
- Hybrid search with FDA metadata filters and retrieval diagnostics.
- Chat sessions with authenticated node-boundary SSE streaming.
- Citation rendering and Evidence Card inspection.
- FDA document viewer with section navigation, page targeting, and highlighted
  cited passages.
- Grounded summaries, key requirements, and key-change comparisons.
- Server-owned transcript and summary exports in text, DOCX, and PDF formats.
- Update-alert list and document navigation.
- Admin-only alert lifecycle actions and redacted audit inspection.
- Responsive desktop and mobile layouts.
- Unit, component, accessibility, and browser workflow tests.

### Out of Scope

- Public landing pages, pricing pages, or marketing content.
- Token-by-token answer streaming. The backend emits progress at LangGraph node
  boundaries and one authoritative committed or refused event.
- Browser-side answer generation, citation synthesis, or confidence scoring.
- Client-authored transcript, summary, Evidence Card, or export payloads.
- Graphiti/Neo4j views, entity timelines, or graph exploration.
- EMA, PMDA, warning-letter, Form 483, or non-guidance workflows.
- Final compliance decisions or legal advice.
- Offline mode, native mobile applications, or collaborative editing.
- Production cloud deployment automation.

## Product and UX Principles

- **Evidence first:** Every non-refusal answer visibly exposes its Evidence
  Cards. Citation markers are interactive controls, not decorative footnotes.
- **Exact-source navigation:** Selecting a citation opens the matching document,
  section, page, version, and passage without requiring another search.
- **Authoritative final state:** Node events show workflow progress only. The UI
  displays answer text only after `committed` or `refused` is received.
- **Refusal is a valid result:** Refusals use a clear, neutral state with the
  reason and suggested query refinement. They are not rendered as transport
  failures.
- **Regulatory status is prominent:** Draft, Final, and Withdrawn state remains
  visible in results, Evidence Cards, document headers, summaries, and alerts.
- **Auditability without noise:** Confidence, source version, retrieval time,
  and execution details are available on demand, while the primary reading
  surface remains concise.
- **Dense and work-focused:** Favor tables, split panes, filters, and compact
  metadata over oversized headings, decorative cards, or marketing composition.
- **API authority:** Authentication, authorization, ownership, citation validity,
  and alert transitions remain backend decisions. UI role checks only control
  presentation.

## Current Baseline

- `apps/web` does not exist yet.
- The Phase 5 FastAPI application is implemented and exposes chat, session,
  search, document, summary, export, alert, audit, health, and readiness routes.
- Supabase JWT validation and researcher/admin role enforcement are implemented
  by the API.
- Chat streaming is `POST /api/chat/stream` over SSE. Browser code must use
  `fetch` plus `ReadableStream` because native `EventSource` cannot attach the
  bearer token.
- Chat node events contain safe progress metadata only. Answer text is available
  only in `committed` or `refused`.
- Search returns Evidence Cards and structured transparency metadata without
  generating an answer.
- Documents expose metadata, versions, sections, passages, and protected source
  artifact downloads.
- Summaries and exports are durable, server-owned records.
- Alerts are researcher-readable. Alert mutations and audit inspection are
  admin-only.

## API Contract Gates

Close these backend gaps before the dependent frontend workflows are
accepted as complete:

1. Add `GET /api/sessions` with owner filtering, newest-first ordering, bounded
   pagination, and a typed response. The current API can create a session and
   load one session's turns but cannot restore a user's session list.
2. Add a stable `chunk_id` citation target to `EvidenceCard`. Chat citations
   currently carry document, section, page, and passage metadata but cannot call
   `GET /api/documents/{document_id}/passages/{chunk_id}` without the chunk id.
3. Replace public `raw_object_key` fields with an authorized artifact descriptor
  containing `artifact_id`, content type, version hash, and creation time. The
  document response and OpenAPI schema must not expose object-store keys, and
  the download endpoint continues to require the authorized `artifact_id`.
4. Add owner-checked `GET /api/summaries/{summary_id}` so durable summary pages
  can be reloaded and shared between authorized sessions. Preserve cross-user
  `404` semantics.
5. Make OpenAPI authoritative for frontend generation: add a typed public search
  filter model, explicit structured error responses, and a checked SSE protocol
  schema or companion protocol artifact for `ChatStreamEvent`.
6. Expose `Content-Disposition`, `X-Request-ID`, and `Retry-After` through CORS,
  and emit a valid `Retry-After` value for `429` responses.
7. Add bounded offset or cursor pagination to `GET /api/alerts` so the alerts
  workspace can traverse more than the newest 200 records.
8. Regenerate and review the OpenAPI document after these changes. Retain
  bearer-authenticated ownership checks and sanitized public errors.

Do not block initial shell or component work on these gates. Block session
restoration, exact citation deep-link acceptance, embedded source-document
acceptance, durable summary reload, generated API-client acceptance, and full
alert-history acceptance until their contracts exist.

## Resolved Technical Decisions

- Use Next.js 15 App Router with React Server Components for the protected shell
  and Client Components only for interactive search, chat, viewers, and forms.
- Use TypeScript strict mode. Do not duplicate backend response interfaces by
  hand.
- Generate API types with `openapi-typescript` from FastAPI's OpenAPI document
  and wrap them in a small authenticated client under `apps/web/src/lib/api`.
  Keep the checked SSE protocol artifact beside generated types until OpenAPI
  can describe the stream content directly.
- Use TanStack Query for authenticated server state, caching, invalidation,
  retries, and export-status polling. Keep query/filter state in the URL and
  transient UI state in components.
- Use `@supabase/supabase-js` plus `@supabase/ssr`. Never expose a Supabase
  service-role key to the browser and never manually persist bearer tokens.
- Call FastAPI directly from the browser with the current Supabase access token.
  Configure `NEXT_PUBLIC_API_BASE_URL` and the backend CORS allowlist for the web
  origin.
- Use an explicit SSE parser that supports split chunks, CRLF framing,
  multi-line `data` fields, named events, cancellation, and malformed-event
  rejection.
- Use `react-markdown` with raw HTML disabled and a citation-token transform.
  Never render answer HTML with `dangerouslySetInnerHTML`.
- Use `react-pdf`/PDF.js for preserved PDFs. Render the actual source page and
  text layer; use passage text and page metadata to highlight the cited range.
  Provide a passage panel and FDA source link when exact PDF text matching is
  unavailable.
- Use Lucide icons through shadcn/ui controls. Keep card radii at 8px or less and
  avoid nested cards.
- Use Vitest, React Testing Library, MSW, and Playwright. Add axe checks to the
  critical Playwright workflows.

## Information Architecture

### Public Routes

- `/login` - Supabase sign-in and password-reset entry.
- `/auth/callback` - Supabase code exchange and safe redirect handling.

### Researcher Routes

- `/research` - Search-first workspace and default authenticated route.
- `/search` - Shareable search results with filters encoded in the URL.
- `/chat` - Create or resume a research session.
- `/chat/[sessionId]` - Durable conversation history and streaming composer.
- `/documents/[documentId]` - Metadata, source viewer, sections, versions, and
  summary actions. Citation focus is represented by query parameters such as
  `chunk`, `page`, and `version`.
- `/summaries/[summaryId]` - Durable summary result, evidence, and export actions.
- `/alerts` - New, updated, and withdrawn guidance alerts.

### Admin Routes

- `/admin/audit` - Filtered, paginated, redacted audit events.
- Alert mutation controls remain within `/alerts` and appear only for admins.

Unknown authenticated routes redirect to `/research`. Unauthenticated access to
protected routes redirects to `/login` with a validated relative return path.

## Visual and Interaction Direction

- Use a restrained regulatory-research palette: white and cool neutral surfaces,
  near-black text, blue interactive accents, green for verified/final states,
  amber for draft or caution states, and red only for withdrawn, refused, or
  destructive states.
- Use Source Sans 3 for application UI and Source Serif 4 for long source
  passages and document reading. Load fonts through `next/font`.
- Desktop uses a persistent left navigation rail and a compact top utility bar.
  Chat and document views use resizable split panes rather than stacked cards.
- Mobile uses a navigation sheet, a full-width primary workspace, and bottom
  sheets for Evidence Cards and filters.
- Keep stable dimensions for toolbars, icon buttons, status badges, result rows,
  and viewer controls so loading and hover states do not shift the layout.
- Use skeletons that mirror final layouts. Avoid full-page spinners after the
  protected shell has loaded.
- Motion is limited to route/content reveal, streaming progress transitions, and
  evidence-panel focus. Respect `prefers-reduced-motion`.

## Proposed File Structure

```text
apps/web/
  app/
    (auth)/login/page.tsx
    auth/callback/route.ts
    (app)/layout.tsx
    (app)/research/page.tsx
    (app)/search/page.tsx
    (app)/chat/page.tsx
    (app)/chat/[sessionId]/page.tsx
    (app)/documents/[documentId]/page.tsx
    (app)/summaries/[summaryId]/page.tsx
    (app)/alerts/page.tsx
    (app)/admin/audit/page.tsx
    error.tsx
    not-found.tsx
    globals.css
    layout.tsx
  src/
    components/
      app-shell/
      auth/
      chat/
      citations/
      documents/
      search/
      summaries/
      alerts/
      audit/
      ui/
    hooks/
    lib/
      api/
        client.ts
        errors.ts
        schema.d.ts
        sse.ts
      auth/
      env.ts
      query-client.ts
      routes.ts
    providers/
  tests/
    components/
    integration/
    e2e/
  components.json
  next.config.ts
  package.json
  playwright.config.ts
  postcss.config.mjs
  tsconfig.json
  vitest.config.ts
```

## Implementation Steps

### Phase 5B.0 - Contract and Tooling Foundation

- Close or explicitly track all API contract gates.
- Scaffold `apps/web` as a Next.js 15 App Router application with TypeScript,
  Tailwind CSS, ESLint, and the repository's package-manager convention.
- Initialize shadcn/ui and install only the primitives needed by the first
  milestone: button, input, textarea, form, label, select, command, popover,
  sheet, dialog, tooltip, tabs, separator, badge, table, scroll-area, skeleton,
  alert, toast/sonner, dropdown-menu, and resizable panels.
- Add Lucide icons, TanStack Query, Supabase SSR, OpenAPI type generation,
  `react-markdown`, `remark-gfm`, and Zod environment validation.
- Add `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_SUPABASE_URL`, and
  `NEXT_PUBLIC_SUPABASE_ANON_KEY` to `.env.example`. Do not add service secrets.
- Add scripts for `dev`, `build`, `lint`, `typecheck`, `test`, `test:e2e`, and
  `api:types`.
- Generate API types from a checked OpenAPI artifact or a running local API.
  Add a CI check that fails when regeneration creates a diff.
- Add root metadata, favicon/application mark, fonts, CSS variables, and a
  responsive base layout. Do not build a landing page.

### Phase 5B.1 - Authentication and Application Shell

- Implement Supabase browser and server clients with cookie refresh middleware.
- Add login, logout, expired-session, callback-error, and password-reset states.
- Validate callback return paths to prevent open redirects.
- Protect the `(app)` route group on the server.
- Build a compact application shell with navigation for Research, Chat, Alerts,
  and role-gated Audit.
- Display the signed-in email and application role in the account menu.
- Treat role metadata as a display hint only. Handle API `403` responses as the
  final authority and remove stale privileged controls after a rejection.
- Add a top-level API availability indicator based on `/health` and `/ready`
  without polling aggressively or exposing dependency details to end users.

### Phase 5B.2 - Typed API and Error Handling

- Implement one API request wrapper that adds the current bearer token, request
  headers, abort signals, and structured response parsing.
- Normalize FastAPI errors into typed UI categories: unauthenticated,
  unauthorized, validation, not found, rate limited, unavailable, and unknown.
- On `401`, refresh the Supabase session once and retry once. Never loop token
  refreshes.
- Respect `Retry-After` for `429` when present. Preserve user input after
  recoverable failures.
- Use TanStack Query keys scoped by authenticated user and resource id. Clear the
  query cache on sign-out or user change.
- Implement authenticated blob downloads with safe filenames derived from
  `Content-Disposition`; do not navigate directly to protected download URLs.
- Add an SSE request helper separate from ordinary JSON requests.

### Phase 5B.3 - Search Workspace

- Build a search input with explicit submit, recent-query convenience, and URL
  synchronization.
- Add compact filters for center, topic, date range, document status, docket,
  CFR reference, and product code. Use segmented controls or selects for bounded
  values and text inputs/comboboxes for open vocabularies.
- Submit typed known filters to `POST /api/search` and show ignored filter keys
  as a non-blocking notice.
- Render results as dense rows with title, exact passage excerpt, section/page,
  Draft/Final/Withdrawn status, source, rank, and rerank score disclosure.
- Pair each result with its Evidence Card. Selecting a row opens the document at
  the matching citation target.
- Distinguish empty success, partial retrieval fallback, total service
  unavailability, validation failure, and cancellation.
- Put retrieval diagnostics in a collapsed "How this was found" panel. Expose
  safe backend codes and timings, not raw implementation details.
- Keep query and filters shareable through the URL without placing tokens or
  private answer content in it.

### Phase 5B.4 - Durable Chat and SSE

- Implement session creation and, after the contract gate, paginated session
  restoration.
- Load immutable turns from `GET /api/sessions/{session_id}/turns`.
- Build a composer with a bounded textarea, submit/cancel controls, filter
  access, and visible regulatory-research scope.
- Send `POST /api/chat/stream` with the bearer token and an `AbortController`.
- Parse `started`, `node`, `committed`, `refused`, `error`, and `done` events.
- Map safe node names to concise progress labels. Do not show chain-of-thought,
  prompt content, raw provider output, or answer text from node events.
- Add the assistant turn only after `committed` or `refused`. Use the durable
  `turn_id` from the final event and invalidate the session-history query.
- Render inline citation markers as keyboard-accessible buttons bound to the
  returned Evidence Cards.
- Open citations in a desktop evidence side panel or mobile bottom sheet. From
  there, navigate to the exact document target.
- Show refusal reason, confidence context, and query-refinement actions without
  presenting refusal as a system crash.
- On cancellation, stop reading, preserve the query locally, and do not create a
  synthetic completed answer.
- Provide transcript export from the server-owned `session_id` only.

### Phase 5B.5 - Evidence Cards and Document Viewer

- Build a reusable Evidence Card with title, citation id, section/page, exact
  passage, FDA status, version hash, source URL, confidence, retrieval/rerank
  disclosure, and retrieval timestamp.
- Visually distinguish source status and stale/withdrawn evidence without
  hiding it.
- Load document metadata and section navigation in parallel.
- Use a three-region desktop layout: section navigation, source viewer, and
  passage/evidence inspector. Collapse side regions into sheets on mobile.
- Resolve `chunk_id` through the passage endpoint and verify that document id,
  version hash, page, and exact passage agree with the selected Evidence Card.
- Fetch protected PDF/HTML artifacts as authenticated blobs using the exposed
  artifact id. Revoke object URLs when the viewer unmounts.
- For PDFs, navigate to `page_number` and highlight normalized passage text in
  the text layer. If exact matching fails, mark the page and show the exact
  passage alongside it rather than claiming a false highlight.
- For HTML artifacts, render sanitized source content in an isolated viewer; do
  not inject untrusted HTML into the application document.
- Provide explicit actions for FDA source, preserved source download, copy
  citation, summary, and version comparison.
- Preserve document, version, page, section, and chunk focus in the URL so
  citation links are shareable between authorized users.

### Phase 5B.6 - Summaries and Exports

- Add actions for Summary, Key requirements, and Key changes.
- For key changes, require a prior version selected from the document's known
  versions before submitting `compare_version_hash`.
- Show an in-request generation state, then refusal or the terminal result with
  current/previous version hashes, faithfulness state, and Evidence Cards. Do
  not imply incremental summary progress while the API remains synchronous.
- Render summary citation markers with the same component and navigation
  behavior as chat citations.
- Keep `summary_id` as the only source for summary exports and `session_id` as
  the only source for transcript exports.
- Add format selection for text, DOCX, and PDF.
- Handle the terminal completed and failed export responses returned by the
  current synchronous API. Keep the `pending` renderer for forward-compatible
  records, but do not poll unless export creation later becomes asynchronous.
- Download completed exports through the authenticated blob helper.

### Phase 5B.7 - Alerts and Admin Audit

- Build a paginated alert table/list with status, type, guidance title, prior/current
  status, detection time, and version-change indicators.
- Filter alerts by lifecycle status and encode the selected filter in the URL.
- Link each alert to its document and offer a key-change summary when both
  versions are available.
- Show acknowledge and resolve controls only to admins. Disable impossible
  backward transitions before submission, while still handling backend `422` or
  `403` as authoritative.
- Build an admin audit table with event type, user/session, route, request id,
  timestamp, and a structured redacted-payload dialog.
- Add audit filters for event type, user, session, route, and date range.
- Use offset pagination exactly as exposed by the API. Do not infer or display a
  total count until the backend provides one.

### Phase 5B.8 - Accessibility, Resilience, and Performance

- Meet WCAG 2.2 AA for contrast, focus visibility, keyboard navigation, labels,
  dialogs/sheets, status announcements, and non-color status cues.
- Announce streaming stage changes through a polite live region, but announce
  only meaningful transitions to avoid screen-reader noise.
- Keep citation markers, Evidence Cards, viewer controls, and table actions fully
  keyboard accessible.
- Add route-level error boundaries and retry actions for each primary workspace.
- Add skeletons and stable panel dimensions to prevent layout shift.
- Virtualize only lists proven large enough to need it. Prefer pagination and
  bounded API responses first.
- Dynamically import PDF.js and other viewer-heavy code.
- Avoid logging query text, answer text, passages, bearer tokens, or Supabase
  session data to browser analytics.
- Capture sanitized client failures, Web Vitals, request ids, and route names for
  operational debugging.

### Phase 5B.9 - Testing and Quality Gates

- Unit-test API error normalization, citation-token parsing, SSE framing,
  authenticated downloads, filter serialization, and route builders.
- Component-test search states, committed answer, refusal, Evidence Cards,
  document metadata, summary results, export states, alerts, and audit filters.
- Use MSW to model success, empty results, partial retrieval, `401`, `403`,
  `422`, `429`, `503`, malformed SSE, cancellation, and final-event ordering.
- Add Playwright workflows for:
  - Sign in and protected-route redirect.
  - Search, filter, and open cited passage.
  - Stream chat progress and receive exactly one committed answer.
  - Receive and understand a refusal.
  - Resume a durable session.
  - Generate and export a summary.
  - Review an alert and open the affected document.
  - Admin alert transition and audit filtering.
- Verify desktop and mobile screenshots for clipping, overlap, blank PDF canvas,
  evidence-panel navigation, and responsive controls.
- Run axe against login, search, chat, document, summary, alerts, and audit pages.
- Require `lint`, `typecheck`, unit/component tests, production build, and critical
  Playwright flows in CI.

## API-to-UI Contract Matrix

| API | Frontend owner | Required UI behavior |
|---|---|---|
| `GET /health`, `GET /ready` | App shell | Lightweight availability state and retry |
| `GET/POST /api/sessions` | Chat sidebar | Restore/create user-owned sessions |
| `GET /api/sessions/{id}/turns` | Chat history | Render immutable committed/refused turns |
| `POST /api/chat/stream` | Chat composer | Progress-only nodes and one final answer/refusal |
| `POST /api/search` | Search workspace | Results, evidence, filters, and safe diagnostics |
| `GET /api/documents/{id}` | Document header/viewer | Metadata, versions, status, and source artifacts |
| `GET /api/documents/{id}/sections` | Section navigation | Ordered section and page targets |
| `GET /api/documents/{id}/passages/{chunk}` | Evidence inspector | Exact cited passage verification |
| `GET /api/documents/{id}/artifacts/{artifact}/download` | Source viewer | Authenticated PDF/HTML blob |
| `POST /api/summaries` | Summary workspace | Grounded result/refusal and evidence |
| `GET /api/summaries/{id}` | Summary workspace | Reload an authorized durable summary |
| `POST/GET /api/exports` | Export controls | Server-owned generation and status |
| `GET /api/exports/{id}/download` | Export controls | Authenticated artifact download |
| `GET/PATCH /api/alerts` | Alerts workspace | Researcher list and admin transitions |
| `GET /api/audit` | Admin audit | Filtered redacted event inspection |

## Security and Privacy Requirements

- Never place access tokens in URLs, logs, analytics, localStorage managed by
  application code, or error messages.
- Never use the Supabase service-role key in `NEXT_PUBLIC_*` variables.
- Escape or structurally render all API text. Raw HTML is disabled for generated
  answers and summaries.
- Sanitize preserved HTML before isolated rendering.
- Construct API paths with encoded identifiers and validated relative routes.
- Abort in-flight requests on sign-out and clear user-scoped caches.
- Do not infer authorization from hidden controls. Handle `401`, `403`, and `404`
  without revealing whether another user's resource exists.
- Do not expose `raw_object_key`, provider errors, database details, prompt text,
  or hidden workflow reasoning.
- Preserve the product boundary: regulatory research support, not legal advice or
  final compliance determination.

## Milestones

### Milestone 1 - Foundation and Search

- Contract gates are closed and OpenAPI/SSE type generation is reproducible.
- Next.js, shadcn/ui, Supabase auth, protected shell, and typed API client work.
- Search, filters, result states, and Evidence Cards are complete.

### Milestone 2 - Chat and Citation Navigation

- Durable session list/history and authenticated SSE work.
- Node progress never leaks uncommitted answer text.
- Inline citations open a verified Evidence Card and exact document target.

### Milestone 3 - Document Intelligence and Exports

- PDF/HTML viewer, section navigation, page targeting, and passage highlighting
  work on desktop and mobile.
- Summary, key requirements, key changes, transcript exports, and summary exports
  are complete.

### Milestone 4 - Monitoring, Admin, and Hardening

- Alerts and admin audit workflows are complete.
- Accessibility, error handling, performance, and security checks pass.
- Critical Playwright workflows pass against a controlled local FDA corpus.

## Definition of Done

- An authenticated researcher can search FDA guidance, inspect ranked evidence,
  ask a question, receive a committed citation-bound answer or clear refusal,
  and navigate every citation to a verifiable source passage.
- The document viewer exposes FDA status, source version, sections, exact passage,
  and preserved source without leaking object-store paths.
- Sessions and final turns survive reload and can be exported from server-owned
  records.
- Summaries and key changes expose citations, version context, faithfulness state,
  durable reload, and authorized exports.
- Researchers can review new, updated, and withdrawn guidance alerts. Admins can
  perform allowed alert transitions and inspect redacted audit events.
- Authentication refresh, cancellation, rate limiting, refusal, partial service,
  unavailable service, validation, and authorization states have deliberate UI.
- Desktop and mobile layouts have no incoherent overlap, clipping, blank viewer,
  or inaccessible controls.
- No generated claim is displayed before the backend commits or refuses it.
- No client-authored content is treated as authoritative evidence or export
  source.
- Frontend lint, strict typecheck, unit/component tests, production build,
  accessibility checks, and critical Playwright workflows pass.
- Setup documentation and `TASK.md` reflect the implemented frontend state.
