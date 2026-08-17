# Bug analysis: Negative index pagination in `/api/guilds/{guild_id}/warnings`

## 1. Root cause analysis
In [`api.py`](file:///d:/Python%20Project/AC%20Carrot/api.py), the `get_warnings` endpoint (defined around line 300) accepts `page` and `limit` query parameters with default values of `1` and `10` respectively:

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

Later, at line 399-401, the pagination slicing indexes are computed and applied to the `filtered_warnings` list:

```python
    # Apply Pagination
    start = (page - 1) * limit
    end = start + limit
    page_warnings = filtered_warnings[start:end]
```

### The behavior under 0 or negative values:
1. **If `page = 0` (assuming `limit = 10`):**
   * `start = (0 - 1) * 10 = -10`
   * `end = -10 + 10 = 0`
   * Slicing expression: `filtered_warnings[-10:0]`
   * In Python, a negative start index in a slice slices relative to the end of the list. However, because the end index is `0`, this slice starts 10 elements from the end and goes up to (but not including) index `0` (which is the beginning). Consequently, this returns an empty list `[]`.

2. **If `page < 0` (e.g., `page = -1`, `limit = 10`):**
   * `start = (-1 - 1) * 10 = -20`
   * `end = -20 + 10 = -10`
   * Slicing expression: `filtered_warnings[-20:-10]`
   * This slices from the 20th element from the end of the list up to the 10th element from the end of the list, returning elements from the end of the warnings list.

In Python, list slicing accepts negative indices without raising an `IndexError`. Because FastAPI does not validate that `page` or `limit` are strictly positive integers, clients can send arbitrary integer values, leading to unexpected slice behavior.

---

## 2. Proposed solution
To restrict `page` and `limit` parameters to positive integers, we can utilize FastAPI's native query validation helper `Query` (imported from `fastapi`).

We can constrain:
* `page` to be greater than or equal to 1 (`ge=1`).
* `limit` to be greater than or equal to 1 (`ge=1`) and optionally add a maximum limit limit (e.g., `le=100`) to prevent denial-of-service/heavy database queries.

### Suggested code modifications (Not yet applied)

1. Import `Query` from `fastapi`:
   ```python
   from fastapi import Query
   ```

2. Update the endpoint signature in [`api.py`](file:///d:/Python%20Project/AC%20Carrot/api.py):
   ```python
   @app.get("/api/guilds/{guild_id}/warnings")
   async def get_warnings(
       request: Request, 
       guild_id: int, 
       page: int = Query(default=1, ge=1, description="Page number, must be >= 1"), 
       limit: int = Query(default=10, ge=1, le=100, description="Items per page, must be between 1 and 100"), 
       sort_key: str = "id", 
       sort_dir: str = "desc", 
       search: str = "", 
       staff: str = "",
       access_level: str = Depends(requires_view_access)
   ):
   ```

With this change, if a client sends `page=0` or `page=-5`, FastAPI will automatically reject the request with a `422 Unprocessable Entity` status code and return a clear error validation detail explaining that the value must be greater than or equal to 1.
