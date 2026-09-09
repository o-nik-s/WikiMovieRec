# Web Application Guide

## Quick Start

### Local Development

```powershell
# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Install web dependencies
pip install flask flask-wtf wtforms celery redis gunicorn

# Run Flask dev server
python -m web.app
```

Open http://localhost:5021 in your browser.

### Current File-Based Production Deployment

```bash
# Upload a source archive and unpack it on the server.
# Then create/refresh the virtual environment and install requirements.
./deploy_commands.ps1
```

Services will be available at:
- Web app: http://217.144.186.110:5021

### Production Deployment

The server runs `gunicorn` behind `systemd` with a persistent `.venv` in the app directory.
Current production now uses **native Redis + Celery** without Docker:
- `timeseries-web` handles the HTTP app;
- `timeseries-worker` runs forecasting jobs;
- Redis runs as a local system service on the same host.
The deploy script updates files in place, installs Python dependencies, writes a local `.env.server`, and restarts both services.

Systemd unit templates are in `deploy/`:
- `deploy/timeseries-web.service`
- `deploy/timeseries-worker.service`

The worker unit includes `TRITON_DISABLE=1` to prevent Triton JIT segfaults on CPU-only servers.

## Architecture

```
┌─────────────┐     ┌──────────────┐
│   Browser   │────▶│  Flask Web   │
│  (Jinja2)   │◀────│  (Gunicorn)  │
└─────────────┘     └──────────────┘
         │
         ▼
       ┌──────────────┐
       │  Pipeline    │
       │ (Forecasting)│
       └──────────────┘
```

### Components

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Web Server | Flask + Gunicorn | HTTP requests, templates, static files |
| Task Queue | Celery worker (`--pool=solo`) | Background processing of long-running jobs without fork-related crashes |
| Broker | Redis (local system service) | Job queue and result storage for Celery |
| Pipeline | `pipeline.run_pipeline()` | Core forecasting logic |

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TS_WEB_ENV` | `development` | Web environment (`development`/`production`) |
| `TS_WEB_SECRET_KEY` | generated locally | Flask session secret; required in production |
| `TS_PROXY_SHARED_SECRET` | empty locally | Secret shared by the authenticated reverse proxy and Flask |
| `TS_AUTH_REQUIRED` | production default | Require proxy identity headers |
| `REDIS_PASSWORD` | unset locally | Redis password when Celery/Redis mode is enabled |
| `TS_REDIS_ALLOW_LOCALHOST` | `false` | Allow localhost Redis URLs in production on single-host deployments |
| `CELERY_BROKER_URL` | `redis://127.0.0.1:6379/0` | Redis broker URL for Celery |
| `CELERY_RESULT_BACKEND` | `redis://127.0.0.1:6379/0` | Redis result backend for Celery |
| `TS_USE_CELERY` | `true` in production | Enable background worker mode |
| `TS_ALLOW_THREAD_FALLBACK` | `false` in production | Disable in-web thread fallback for long jobs |
| `MAX_CONTENT_LENGTH` | `16MB` | Max file upload size |

### Celery Configuration

> The current production server uses Celery + Redis as native system services. The worker runs with `--pool=solo` because fork-based child processes were crashing on ML-heavy jobs.

```python
# web/tasks/celery_app.py
broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
result_backend = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
task_time_limit = 600  # 10 minutes hard limit
task_soft_time_limit = 540  # 9 minutes soft limit
```

## API Endpoints

### REST API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/models/` | List available forecasting models |
| GET | `/api/modes/` | List available pipeline modes |
| GET | `/api/ready/` | Readiness with job store + Celery diagnostics |
| GET | `/api/worker/health/` | Worker health status when Celery is enabled |
| GET | `/results/<job_id>/status` | Get job status (JSON) |
| GET | `/results/<job_id>/download` | Download HTML report |

