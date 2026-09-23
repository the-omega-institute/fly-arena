# Public preview at fly.omega.gift

The frontend is published to GitHub Pages from the internal source repository. The Pages site is public; repository visibility is unchanged. An explicit workflow dispatch builds and tests the web app, embeds the repository variable `ARENA_PREVIEW_API`, and deploys it to `fly.omega.gift`.

The API and simulations run on Mac Studio. Set `ARENA_WEB_ORIGIN=https://fly.omega.gift` on that API process to permit browser calls from exactly that origin. Static preview uses the existing local designer bearer tokens. It does not send cross-site cookies or activate NyxID. OpenAPI docs, AI prompts, anatomy and morphology requests use the same configured API origin.

For the initial trial, a persistent cloudflared process exposes the loopback API through a temporary HTTPS URL. The URL may change if the tunnel restarts: update `ARENA_PREVIEW_API` and dispatch the Pages workflow again. This is a trial deployment, not a stable compute endpoint. Existing queue and designer limits apply.

NyxID remains disabled until the registered client and final hosting arrangement are connected. Its prepared same-origin callback is `https://fly.omega.gift/api/v1/auth/nyxid/callback`; GitHub Pages cannot serve that backend route itself. Before enabling NyxID, route `/api` through the same origin or explicitly implement and test separate API-origin sessions. The backend rejects combining this preview CORS configuration with NyxID mode.

Do not cache private authentication responses. Keep the application and tunnel supervised, retain user data on the Mac, and drain jobs before updating simulation sources. No player code executes inside a match.
