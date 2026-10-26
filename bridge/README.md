# Sundra Builds Bridge — Go MVP

An authenticated HTTP bridge that accepts real PNG uploads and forwards public image URLs to Upload-Post for Facebook publishing.

## Required environment

- `BRIDGE_TOKEN`: long random bearer token for protected endpoints.
- `UPLOAD_POST_API_KEY`: Upload-Post API credential.
- `PUBLIC_BASE_URL`: public HTTPS origin of this service (for example `https://your-domain.example`).
- `DATA_DIR`: persistent image directory (default `./data`).
- `PORT`: optional, default `8080`.

Run: `go run .` from `bridge/`.

## Endpoints

- `GET /healthz` — health check
- `POST /api/assets` — authenticated multipart form field `image` (1080×1350 PNG, max 12 MiB). Returns image URL and ID.
- `POST /api/posts/{id}` — authenticated JSON `{"caption":"..."}`; one publishing attempt per ID.
- `GET /api/posts/{id}` — authenticated status
- `GET /media/{id}.png` — publicly fetchable image URL for Upload-Post

Example upload:

```bash
curl -H "Authorization: Bearer $BRIDGE_TOKEN" -F "image=@post.png" https://your-domain.example/api/assets
```

Example publish:

```bash
curl -H "Authorization: Bearer $BRIDGE_TOKEN" -H "Content-Type: application/json" \
  -d '{"caption":"Educational post caption"}' https://your-domain.example/api/posts/IMAGE_ID
```

## MVP limitations / do not expose for unattended production use yet

- In-memory publishing state is **not durable** across restarts. Implement SQLite before live production use.
- Upload-Post request fields and response handling require a real integration test against your account; an HTTP 200 is deliberately recorded as `unknown`, **not** confirmed publication.
- The app validates PNG signature and dimensions but not full decoding, visual quality, or content safety.
- Protect the service with HTTPS, rate limiting, secret management, and monitoring.
- ChatGPT cannot automatically push its generated PNG bytes to an arbitrary web endpoint unless a compatible connector/upload tool is configured. This service alone does not enable that transfer.
- No GitHub repository rename was performed; rename manually under repository Settings → General if desired.