### Web Routes

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Landing page |
| GET/POST | `/analysis/` | Analysis form |
| GET | `/results/<job_id>` | Results page |

## Job Lifecycle

1. User submits analysis form
2. Flask creates job record and saves CSV (if uploaded)
3. A background task is dispatched via Celery when enabled; thread fallback is disabled in production
4. Worker or thread runs `pipeline.run_pipeline()`
5. Results are saved to `reports/results/`
6. Job status is updated
7. User polls `/results/<job_id>/status` for completion
8. Report is available for download

## Development Workflow

### Run tests

```bash
pytest tests/ -v
```

### Lint and format

```bash
ruff check .
ruff format .
mypy . --ignore-missing-imports
```

### Debug Celery tasks

```bash
# Run worker in debug mode
celery -A web.tasks.pipeline_tasks worker --pool=solo --loglevel=debug

# Monitor tasks
celery -A web.tasks.pipeline_tasks inspect active
```

## Troubleshooting

### Celery worker not connecting to Redis

```bash
# Check Redis is running
redis-cli ping

# Check worker logs
journalctl -u timeseries-worker -n 100 --no-pager
```

### Job stuck in "running" state

```bash
# Check worker status
journalctl -u timeseries-worker -n 200 --no-pager

# Restart worker
systemctl restart timeseries-worker
```

### File upload fails

- Check `MAX_CONTENT_LENGTH` in Flask config (default: 16MB)
- Verify `data/uploads/` directory exists and is writable

## Security Notes

- Set `TS_WEB_SECRET_KEY`, `TS_PROXY_SHARED_SECRET` and `REDIS_PASSWORD` through a secret manager when Celery/Redis mode is enabled
- Use HTTPS in production
- Use managed Redis with TLS/ACL for public deployments if Celery is enabled
- Configure the reverse proxy for Windows/SSO authentication and strip/overwrite identity headers from clients
- Set proper file permissions for `data/uploads/`
- Use Gunicorn with multiple workers for production load
- Use a solo Celery pool when ML libraries are not fork-safe
- Prefer native systemd services over Docker Compose in current production

## SSH key workflow for deployments

For repeatable deployments from VS Code, keep a reusable private key on the local machine:

- private key: `~/.ssh/deploy_ed25519`
- public key: `~/.ssh/deploy_ed25519.pub`

Recommended workflow:

1. Generate the key once with `ssh-keygen -t ed25519 -f $HOME\.ssh\deploy_ed25519 -C deploy-key`.
2. Add the public key to each server's `~/.ssh/authorized_keys`.
3. Verify access with `ssh -i $HOME\.ssh\deploy_ed25519 -o BatchMode=yes root@server`.
4. Point deploy scripts at that key.

For multiple projects, reuse the same key unless you need strict access separation.
If you do need separation, create a new key per environment and pass it through the deploy script parameter that selects the private key path.

## Scaling

### Horizontal Scaling

```bash
# Scale Gunicorn workers by editing the systemd service or deploy script
systemctl edit timeseries-web
```

### Vertical Scaling

- Increase Gunicorn workers: `--workers 4` (rule of thumb: 2-4 per CPU core)
- Enable Celery only if background queueing is required; for current production it is already enabled
- Use persistent app storage for reports and logs

## Monitoring

### Job Status

```python
# Check job status via API
import requests
response = requests.get("http://localhost:5021/results/<job_id>/status")
print(response.json())
```

### Worker Metrics

```bash
# Active tasks
celery -A web.tasks.pipeline_tasks inspect active

# Scheduled tasks
celery -A web.tasks.pipeline_tasks inspect scheduled

# Worker stats
celery -A web.tasks.pipeline_tasks inspect stats
```

### Automatic stale job cleanup

The health cron script also calls `job_store.recover_stale_jobs()` so abandoned
`pending` or `running` rows are marked failed with `Job expired before completion`.
This keeps old historical rows from polluting the dashboard and counters.