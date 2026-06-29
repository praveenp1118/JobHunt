# API conventions — apply to ALL routers

## Authentication
- Every endpoint uses: user = Depends(get_current_user)
- Public endpoints explicitly documented with # PUBLIC

## Response format
- Success: return Pydantic schema or dict
- Error: raise HTTPException(status_code=N,
         detail={"code": "snake_case", "message": "..."})
- Never return raw exception messages

## Pagination
- All list endpoints support: page=1, limit=50
- Return: {items: [...], total: N, page: N,
          limit: N, total_pages: N}
- Default limit: 50, max: 200

## Filtering
- Jobs endpoints always accept:
  source, feed_id, domain_cv_id, market
- Always filter by user_id first

## Naming
- GET /api/{resource} → list
- GET /api/{resource}/{id} → single item
- POST /api/{resource} → create
- PATCH /api/{resource}/{id} → partial update
- DELETE /api/{resource}/{id} → delete
- POST /api/{resource}/{id}/{action} → custom action

## Token logging
- Every Claude API call must call log_anthropic_usage()
- Every Apify call must call log_apify_usage()
- Never skip usage logging
