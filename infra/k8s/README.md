# Deploying the Nidra backend to DOKS

The backend stack (FastAPI API + 5 scheduled CronJobs) on the `pragya-hackathon`
cluster, fronted by ingress-nginx + cert-manager with free TLS on a `sslip.io`
host. Postgres is **DO Managed Postgres** (`pragya-db`); the agent runs the
**claude-code** engine pointed at the **DO inference gateway**.

Images live in DOCR (`registry.digitalocean.com/nidra-pragya/backend`).

## One-time cluster setup

```sh
# 1. Registry pull secret in the namespace (the Deployment references it).
kubectl create namespace nidra --dry-run=client -o yaml | kubectl apply -f -
doctl registry kubernetes-manifest --namespace nidra --name registry-nidra-pragya | kubectl apply -f -

# 2. Ingress controller (provisions a DO load balancer) + cert-manager.
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo add jetstack https://charts.jetstack.io
helm repo update
helm install ingress-nginx ingress-nginx/ingress-nginx \
  -n ingress-nginx --create-namespace --set controller.publishService.enabled=true
helm install cert-manager jetstack/cert-manager \
  -n cert-manager --create-namespace --set crds.enabled=true

# 3. Managed Postgres: allow the cluster, enable pgvector.
doctl databases firewall append <DB_ID> --rule k8s:<CLUSTER_ID>
# then connect once and:  CREATE EXTENSION IF NOT EXISTS vector;
```

## Build + push the image

```sh
doctl registry login
docker buildx build --platform linux/amd64 \
  -t registry.digitalocean.com/nidra-pragya/backend:v1 --push backend
```

(`--platform linux/amd64` is required — the nodes are amd64.)

## Configure + deploy

```sh
cp infra/k8s/secret.env.example infra/k8s/secret.env   # gitignored
# fill secret.env from root .env + the PROD OVERRIDE lines (DB URL, DO inference, URLs)
kubectl apply -k infra/k8s
kubectl -n nidra rollout status deploy/backend
```

## Expose over HTTPS (after the LB has an IP)

```sh
export LB_IP=$(kubectl -n ingress-nginx get svc ingress-nginx-controller \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
export HOST="api.${LB_IP//./-}.sslip.io"
sed "s/__HOST__/${HOST}/g" infra/k8s/ingress.yaml | kubectl apply -f -

# put the real host into the public-URL keys in secret.env, then:
kubectl apply -k infra/k8s && kubectl -n nidra rollout restart deploy/backend
```

Then point `GOOGLE_OAUTH` redirect URIs + Plaid + `CORS_ALLOW_ORIGINS` at
`https://$HOST`, and set the mobile app / extension API base to it.

## Verify

```sh
curl -s https://$HOST/health
curl -s https://$HOST/ready
kubectl -n nidra get pods,cronjobs
kubectl -n nidra logs deploy/backend -f
```

## Notes / gotchas

- **Model id**: `LLM_CHAT_MODEL` must be a model the DO inference gateway serves.
  Verify against DO's inference model list; a wrong id fails at first agent call.
- **Migrations** run from the image entrypoint (`alembic upgrade head`) on boot.
  Single replica + `Recreate` strategy avoids races. Extract to a Job before scaling out.
- **Secrets**: only ever in `infra/k8s/secret.env` (gitignored) + the in-cluster
  Secret. Rotate the DO inference token and DB password after the hackathon.
- **DB TLS**: asyncpg needs `?ssl=require` (not `sslmode`).
