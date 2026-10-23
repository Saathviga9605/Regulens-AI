# API Contracts

Base URL (development): `http://127.0.0.1:8000/api/v1`. All responses are JSON. Every response carries an
`X-Request-ID` header.

## GET /health

Checks the API and performs a real `SELECT 1` against the configured database.

**200 OK — healthy**

```json
{
  "app_name": "ReguLens AI",
  "api_version": "v1",
  "status": "ok",
  "database": { "status": "ok", "detail": null }
}
```

**200 OK — degraded** (API reachable, database query failed)

```json
{
  "app_name": "ReguLens AI",
  "api_version": "v1",
  "status": "degraded",
  "database": { "status": "unavailable", "detail": "Database connectivity check failed." }
}
```

| Field | Type | Values |
|-------|------|--------|
| `status` | string | `ok` \| `degraded` |
| `database.status` | string | `ok` \| `unavailable` |
| `database.detail` | string \| null | Client-safe message; never contains paths or exception text |

Degraded returns HTTP 200 deliberately: the endpoint itself worked, and clients read `status`.

## GET /system/info

Safe, non-sensitive metadata. Never includes database URLs, file paths, hostnames or secrets.

```json
{
  "app_name": "ReguLens AI",
  "app_version": "0.1.0",
  "api_version": "v1",
  "environment": "development",
  "database_backend": "sqlite",
  "implemented_capabilities": ["API health check with live database probe", "..."],
  "planned_capabilities": ["Application and institutional record management", "..."]
}
```

## Error format

All errors share one shape:

```json
{
  "error": {
    "code": "internal_error",
    "message": "An unexpected error occurred.",
    "request_id": "3f2c…",
    "details": []
  }
}
```

| Status | `code` | When |
|--------|--------|------|
| 404 | `not_found` | Unknown route |
| 405 | `method_not_allowed` | Wrong HTTP method |
| 422 | `validation_error` | Request validation failed (`details` lists `loc`/`msg`) |
| 4xx | `http_error` | Other HTTP errors |
| 500 | `internal_error` | Any unhandled exception. Generic message only; stack trace logged server-side with the same `request_id`. |

## CORS

Allowed origins come from `REGULENS_CORS_ORIGINS` (exact match). Disallowed origins receive no
`Access-Control-Allow-Origin` header and preflights return 400. Credentials are not allowed.
Wildcard `*` is rejected when `REGULENS_ENVIRONMENT=production`.

## Interactive docs

`/docs` and `/openapi.json` are served outside production only.
