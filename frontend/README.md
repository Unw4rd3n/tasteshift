# TasteShift frontend

Orbital Observatory: a selectable solar system with a quiet editorial detail panel. This is the consumer UI for the Python API, not a replacement for it.

## Run locally

Use Node 22 LTS or newer. Start the API and PostgreSQL using the repository README, then:

```sh
cd frontend
npm ci
npm run dev -- --port 4173 --strictPort
```

Open `http://127.0.0.1:4173`. The first system is explicitly a sample and makes no provider calls. **Make it yours** searches Qloo; select three to five confirmed interests. An optional intention uses the experience planner. Safe → Wild requests a new selection only in live mode.

API calls use relative `/api` URLs and guest-session cookies. The Vite proxy targets `http://127.0.0.1:8000`; `.env.example` documents overrides. The proxy adapts only a same-origin loopback development Origin to the backend's configured Origin. Foreign origins are not rewritten. No provider keys belong in the frontend.

Saved cards remain on this device. Live saves first wait for server acknowledgement; preview saves are labelled as samples. Refresh returns to the preview, while bookmarks remain. There is no account sync or session-history restoration yet.

## Verify

```sh
npm run typecheck
npm test
npm run format:check
npm run build
npm run test:sites
```

Component tests cover sample/live separation, selection, search races, retry idempotency, empty/error states, acknowledged feedback and reduced motion. Boundary tests cover requests and URL safety. Live browser checks and visual comparison are recorded in `design-qa.md`; ordinary tests do not call providers.

## Hosting boundary

`npm run build` emits a static client plus the starter's Sites Worker and metadata. This packages the UI; it does **not** deploy the Python API or connect a hosted UI to it. Production needs HTTPS and a same-origin `/api` reverse proxy to FastAPI, with exact `APP_ORIGIN`, secure cookies and deployment-level rate limits. Never reuse the development Origin adapter in production.

There is no automatic fallback from failed Qloo results to sample data. Exploration availability comes from the API's coverage flags. Planets and orbit distances are an interface metaphor, not affinity measurements or liking probabilities.
