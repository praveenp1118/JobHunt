Trigger a manual scanner run via the API.

```bash
curl -X POST http://localhost:8000/api/scanner/run \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json"
```

Then check results:
```bash
docker-compose logs worker --tail 30
```

Report scan results from Activity → System tab.
