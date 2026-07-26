# Frontend Working Guide

## Scope

- This directory is the Next.js 14 App Router frontend for the ValueCommit research prototype.
- Keep frontend changes compatible with the FastAPI contract exposed through same-origin `/api/*` calls.
- The package has two audiences: participant study pages and researcher-only inspection/prototype pages.

## Routes and Audiences

- `app/study/survey` -> `app/study/tutorial` -> `app/study/session/new` -> `app/study/session/[sessionId]` is the participant flow.
- `app/(researcher)` owns the launcher, simulation, Rufus trace viewer, PSCon viewer, and research dashboards.
- The `(researcher)` route group adds researcher navigation without changing public URLs.
- `app/study/compare` and the `compare` / `v/[variant]` session routes are researcher prototypes despite living under `/study`.
- Do not expose research traces, ontology internals, comparison controls, or researcher navigation in the participant flow.

## API and Type Seams

- Add or change backend calls in `lib/api.ts`; components should not invent a second base URL or header policy.
- `next.config.mjs` rewrites `/api/:path*` to `BACKEND_URL`, defaulting to `http://localhost:8000`.
- `NEXT_PUBLIC_RESEARCH_KEY`, when set, is sent as `X-Research-Key` by the shared request helper.
- Shared domain shapes live in `lib/types.ts`; survey instruments and score computation live in `lib/survey.ts`.
- Existing API responses contain substantial `any` usage. Prefer explicit response types for new work and do not spread new untyped shapes through components.
- Preserve backend field names and participant/session identifiers exactly at the boundary.

## Deployment Isolation

- `APP_MODE=study` is enforced in `middleware.ts`: `/` redirects to `/study/survey`, while researcher and prototype routes are rewritten to a 404 target.
- Keep `/study/*` participant routes and `/api/*` proxy traffic reachable in study mode.
- When adding a researcher-only route, add it to the middleware matcher or place it under an already blocked prefix.
- Frontend isolation complements backend `VC_APP_MODE=study`; do not treat either layer as a substitute for the other.

## Participant State Rules

- The new-session page stores the first utterance in `sessionStorage` under `vc_first_<sessionId>`; the session page consumes it once and guards against React Strict Mode double effects.
- The main session page optimistically inserts user turns, replaces them with persisted server turns, and reloads server truth after a failed or timed-out request.
- Preserve that recovery path when changing message submission; a slow LLM request may finish server-side after the browser connection fails.
- Product feedback, conflict resolution, preference correction, evidence inspection, and post-survey submission all update the same session state.
- Render explicit empty and error states. A valid zero-product response must not look like an unchanged or broken conversation.
- Experimental variants must use the existing session APIs so comparisons reflect presentation differences, not different backend behavior.

## UI Conventions

- User-facing copy is primarily Korean; keep it concise, natural, and participant-appropriate.
- Use the shared language in `app/globals.css`: indigo `#4f46e5`, white cards, `#e4e8eb` borders, and `.card`, `.btn`, `.btn-primary`, `.chat-input`, and animation utilities.
- Use Tailwind classes for local layout and styling. Reuse shared chat, product, preference, research, study, and tutorial components before adding duplicates.
- Preserve Google Sans plus Noto Sans KR fallback, Korean word-boundary behavior, and the no-navigation participant layout.
- Most interactive surfaces are client components with local React hooks; there is no global store or query library.

## Commands and Verification

- Install dependencies: `npm install`
- Start development: `npm run dev`
- Type-check without updating incremental artifacts: `npm exec -- tsc --noEmit --incremental false`
- Lint: `npm run lint`
- Production verification: `npm run build`
- Serve a production build: `npm run start`
- There is currently no frontend test suite or test script. Do not claim test coverage; report type-check, lint, build, and any manual route exercised.
- For participant-flow changes, manually verify the complete route transition and at least one failed-request or empty-result state.
