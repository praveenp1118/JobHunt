Run the full test suite and report results.

```bash
docker-compose exec backend pytest tests/ -v 2>&1 | tail -20
```

Report:
- Total tests passing
- Any failures with error message
- Whether count is above 136 (current minimum)
