# RegRAG Frontend (Phase 5B)

Operational Next.js 15 frontend for FDA regulatory research workflows.

## Setup

1. Copy `.env.example` to `.env.local`.
2. Fill in all public variables:
   - `NEXT_PUBLIC_API_BASE_URL`
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY`
3. Install dependencies:

```bash
npm install
```

## Scripts

- `npm run dev` - start local app.
- `npm run build` - production build.
- `npm run start` - run production server.
- `npm run lint` - run ESLint.
- `npm run typecheck` - run TypeScript checks.
- `npm run test` - run Vitest once.
- `npm run test:watch` - run Vitest in watch mode.
- `npm run test:e2e` - run Playwright tests.
- `npm run api:types` - regenerate OpenAPI types from checked `openapi.json` and fail if forbidden `raw_object_key` appears.

Install the Chromium runtime once before running browser tests:

```bash
npx playwright install chromium
```

The unauthenticated redirect, login, accessibility, responsive, and visual checks run without
credentials. Set `E2E_USER_EMAIL` and `E2E_USER_PASSWORD` to enable the authenticated research,
search, chat, and alerts accessibility checks. Credentialed runs use one worker because all browser
projects reuse the same local Supabase account.

## Notes

- Authentication uses Supabase SSR helpers and secure cookies.
- This app does not use service-role keys in the browser.
- API authority remains on backend RBAC and ownership checks.
- For local authentication, run `npx --yes supabase@latest start` from the repository root and
  create confirmed password users in Supabase Studio at `http://127.0.0.1:54323`.
- `npm audit --omit=dev` currently reports four high-severity findings inherited from Next.js
  15's pinned `postcss`/`nanoid` and `sharp` dependencies. npm's proposed force fix downgrades
  Next.js to 9, so it must not be applied. Reassess when a compatible Next.js 15 patch or the
  approved framework upgrade provides patched transitive versions.
