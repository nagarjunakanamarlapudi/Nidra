# Pragya — Web

The single-user chat shell for the **Pragya** personal assistant. A minimal
Next.js (App Router, TypeScript) app that talks to the Pragya backend API.

## Development

```bash
npm install
cp .env.local.example .env.local   # adjust if your backend isn't on :8000
npm run dev                        # http://localhost:3000
```

On first load you'll be asked for an **access token** (the backend bearer
token). It's stored in `localStorage` under `pragya_token`; use **Sign out** to
clear it.

## Environment

| Variable               | Default                 | Description               |
| ---------------------- | ----------------------- | ------------------------- |
| `NEXT_PUBLIC_API_BASE` | `http://localhost:8000` | Base URL of the Pragya API. |

The API client (`lib/api.ts`) calls `POST {NEXT_PUBLIC_API_BASE}/chat` with an
`Authorization: Bearer <token>` header.

## Testing

```bash
npm test        # vitest run
```

Tests live in `__tests__/`. `api.test.ts` mocks `fetch` and verifies the
request shape, the response mapping, and error handling.

## Build

```bash
npm run build   # production build (standalone output)
npm run lint    # eslint
```

## Docker

The `Dockerfile` produces a small, non-root image from Next.js standalone
output:

```bash
docker build -t pragya-web .
docker run -p 3000:3000 -e NEXT_PUBLIC_API_BASE=http://host.docker.internal:8000 pragya-web
```

> `NEXT_PUBLIC_*` values are inlined at **build** time. To point the image at a
> different API, set `NEXT_PUBLIC_API_BASE` as a build arg/env during
> `docker build`, or rebuild for the target environment.
