# Bug Diagnostics Report

## Executive Summary
When calling the `/api/admin/backup` endpoint to download database and attachments backup files, the API returns a `403 Forbidden` response if the environment variable `BACKUP_SECRET_TOKEN` is not configured. 

## Reproduction Steps
1. Start the API application without configuring `BACKUP_SECRET_TOKEN` in the environment variables:
   ```bash
   # Make sure BACKUP_SECRET_TOKEN is unset
   # Run the api service
   uvicorn api:app --reload
   ```
2. Request the backup endpoint with or without a token parameter:
   ```bash
   curl "http://localhost:8000/api/admin/backup?token=anything"
   ```
3. Observe the response:
   - HTTP status code `403 Forbidden`
   - Response body: `{"detail": "Forbidden: Invalid or missing token"}`

## Root Cause Analysis
- **Location:** [`api.py`](file:///d:/Python%20Project/AC%20Carrot/api.py#L47-L51)
- **Issue:** 
  In the `download_backup` endpoint handler:
  ```python
  @app.get("/api/admin/backup")
  async def download_backup(background_tasks: BackgroundTasks, token: str = None):
      expected_token = os.getenv("BACKUP_SECRET_TOKEN")
      if not expected_token or token != expected_token:
          raise HTTPException(status_code=403, detail="Forbidden: Invalid or missing token")
  ```
  If `BACKUP_SECRET_TOKEN` is not set in the environment variables, `expected_token` resolves to `None`. In this case:
  - If `token` is missing or set to any value, the condition `not expected_token` evaluates to `True`.
  - The check immediately raises a `403 Forbidden` exception, rendering the endpoint unusable regardless of what token is provided in the query string.

## Technical Details
The environment variable `BACKUP_SECRET_TOKEN` is loaded dynamically from the environment on each request via `os.getenv("BACKUP_SECRET_TOKEN")`. When it is missing, `expected_token` is `None`. Because the condition evaluates `not expected_token` first, the request is rejected before verifying `token == expected_token`.

## Recommendations for the Fix
To handle a missing token configuration, you can implement one of the following strategies:

### Option 1: Disable the backup endpoint when no secret token is configured
Raise a `501 Not Implemented` or `503 Service Unavailable` error explaining that backup services are not configured. This avoids exposing a broken endpoint with a generic `403` status.
```python
expected_token = os.getenv("BACKUP_SECRET_TOKEN")
if not expected_token:
    raise HTTPException(status_code=503, detail="Backup service is not configured on this server.")
if token != expected_token:
    raise HTTPException(status_code=403, detail="Forbidden: Invalid token")
```

### Option 2: Fall back to a default token or warn during startup
Check for the variable presence during application startup or log a warning if it is not configured.
