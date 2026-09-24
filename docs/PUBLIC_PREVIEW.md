# Public preview at fly.omega.gift

The frontend is published to GitHub Pages from the internal source repository. The Pages site is public; repository visibility is unchanged. An explicit workflow dispatch builds and tests the web app, embeds the repository variable `ARENA_PREVIEW_API`, and deploys it to `fly.omega.gift`.

The API and simulations run on Mac Studio. Set `ARENA_WEB_ORIGIN=https://fly.omega.gift` on that API process to permit browser calls from exactly that origin. With `ARENA_APP_ORIGIN` set, the Pages workflow publishes a same-origin entry to the complete application; the API's `/auth/config` then reports whether live NyxID OIDC login is enabled. Without that entry, the static preview uses the existing local designer bearer flow. OpenAPI docs, AI prompts, anatomy and morphology requests use the same configured API origin.

For the initial trial, a persistent cloudflared process exposes the loopback API through a temporary HTTPS URL. The URL may change if the tunnel restarts: update `ARENA_PREVIEW_API` and dispatch the Pages workflow again. This is a trial deployment, not a stable compute endpoint. Existing queue and designer limits apply.

PR #84 ships the live NyxID login path: the registered client and backend must use the same HTTPS application origin, with callback `https://fly.omega.gift/api/v1/auth/nyxid/callback` when that is the configured origin. GitHub Pages cannot serve that backend route itself, so `ARENA_APP_ORIGIN` points the Pages entry at the API-hosted application. The backend rejects combining this preview CORS configuration with NyxID mode; check `/auth/config` before treating login as enabled.

Do not cache private authentication responses. Keep the application and tunnel supervised, retain user data on the Mac, and drain jobs before updating simulation sources. No player code executes inside a match.
