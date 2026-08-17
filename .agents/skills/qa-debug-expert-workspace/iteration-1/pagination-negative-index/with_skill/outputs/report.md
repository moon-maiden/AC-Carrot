# Bug Diagnostics Report

## Executive Summary
In the `get_warnings` endpoint (and similarly `get_paid_requests`) of [api.py](file:///d:/Python%20Project/AC%20Carrot/api.py), input parameters `page` and `limit` are not validated to be positive integers. When a client passes `page <= 0` (e.g. `page=0` or `page=-1`), the start index computation `(page - 1) * limit` results in a negative number. When sliced against the `filtered_warnings` list, Python interprets the negative index as counting backwards from the end of the sequence, leading to unexpected pagination results containing elements from the end of the list.

## Reproduction Steps
A request can be made to the warnings API with `page=0` or a negative value:
```http
GET /api/guilds/123/warnings?page=0&limit=10
Authorization: Bearer <token>
```
1. `start = (0 - 1) * 10 = -10`
2. `end = -10 + 10 = 0`
3. Slicing `filtered_warnings[-10:0]` returns the last 10 elements of the warnings list instead of the first page.

## Root Cause Analysis
* **Location:** [`api.py` (L303-304)](file:///d:/Python%20Project/AC%20Carrot/api.py#L303-L304) and [`api.py` (L399-401)](file:///d:/Python%20Project/AC%20Carrot/api.py#L399-L401).
* **Issue:** 
  In the endpoint definition:
  ```python
  @app.get("/api/guilds/{guild_id}/warnings")
  async def get_warnings(
      request: Request, 
      guild_id: int, 
      page: int = 1, 
      limit: int = 10, 
      ...
  ):
  ```
  The values for `page` and `limit` are typed as `int` but not constrained.
  Then, the slice calculation:
  ```python
  start = (page - 1) * limit
  end = start + limit
  page_warnings = filtered_warnings[start:end]
  ```
  computes `start` and `end` as negative integers when `page <= 0` (and `limit > 0`), which triggers Python's negative list slicing.

## Recommendations for the Fix

### Option 1: Pydantic / FastAPI Query Parameters Constraints (Recommended)
FastAPI can automatically validate query parameters using FastAPI's `Query` class and Pydantic constraints. This is the cleanest approach as it yields a structured `422 Unprocessable Entity` validation error before the handler code executes.

```python
from fastapi import Query

# In get_warnings signature:
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=100),
```

### Option 2: Inline Validation and Defaulting
Alternatively, enforce a lower bound within the endpoint body:

```python
page = max(1, page)
limit = max(1, limit)
```
