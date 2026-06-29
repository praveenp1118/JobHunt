Show recent logs from all services.

```bash
echo "=== BACKEND ==="
docker-compose logs backend --tail 20

echo "=== WORKER ==="
docker-compose logs worker --tail 20

echo "=== BEAT ==="
docker-compose logs beat --tail 10
```

Look for: ERROR, WARNING, Exception, Traceback
Report any issues found.
