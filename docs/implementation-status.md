# Implementation Status

Last verified: 2026-10-23 on Windows 11, Python 3.13.14, Node 24.19.0 / npm 11.17.0.

Statuses: **Implemented and tested** · **Implemented but not fully tested** · **Planned** · **Blocked**

## Deliverable 1 — Foundation

| Feature | Status | Evidence |
|---------|--------|----------|
| FastAPI app factory, `/api/v1` prefix | Implemented and tested | all backend tests |
| `GET /api/v1/health` with real `SELECT 1` | Implemented and tested | `test_health.py` (structure, query captured via SQLAlchemy event, file created) |
| Degraded health when DB unusable | Implemented and tested | `test_health_reports_degraded_when_database_unreachable`; also verified live on a running server |
| `GET /api/v1/system/info` (safe metadata) | Implemented and tested | `test_system_info.py` |
| Centralised settings (`REGULENS_*`, repo-root `.env`) | Implemented and tested | `test_relative_sqlite_path_resolves_under_repo_root`; live run read `.env` |
| SQLite engine, per-request sessions, data dir creation | Implemented and tested | `test_health_creates_database_file_in_configured_location` |
| `init_db` initialisation | Implemented and tested | runs in every test app's lifespan |
| Consistent error responses (404/405/422/500) | Implemented and tested (422 not directly exercised — no endpoint takes input yet) | `test_errors.py` |
| 500 handler hides stack traces/paths | Implemented and tested | `test_unexpected_exception_hides_internal_details` |
| CORS allow-list; wildcard rejected in production | Implemented and tested | `test_cors_and_config.py`; live cross-origin request verified |
| Structured JSON logging | Implemented but not fully tested | observed in live server output; no automated assertion |
| `X-Request-ID` header | Implemented and tested | `test_health_returns_expected_structure` |
| Dashboard shell, sidebar, responsive nav | Implemented and tested (render) | `dashboard.test.tsx`; responsive layout not visually verified in a browser |
| Typed API client | Implemented and tested | via dashboard tests |
| Loading / connected / degraded / disconnected states | Implemented and tested | `dashboard.test.tsx` |
| Retry triggers new request | Implemented and tested | `retry triggers a new health request…` |
| Module placeholder pages (no fabricated data) | Implemented and tested | `Module placeholders` test |
| Production build | Implemented and tested | `npm run build` succeeded |
| Frontend ↔ backend live connectivity | Implemented and tested (manual) | Vite dev server served app with configured `VITE_API_BASE_URL`; cross-origin request from the dev origin returned 200 with correct CORS header. Not rendered in a real browser. |

## Later deliverables

| Feature | Status |
|---------|--------|
| Application & institution management | Planned |
| PDF upload & storage | Planned |
| OCR | Planned |
| Evidence-linked extraction | Planned |
| Regulatory rules with provenance | Planned |
| Cross-document consistency checks | Planned |
| Anomaly detection | Planned |
| Simulated issuer verification | Planned |
| Review queue & human decisions | Planned |
| Audit trail | Planned |
| Preliminary scrutiny reports | Planned |
| Authentication & roles | Planned |
| Alembic migrations | Planned |

## Verification log (2026-10-23)

| Check | Result |
|-------|--------|
| `python -m pytest` | 12 passed (1 upstream deprecation warning from Starlette TestClient/httpx) |
| `npm test` | 8 passed |
| `npm run typecheck` | 0 errors |
| `npm run build` | success (~208 kB JS, 67 kB gzip) |
| `npm audit` | 0 vulnerabilities |
| Live `GET /health` | 200, `status: ok`, `database: ok` |
| Live degraded server (DB path is a directory) | 200, `status: degraded`, no path leaked |
| Live CORS from dev origin | `Access-Control-Allow-Origin` echoed correctly |

## Known limitations

- Port 5173 was occupied by an unrelated app on the verification machine; live checks used port 5180 with a
  matching CORS override. Default config targets 5173.
- npm 11 blocked esbuild's postinstall script (`allow-scripts`); builds and tests work regardless because the
  platform binary ships as an optional dependency.
