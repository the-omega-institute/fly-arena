# Contributing

Keep changes small, testable, and honest about what is modeled versus
recorded. Do not fabricate activity, poses, performance, or biological claims;
keep failed and incomplete runs visible.

Before opening a change, run the focused tests and the repository checks:

```sh
uv run pytest -q -m "not integration"
cd web && npm test && npm run test:journeys && npm run build
```

Document new third-party data or assets in `NOTICE.md` and
`docs/ATTRIBUTION.md`. Never commit credentials, local deployment paths, raw
connectome downloads, ignored runtime data, or private user records.
