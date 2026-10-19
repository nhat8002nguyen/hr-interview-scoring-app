# Talotrace production deploy

The API runs on the existing `116.118.9.222` host and shares the `type-by-voice` nginx and certbot.
The two Next.js apps deploy on Vercel.
This stack does not publish ports 80 or 443.

## Host layout

- Repository: `/opt/talot-assessment`
- Environment file: `/opt/talot-assessment/deploy/.env`
- Shared edge: `/opt/type-by-voice/deploy`
- Shared Docker network: `talot-edge`
- API hostname: `https://talot-api.nate-ng.com`

`edge-init.sh` writes `/opt/type-by-voice/deploy/docker-compose.override.yml` so the existing nginx joins `talot-edge`.
It also writes the ACME bootstrap site and issues the certificate through the existing certbot service.
The existing certbot renewal loop renews the new certificate automatically.

## DNS

Create this record before the first certificate:

```text
A talot-api.nate-ng.com -> 116.118.9.222
```

Use DNS-only mode (grey cloud) for the first issuance.
Verify with:

```bash
dig +short talot-api.nate-ng.com
```

## First-time setup

On the host:

```bash
cd /opt/talot-assessment/deploy
cp .env.example .env
chmod 600 .env
```

Generate secrets and fill `.env`:

```bash
openssl rand -hex 32          # JWT_SECRET
openssl rand -base64 24       # POSTGRES_PASSWORD (use alphanumeric only)
openssl rand -base64 18       # SEED_HR_PASSWORD
```

Set `DEEPSEEK_API_KEY`, `CORS_ORIGINS`, and `CANDIDATE_WEB_ORIGIN` to the real values.
Never commit `.env`.

Issue the certificate:

```bash
chmod +x scripts/*.sh
./scripts/edge-init.sh
```

The script prints the certificate location.
If nginx cannot validate the TLS config yet, that is expected: the talot API container does not exist until the first deploy.

## Deploy

The GitHub Actions workflow builds and pushes the image, updates `IMAGE_TAG`, and runs:

```bash
cd /opt/talot-assessment/deploy
./scripts/deploy.sh
```

For a manual deploy:

```bash
IMAGE_TAG=<sha-or-latest> GHCR_OWNER=nhat8002nguyen ./scripts/deploy.sh
```

The script pulls the image, starts `api-db`, `migrate`, and `api`, waits for `/health`, connects nginx to `talot-edge` if needed, installs the TLS site, and reloads nginx.

If the GHCR package is private and the host login is stale:

```bash
GHCR_USER=nhat8002nguyen GHCR_TOKEN=<read:packages-pat> ./scripts/ghcr-login.sh
```

## Verify

```bash
curl -fsS https://talot-api.nate-ng.com/health
curl -fsS https://tbv-api.nate-ng.com/health
```

Both must return `{"status":"ok"}`.

From the repository root, run the production smoke:

```bash
(cd apps/backend && uv run python ../../scripts/smoke_integration.py \
  --api-url https://talot-api.nate-ng.com \
  --candidate-origin https://talot-candidate-web.vercel.app \
  --pack ../../intial-resources/business-systems-pack.zip \
  --audio ../../intial-resources/business-systems-pack/answers/A031.m4a \
  --timeout 600)
```

## Rollback

Set `IMAGE_TAG` to the previous known-good SHA and run `./scripts/deploy.sh`.
The database volume is not touched.

## Security notes

- Keep `.env` at mode `600` and out of Git.
- The existing certbot container mounts the Docker socket so it can reload nginx.
  That is a documented tradeoff inherited from the template; keep the image pinned.
- Rotate the Vercel token and VPS root password after setup.
