# Week 3 — Summary

Frontend. Branch `feat/week3-frontend` (off `project`, never `main`). Order followed:
PLAN D1→D5. The backend gained only what the UI needed (a conversations list endpoint, a
conversation DELETE, one provisioning fix); everything else this week is React.

## D1 — Routing, auth, data layer

1. Providers — `src/app/providers.tsx` — `<AuthProvider>` (react-oidc-context, driven by our own UserManager) wrapping TanStack Query. Auth outermost so every query sees the current token.
2. OIDC — `src/lib/oidc.ts` — one shared `UserManager` for the `knowveris-web` public client (code + PKCE S256), tokens persisted in `localStorage`, `automaticSilentRenew`.
3. JWT interceptor — `src/lib/apiClient.ts` — a single Axios instance; the Bearer token is attached in exactly one place (project rule: never pass a token by hand). `apiErrorDetail` unwraps FastAPI's `detail`, which is a string for an `HTTPException` but a list of objects for a 422.
4. Guards — `ProtectedRoute` (authenticated) + `RoleGuard` (realm role, `admin` composite satisfies `employee`, mirroring the backend's `require_admin`).
5. Commit — `01ffce0` feat(web): Week 3 D1 — router, OIDC, TanStack Query, JWT interceptor, guards.

## D2 — Layout, dashboard, history

6. Conversations endpoint — `app/api/v1/endpoints/conversations.py` — `GET /api/v1/conversations` with per-conversation message counts (commit `6c35fe1`).
7. Shell — `AppLayout` + `LeftSidebar` — fixed sidebar (avatar, role badge, nav, theme toggle, logout) + scrollable content region.
8. Center panel — `StatsCard` (conversation + message totals) and `HistoryCard` → `/history`, both reading the shared `["conversations"]` query.
9. Delete conversation — `DELETE /api/v1/conversations/{id}` + a confirmation prompt in the list (commit `c2d6799`).
10. Commit — `d581f0c` feat(web): Week 3 D2 — 3-column layout, Left Sidebar, StatsCard + HistoryCard.

## D3 — Streaming chat

11. SSE transport — `features/chat/api.ts` — hand-rolled frame parser over `fetch` (Axios buffers a response before resolving, so it cannot read a body while it streams). `token` events feed the visible answer; the closing `final` event carries citations, flags and timings.
12. `authorizedFetch` — `lib/apiClient.ts` — the same auth rules as the Axios instance for the one call that cannot use it.
13. Chat panel — `ChatPanel` / `ChatTurn` — partial answers live in component state, not the query cache (they arrive dozens of times a second); the conversation *list* is cached and invalidated when a turn completes. The persisted answer replaces the concatenated deltas at the end — a refusal streams no token, and guardrail 2 may have stripped a citation.
14. Sources — `SourceCard` — document + page (PDF) or § section (DOCX) + score, per ADR-005.
15. RTL — `lib/rtl.ts` — direction detected **per message**, not per page: sniffed from the script while streaming, then replaced by the pipeline's own language detection when `final` lands.
16. Commit — `e1e7604` feat(web): Week 3 D3 — SSE streaming chat, SourceCard, per-message RTL.

## D4 — Admin screens

17. Documents — `DropZone` (drag & drop or click, PDF/DOCX only) + `DocumentTable` polling `GET /documents` every 5 s while anything is `PENDING/PARSING/EMBEDDING`, and stopping on its own once everything is `INDEXED`/`FAILED` (PLAN Flow A).
18. Upload quirk — the `multipart/form-data` header override is required, not cosmetic: the shared instance defaults to JSON, and Axios v1 serialises a FormData body to JSON when the request declares a JSON content type, so the API saw `{"file":{}}` and answered 422.
19. Employees — `CreateUserForm` / `UsersTable` / `TemporaryPassword` — creation, enable/disable, password reset, temporary password shown exactly once. No delete action, by design (PLAN §3).
20. Commit — `ce29543` feat(web): Week 3 D4 — admin documents (drag & drop + status polling) and employee accounts.
21. ⚠️ Orphan-account bug — provisioning created the Keycloak user, then failed on the password or role step, leaving an account that existed in Keycloak but not in Postgres and could not be recreated (409 forever). Fixed by rolling the Keycloak user back when any later step fails. Commit `0649804` fix(api): roll back a half-created Keycloak account when provisioning fails. (45 tests passing.)

## D5 — Error handling, loading, responsive, session expiration

22. Error messages — `lib/apiClient.ts` — `friendlyErrorMessage` covers what `detail` does not: a network drop (the most common failure when everything runs in local containers) previously surfaced as "Network Error", and a bare 5xx as nothing at all. Order: endpoint `detail` → known status wording → raw exception.
23. Query policy — `providers.tsx` — retrying a 401/403/404 is pointless and each retry produces another expiry signal, so those fail fast; everything else gets one retry. Mutations never retry — replaying one could create a second employee account.
24. Panel states — `components/ui/state.tsx` — `ErrorState` (message + **Try again** wired to the query's `refetch`) and `EmptyState`, replacing four ad-hoc `<p className="text-destructive">` variants that offered no way out but a full page reload — which on this stack also re-runs the OIDC session check.
25. Toasts — `components/ui/toast.tsx` — for failures with nowhere to render. A failed delete was the concrete case: the row is gone the moment the dialog closes, so the error had no anchor and a failure looked exactly like a success until the list refetched.
26. Error boundary — `app/ErrorBoundary.tsx` — both catchers, because they cover different halves: React Router intercepts anything thrown inside a route (`errorElement`), and only a class component sees a crash above it. Either one alone still leaves a white screen for half the failures.
27. Chat retry — `ChatPanel.ask(text?, retryOf?)` — re-asks a failed turn in place instead of appending a duplicate. At 60-90 s per answer, "retype it and wait again" is not a recovery path.
28. 🎯 **Session expiration** — the realm gives an access token 5 min and idles the SSO session out after 30 (PLAN §3), so this is a routine event, not an edge case.
    - `lib/session.ts` — a tiny event bus. Expiry is discovered outside React (a 401 in the transport layer, a failed silent renew in the UserManager); both publish, one dialog subscribes.
    - `lib/oidc.ts` — subscribes to `addSilentRenewError` / `addAccessTokenExpired` / `addUserSignedOut` so the dialog appears **when renewal fails**, not on the user's next click.
    - `SessionExpiredDialog` — blocking, not a toast: everything behind it will 401, so "carry on" would be a lie. Deliberately *not* an automatic redirect either — one fired mid-answer discards a 60-90 s generation with no explanation.
    - Return path — the OIDC `redirect_uri` is pinned to the app root, so an admin who expires on `/admin/users` would land on the dashboard. The path is stashed at expiry time (by then the router already says `/login`) and consumed once after re-login.
    - `RootLayout` — the dialog is mounted **above** `ProtectedRoute`: dropping the token flips that guard to `/login` in the same tick, and a dialog mounted inside it would unmount before it was ever seen.
29. Responsive — `AppLayout` is two shapes: the fixed 260 px sidebar from `md` up, and below that an off-canvas drawer behind a top bar (a 260 px column on a phone leaves nothing for the answer). The content region is height-constrained only on `md`, so on a phone the page scrolls as a whole. On the dashboard the chat moves **first** when the columns stack — it is why an employee opens the app. Tables drop context columns (`language`, `size`, `uploaded`; `name`, `email`) at `sm`/`md` and fold them into the primary cell.
30. Favicon + head (left over from D4) — `public/favicon.svg` (a page, a K, and the accent dot standing for the citation every answer carries), plus `description`, `color-scheme`, per-scheme `theme-color`, and a pre-paint inline script that applies the stored theme. Without that script the app rendered light and `useTheme` flipped it a frame later — a white flash on every reload in dark mode.
31. Smaller fixes — `DropZone` reports rejected filenames (dragging in a mixed folder and seeing nothing happen reads as a broken drop zone); the upload progress line says *which* file and how far into the batch; per-row spinners on the admin table via the mutation's `variables`; `Button` gained a `loading` prop that implies `disabled`.

## Status — Week 3 complete

**Done:** D1 routing/auth/data layer · D2 layout + dashboard + history · D3 SSE streaming chat with sources and RTL · D4 admin documents + employee accounts · D5 error handling, loading states, responsive design, session expiration, favicon.

`npm run build` (tsc strict + vite) green; every changed module verified against the running dev server.

**Not done / carried:**

- **Multi-turn** (PLAN §9, "nice-to-have if time permits") — not started. The lightweight design (query fusion for retrieval + last 2 turns in the prompt, no extra LLM call) is specified in PLAN and stays a Week 4 buffer item.
- **Reopening a past conversation** from the history list — the rows delete but do not load back into the chat panel; it depends on multi-turn.
- `npm run lint` — the script is declared but ESLint was never added as a dependency, so the command fails. TypeScript strict mode is the actual gate today.
- The Week 2 measurement-only items (live reranker table, quiet-machine latency re-benchmark, generation-quality eval, live run of the FATF demo golden set) are unchanged and still feed the report.
