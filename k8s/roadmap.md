# DISP → Kubernetes migration roadmap

This is the single source of truth for moving `disp` off the SSH+`docker-compose`
deploy path and onto Kubernetes. The research that produced the structural pattern
below (three public repos, compared in detail) is **not** preserved elsewhere — this
document absorbed every finding worth keeping, so treat it as authoritative rather
than going to re-derive anything from memory.

Work through tasks in order — most have a hard dependency on the one before. Update
a task's **Status** line as you go; that's the whole tracking mechanism, no separate
board.

## Status board

| # | Task | Status |
|---|------|--------|
| T0 | Directory layout & naming convention | Done |
| T1 | Namespace | Done |
| T2 | Registry pull credentials | Skipped — images are publicly pullable, see T2 |
| T3 | Postgres via CloudNativePG (CNPG) | Done — applied and Ready 2026-10-05; backups deferred to T13 |
| T4 | `api`/`worker` ConfigMap + Secret | Files written and validated 2026-10-05 (server dry-run + real `Settings`); **not yet applied**; R2 vars deferred to T8 |
| T5 | Migration Job | Not started — apply only after T8 (Procrastinate step needs full `Settings`, see T4 resolution) |
| T6 | `api` Deployment + Service | Not started |
| T7 | `worker` Deployment | Not started |
| T8 | File storage — Cloudflare R2 | Not started — needs an R2 bucket + API token created (outside kubectl) |
| T9 | `web` Deployment + Service | Not started |
| T10 | Ingress + TLS | Not started |
| T11 | pgweb | Dropped — see D4 resolution below |
| T12 | Deploy trigger (CI → cluster) | Blocked — needs decision (see Open Decisions §D5): Argo CD vs Flux |
| T13 | Production-readiness review | Not started |
| T14 | Cutover from `docker-compose` | Not started |

---

## Reference sources

Kept only as citation backing for the patterns below — don't re-fetch these unless a
task's guidance turns out to be wrong or insufficient in practice.

- **`sourcegraph/deploy-sourcegraph-k8s`** — https://github.com/sourcegraph/deploy-sourcegraph-k8s
  Real customer-facing self-host manifest set for Sourcegraph. Primary structural
  model for this migration: per-component directories, `<name>.<Kind>.yaml` file
  naming, `StatefulSet`+`PersistentVolumeClaim` for stateful services, a dedicated
  migration `Job`.
- **`GoogleCloudPlatform/bank-of-anthos`** — https://github.com/GoogleCloudPlatform/bank-of-anthos
  Google-maintained sample with a shape close to `disp` (backend services each with
  their own Postgres DB, plus a frontend). Primary model for container-spec hygiene:
  probes, resource limits, `securityContext` hardening, layered `envFrom`.
- **`GoogleCloudPlatform/microservices-demo`** (Online Boutique) — https://github.com/GoogleCloudPlatform/microservices-demo
  Weakest architectural match (no real DB) but demonstrates two useful fallback
  options: a single hand-maintained flat manifest file as a Kustomize alternative,
  and Kustomize *components* (toggleable, composable add-ons) as a lighter tool than
  full overlay duplication.

---

## Cluster facts

Verified directly against the real cluster on 2026-09-01 (`kubectl
--kubeconfig ~/.kube/falken.yaml`, context `falken` — the user's shell alias `k`
points at the same file, `~/.kube/falken.yaml`, **not** `~/.kube/falken` — note the
extension, it tripped up the first lookup). Re-verify anything below that a later
task finds inconsistent; this is a snapshot, not a guarantee.

- **Separate machine from production.** This k3s cluster runs on its own Hetzner
  server, entirely separate from the droplet currently running `docker-compose` in
  production. No shared ports/resources to worry about; T14's cutover is a DNS
  repoint between two independent hosts, not an in-place migration.
- **Namespace `mohsen-hassani-disp` exists** (T1 applied; re-verified 2026-10-05,
  label `domain=mohsen-hassani.com`, empty at that point). It is also the kubeconfig
  context's *default* namespace.
- **Ingress:** k3s's bundled Traefik, `IngressClass` named `traefik` (cluster
  default). This is a **different, in-cluster Traefik** from the one in the
  separate `infra` project the current `docker-compose` deploy uses on the other
  machine — don't confuse the two, they don't share config.
- **TLS: cert-manager is already installed and working.** Two `ClusterIssuer`s
  exist and are `Ready`: `letsencrypt-prod` and `letsencrypt-staging`, both
  ACME/Let's Encrypt via a **DNS-01 Cloudflare solver** (api token secret
  `cloudflare-api-token`, issuer email `m.hassani.de@gmail.com`). T10 reuses
  `letsencrypt-prod` directly — no new cert-manager setup needed, just the right
  annotation on the `Ingress`/`Certificate` object.
- **Storage class: only `local-path`** (Rancher's `local-path-provisioner`,
  `ReclaimPolicy: Delete`, `VolumeBindingMode: WaitForFirstConsumer`). This is
  **`ReadWriteOnce`-only** — confirms the file-storage decision below wasn't just a
  preference, `ReadWriteMany` genuinely isn't available on this cluster today
  without adding a new storage provisioner (NFS/Longhorn/etc.), which nobody chose
  to do.
- **The container registry is itself hosted on this cluster.**
  `registry.mohsen-hassani.com` (namespace `mohsen-hassani-registry`) is Gitea's
  built-in container registry — pod `registry-app-*`, `Service` `registry-svc:3000`,
  `Ingress` `registry-ingress` (class `traefik`, host
  `registry.mohsen-hassani.com`). Auth for `docker login`/`imagePullSecrets` is a
  **Gitea username + access token**, not a separate registry-specific credential
  system. CI pushes with a token that has `write:package` scope (GitHub secrets
  `REGISTRY_USERNAME`/`REGISTRY_PASSWORD`).
- **`disp` and `disp-web` are publicly pullable** (verified 2026-10-04 against
  `:713cd73ac93b`, the first images CI pushed): anonymous pull tokens are issued,
  manifest GETs with them return 200, and a `docker pull` with an empty Docker config
  succeeds. Nobody set this per package. Gitea packages **inherit their owner's
  visibility**, and the Gitea user `mohsen_hassani` is `public` (Gitea 1.27.3). Images
  are single-arch `linux/amd64`, matching the only node (`falken`, amd64). This is why
  T2 is skipped.
- **A `mohsen-hassani-logging` namespace also exists** (some logging stack, likely
  Loki/Grafana-shaped) — unrelated to `disp`, noted only so it isn't mistaken for
  something this migration owns.
- **Neither Argo CD nor Flux is installed yet** (checked: no matching namespace or
  CRDs) — whichever this migration picks for T12, it starts from a clean slate on
  this cluster.
- **CNPG (CloudNativePG) operator is already installed** (re-verified 2026-10-05;
  the 2026-09-01 snapshot that said otherwise was wrong or has since changed).
  `Deployment` `cnpg-controller-manager` in namespace `cnpg-system`, image
  `ghcr.io/cloudnative-pg/cloudnative-pg:1.24.0`, CRDs dated 2026-09-01. It is
  **shared cluster infrastructure installed for another app**: `site-my-website`
  runs a 1-instance `Cluster` (`my-website-db`, stock `postgresql:16.4` image) on
  it. T3 therefore only defines a `Cluster` against it. Don't upgrade or reconfigure
  the operator from this project. Being 1.24, it predates the `Database` CRD (1.25)
  and extension image volumes (1.27), which constrains how pgvector is provided,
  see T3.

---

## Locked-in decisions

Established in prior work this migration must stay consistent with — not up for
re-litigation inside a task unless something below turns out to be wrong.

- **Scope: single production environment, expressed as one Kustomize overlay.**
  `k8s/base/` holds every component; `k8s/overlays/prod/` is the only overlay and
  the actual `kubectl apply -k` entry point (`kubectl apply -k k8s/overlays/prod`),
  currently just `resources: [../../base]` with no patches. (Revised 2026-09-01 —
  an earlier draft of this decision avoided overlays entirely and treated a second
  namespace as the extension point instead; reversed once `base/` was kept
  specifically *because* it pairs with overlays, per that discussion. A
  hypothetical second environment's extension point is now a sibling
  `overlays/staging/` referencing the same `../../base`, the idiomatic Kustomize
  way, not a second namespace with duplicated files.)
- **Namespace:** `mohsen-hassani-disp`, labeled `domain: mohsen-hassani.com`.
- **Registry:** `registry.mohsen-hassani.com/mohsen_hassani/{disp,disp-web}` (moved
  off GHCR — see `docker-compose.prod.yml`, `.github/workflows/deploy.yml`). Images:
  `disp` = root `Dockerfile` (serves both `api` and `worker`, same image, different
  `command:`), `disp-web` = `clients/web/Dockerfile` (nginx serving the built PWA).
- **Image tags:** GitHub Actions tags every build with the first 12 chars of the
  commit SHA, plus a floating `:latest`. **Kubernetes Deployments must reference the
  immutable sha tag, never `:latest`** — unlike the compose path, nothing here
  substitutes a tag at deploy time by default, so a manifest pinned to `:latest`
  would silently drift. (This is a deviation worth naming explicitly: neither
  bank-of-anthos nor sourcegraph's manifests hardcode a tag directly for the same
  reason — real tag substitution belongs in T12.)
- **Config/Secret split convention** (established in `k8s/configs/api.yaml` before
  the directory was reset, being carried forward into the new layout):
  ConfigMap for non-secret values, `Secret` (`stringData:`) for credential material,
  wired into containers via `envFrom`. Real `Secret` manifests are **never**
  committed — only `*.secret.example.yaml` templates are, mirroring the existing
  `.env`/`.env.example` split. `.gitignore` already has the pattern
  `k8s/secrets/*` / `!k8s/secrets/*.example.yaml`; T0 confirms it still matches the
  new file locations.
- **Required env vars** (from `src/disp/core/config.py`'s `Settings`, `env_prefix="DISP_"`):
  `DATABASE_URL`, `JWT_SECRET`, `SETTINGS_KEY`, `BASE_URL` have no default and are
  required — a pod missing any of these crash-loops on a pydantic `ValidationError`
  at startup, not a graceful failure. `SecretStr`-typed fields (must live in the
  `Secret`, not the `ConfigMap`): `jwt_secret`, `settings_key`, and — only if those
  features get turned on — `files_s3_access_key_id`, `files_s3_secret_access_key`,
  `llm_api_key`, `embedding_api_key`, `translation_api_key`. `database_url` is typed
  `str`, not `SecretStr`, but contains an inline password and must be treated as
  secret anyway.
- **`DISP_ENV=production` requires `DISP_COOKIE_SECURE=true`** — enforced by a
  `model_validator` in `config.py`; the two env vars must always move together or
  the pod fails at startup.
- **File storage is Cloudflare R2 (`DISP_FILES_BACKEND=s3`), not a shared volume.**
  Resolved via the D2 discussion: the cluster's only storage class (`local-path`) is
  `ReadWriteOnce`-only anyway (see Cluster facts), so a volume shared between `api`
  and `worker` the way `docker-compose.yml`'s `media:` volume works today was never
  actually viable here — `core.sweep_files` runs in the worker process (per
  `CLAUDE.md`'s `core.files` gotchas) and needs to see the same files the API wrote,
  and R2 (an object store both processes talk to over the network) satisfies that
  without either process needing a mounted volume at all. `DISP_FILES_ROOT` and any
  volume mount are **not** part of `api`/`worker`'s manifests — see T8 for the R2
  config vars that replace them.
- **Migrations stay a manual, explicit step — not an automatic pre-deploy hook.**
  `docs/operations.md`'s "SSH deploy" section and `CLAUDE.md` are explicit that
  `scripts/deploy.sh` "never runs migrations... so a deploy can never silently apply
  one." T5 builds a migration `Job` manifest, but it is applied by hand
  (`kubectl apply -f` / `kubectl create -f`), never wired into the same rollout as
  T6/T7. Preserving this is a deliberate carry-over, not an oversight.
- **Health endpoints, from existing `docker-compose.yml` healthchecks** (reuse
  exactly, don't invent new ones): `api` liveness → `GET /health/live`, `api`
  readiness → `GET /health` (this is the endpoint `scripts/deploy.sh` already polls
  post-deploy). `web` → `GET /` on port `8080` (non-root nginx, per
  `clients/web/Dockerfile`'s own `HEALTHCHECK`). `worker` has **no** existing
  healthcheck in `docker-compose.yml` — T7 matches that (no probe) rather than
  inventing one; Procrastinate exposes no HTTP endpoint to probe against today.

---

## Open decisions

D1–D4 were resolved in the 2026-09-01 discussion and are folded into "Cluster
facts"/"Locked-in decisions" above — kept here as a resolution log so the
reasoning isn't lost:

- **D1 (Postgres) → resolved: [CloudNativePG](https://cloudnative-pg.io/) (CNPG)**,
  not a hand-rolled `StatefulSet`. See T3 — this is a deviation from both reference
  repos, which hand-roll their own `StatefulSet`s; CNPG is a dedicated Postgres
  operator (handles failover/backups/replica management), a more production-grade
  answer than either research repo demonstrated. Not yet installed on the cluster.
- **D2 (file storage) → resolved: S3-compatible backend**, further narrowed to
  **Cloudflare R2** specifically (not in-cluster MinIO or Hetzner Object Storage —
  the user already has Cloudflare for DNS, see the cert-manager DNS-01 solver in
  Cluster facts). See T8. Also independently confirmed necessary, not just
  preferred: the cluster's only storage class is `ReadWriteOnce`-only.
- **D3 (ingress/TLS) → resolved by inspecting the live cluster**, not by asking:
  Traefik (`IngressClass: traefik`), cert-manager already live with
  `letsencrypt-prod` ready to use. Hostname: **`disp.mohsen-hassani.com`**, DNS
  record already exists and already points at this Hetzner server — meaning T10's
  `Ingress`, once applied, starts actually serving public requests for that host
  immediately. Sequence T10 after T6/T7/T9/T5 are genuinely ready, not before.
- **D4 (`pgweb`) → resolved: dropped.** T11 is marked Dropped on the status board,
  not deleted from this document — `kubectl port-forward` replaces it.

One decision remains open:

- **D5 (blocks T12): which GitOps controller — Argo CD or Flux?** Resolved in
  principle (GitOps over a `kubectl`-from-CI step, per the 2026-09-01 discussion —
  decouples deploy credentials from GitHub Actions entirely), but the specific tool
  is still unpicked. Neither is installed on the cluster yet (verified — clean
  slate either way). Revisit when T12 is actually reached; nothing before it depends
  on this choice.

---

## Task detail

### T0 — Directory layout & naming convention

**Where this stands today:** `k8s/` is empty except this file.

**What "done" looks like:** every subsequent task has an unambiguous place to put
its files, `.gitignore` correctly protects real secret values under the new
layout, and there's a single, unambiguous `kubectl apply -k` entry point
(`k8s/overlays/prod`) rather than applying `base/` directly.

**Why this task exists:** picking the layout once up front avoids reshuffling paths
mid-migration, and the layout choice directly shapes how every later task is
written.

**Pattern to follow:** `sourcegraph/deploy-sourcegraph-k8s`'s `base/sourcegraph/<name>/`
per-component directories, each holding `<name>.<Kind>.yaml` files plus its own
`kustomization.yaml` — e.g. `base/sourcegraph/pgsql/{pgsql.ConfigMap.yaml,
pgsql.PersistentVolumeClaim.yaml, pgsql.Service.yaml, pgsql.StatefulSet.yaml,
kustomization.yaml}`. Chosen over Online Boutique's single flat manifest file
because `disp` has enough distinct components (`postgres`, `api`, `worker`, `web`,
migration `Job`) that one file per kind stays more navigable than one giant file,
without needing sourcegraph's full monitoring/RBAC scope. **Revised 2026-09-01:**
also keeping sourcegraph's `base/`+overlay pairing itself (not just its per-component
shape) — see the "Scope" bullet in Locked-in decisions for why `overlays/prod/` was
added rather than applying `base/` directly.

**Layout for this repo:**
```
k8s/
  roadmap.md
  base/
    kustomization.yaml            # base aggregator — references every component below
    namespace/
      namespace.Namespace.yaml    # see T1
      kustomization.yaml
    postgres/                     # see T3 — a CNPG `Cluster` resource, not a
      postgres.Cluster.yaml       # hand-rolled StatefulSet; CNPG generates its
      kustomization.yaml          # own Service/Secret, nothing else lives here
    api/                          # see T4, T6 — api-configs/api-secrets live here,
      api.ConfigMap.yaml          # worker (T7) references the same two objects
      api.Deployment.yaml         # rather than duplicating them
      api.Service.yaml
      kustomization.yaml
    worker/                       # see T7
      worker.Deployment.yaml
      kustomization.yaml
    migration-job/                # see T5
      migration.Job.yaml
      kustomization.yaml
    web/                          # see T9
      web.Deployment.yaml
      web.Service.yaml
      kustomization.yaml
    ingress/                      # see T10
      ingress.yaml
      kustomization.yaml
  overlays/
    prod/
      kustomization.yaml          # THE apply entry point: kubectl apply -k k8s/overlays/prod
  secrets/
    api.secret.example.yaml       # committed template — see T4
    api.secret.yaml                # gitignored — real values
```
(`registry-credentials.secret{,.example}.yaml` were planned here for T2. Dropped
2026-10-04 when T2 was skipped because the images are public.)

**What we're changing from the source, and why:** dropping sourcegraph's
`examples/<target>/`-as-resource-sizing-and-cloud-target-matrix (its overlay layer
does far more than this project needs — storage class per cloud provider, t-shirt
resource sizing) down to a single, mostly-empty `overlays/prod/`; and dropping its
`base/monitoring/`, per-service RBAC, and legacy-migration directories entirely
(disproportionate for a solo deploy). Also flattening `secrets/` to the top level
rather than nesting per-component, since only `api`+`worker` (sharing one Secret)
currently need real secret material. Revisit if that count grows.

**Files to create/modify:** the directory skeleton above (empty `kustomization.yaml`
stubs are fine at this stage); update `.gitignore`'s existing
`k8s/secrets/*` / `!k8s/secrets/*.example.yaml` pair if the final paths above shift
during implementation.

---

### T1 — Namespace

**Where this stands today:** Not created (the previous `k8s/namespace.yaml` was
removed when the directory was reset). Content is known from before, though —
reproduced below.

**What "done" looks like:** `kubectl apply -k k8s/overlays/prod` (once T3+ exist —
right now it happens to only render this one `Namespace` object, since it's the
only base component that exists yet) creates the namespace; every other
component's manifests reference it in `metadata.namespace`.

**Why this task exists:** every namespaced object in every later task needs this to
exist first.

**Pattern to follow:** a plain `Namespace` object, no controller involved — this one
doesn't need a reference repo, it's the same regardless of source.

**Content:**
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: mohsen-hassani-disp
  labels:
    domain: mohsen-hassani.com
```

**What we're changing from the source, and why:** n/a.

**Files to create/modify:** `k8s/base/namespace/namespace.Namespace.yaml` +
`k8s/base/namespace/kustomization.yaml` referencing it.

---

### T2 — Registry pull credentials — **Skipped**

**Resolution (2026-10-04): skipped, because the images are publicly pullable.**
Once CI had pushed real images, an anonymous pull succeeded (see the registry
bullets in Cluster facts). No `Secret` is created, and no manifest from T5 onward
carries `imagePullSecrets`. Why public is acceptable here:
- **No new exposure.** The GitHub repo `mohsen-hassani/disp` is itself public, so the
  `disp` image holds no code that isn't already readable there. `disp-web` is the PWA
  the site serves to every visitor anyway.
- **No secrets in either image.** Both Dockerfiles `COPY` explicit paths only (`src`,
  `pyproject.toml`/`uv.lock`, `alembic.ini`; the built `dist/` + nginx config), and
  every credential reaches the containers as an env var at runtime (T4).

**The catch, and when to revisit:** public access is not a per-package setting. It
**follows the Gitea user's visibility.** If the `mohsen_hassani` profile is ever set
to *limited* or *private*, every pod pulling these images fails with
`ImagePullBackOff`, and nothing in this repo will have changed. If that happens, or
the GitHub repo goes private, implement the plan below. The quickest way to keep
the images private without hiding the whole profile is a private Gitea organization,
which changes the image paths to `registry.mohsen-hassani.com/<org>/…`, so
`deploy.yml` changes too. Use a `read:package`-only token for the cluster, never
CI's write token.

The original plan follows unchanged, for that case.

**Where this stands today:** Not created. This is a **new requirement that didn't
exist before** — the `docker compose pull` path only needed the *host* logged in
(`docs/operations.md` step 5, added when the registry moved off GHCR); Kubernetes
needs each pod's `imagePullSecrets` to carry credentials for
`registry.mohsen-hassani.com`, since the compose host's own `docker login` state
isn't visible to the cluster's container runtime.

**What "done" looks like:** a `kubernetes.io/dockerconfigjson` `Secret` exists in
`mohsen-hassani-disp`, and every Deployment/Job that pulls a `disp`/`disp-web` image
references it via `imagePullSecrets`.

**Why this task exists:** without it, every pod that tries to pull a private image
from `registry.mohsen-hassani.com` fails with `ImagePullBackOff` — this blocks T6,
T7, T9, and T5 (the migration Job also pulls the `disp` image) unless the registry
is made public for these two repositories instead (worth asking whether
`registry.mohsen-hassani.com` even supports per-repo public/private toggling before
building this — if it does and `disp`/`disp-web` are set public, this task can be
skipped entirely, mirroring how GHCR packages can be public).

**Pattern to follow:** standard k8s docker-registry secret —
`kubectl create secret docker-registry registry-credentials --docker-server=registry.mohsen-hassani.com --docker-username=... --docker-password=... -n mohsen-hassani-disp --dry-run=client -o yaml` to generate the manifest shape, then treat it exactly like `api.secret.yaml`: real file gitignored, an `.example` template committed.

**What we're changing from the source, and why:** neither reference repo needed
this, since both assume a public registry (GHCR public packages / Google Artifact
Registry with cluster-level pull permissions) — this task exists purely because of
the earlier decision to self-host the registry at `registry.mohsen-hassani.com`.

**Files to create/modify:**
`k8s/secrets/registry-credentials.secret.example.yaml` (committed),
`k8s/secrets/registry-credentials.secret.yaml` (gitignored, real credentials).
Every Deployment/Job manifest from T5 onward needs
`spec.template.spec.imagePullSecrets: [{name: registry-credentials}]` added.

---

### T3 — Postgres via CloudNativePG (CNPG)

**Resolution (2026-10-05) — read this first; it supersedes parts of the original
plan below:**
- **Part 1 (install the operator) is moot.** It is already installed and shared with
  `site-my-website` (see Cluster facts). T3 is only the `Cluster` resource.
- **pgvector image: third-party, pinned by digest.** The stock CNPG image does not
  include pgvector and the `learning` migration needs it (M19 §7). The operator (1.24)
  is too old for extension image volumes, and upgrading it would touch another app's
  infrastructure, so the options were "build our own image in CI" or "use someone
  else's". Decision: **`ghcr.io/tensorchord/cloudnative-vectorchord:16.15-1.1.1`**,
  pinned as `@sha256:f5a17fa05faf25e81304ee95e9f920d8ae077ac4a4ef0a1251e09c7197cbb236`
  (multi-arch index digest). TensorChord builds it on CNPG's own `postgres-containers`
  base, for CNPG. Verified 2026-10-05 by running the image locally: PG 16, **pgvector
  0.8.6**, runs as uid 26 (CNPG's default, so no `postgresUID` override), has
  `linux/amd64` (the node is amd64). The image also ships VectorChord (`vchord`),
  which we **do not** enable: no `shared_preload_libraries`, no `CREATE EXTENSION
  vchord`. Tradeoff accepted: the database image depends on a third party's tag
  cadence and supply chain. The digest pin stops silent tag moves, and the escape
  hatch is the rejected alternative (our own `FROM ghcr.io/cloudnative-pg/postgresql:16`
  + `apt install postgresql-16-pgvector`, a third build step in `deploy.yml`). Because
  it is the same Postgres 16 data format, switching the `imageName` later is a rolling
  image update, not a dump/restore (cf. `docs/operations.md`, the M19 image swap).
- **`vector` must be created by the superuser at bootstrap.** `vector` is *not* a
  trusted extension (verified: no `trusted = true` in `vector.control`), so the
  `learning` migration's `CREATE EXTENSION IF NOT EXISTS vector`, run as the
  unprivileged `disp_user`, would fail. The `Cluster` therefore runs
  `bootstrap.initdb.postInitApplicationSQL: [CREATE EXTENSION IF NOT EXISTS vector]`
  (runs as the superuser in the app database), after which the migration's statement
  is a no-op. (`pgcrypto`, which core's migration creates, is trusted, so it needs
  nothing.) **This hook only runs when the cluster is first initialised.** On an
  already-initialised cluster, changing it does nothing.
- **`Cluster` shape:** name `postgres`, namespace `mohsen-hassani-disp`; `instances:
  1`; database `disp_db`, owner `disp_user` (same names as `docker-compose.yml`);
  `storage` 10Gi on `local-path` (which has `ALLOWVOLUMEEXPANSION: false`, so the size
  is fixed at creation); `enableSuperuserAccess: false`; `resources` requests/limits
  set (T13 checklist).
- **What T4 inherits.** CNPG generates Secret **`postgres-app`**
  (`kubernetes.io/basic-auth`: `username`, `password`, `host`, `port`, `dbname`,
  `uri`, `jdbc-uri`, ...) and Services `postgres-rw` / `-ro` / `-r`. Use
  **`postgres-rw`** (the primary). Its `uri` key is `postgresql://…`, but
  `DISP_DATABASE_URL` needs the `postgresql+asyncpg://` scheme, so T4 composes the URL
  from `username`/`password`/`host`/`dbname` rather than copying `uri`. CNPG's TLS is
  on server-side by default. Confirm in T4 whether asyncpg connects without extra
  `ssl` parameters (CNPG doesn't force it).
- **Verified live (2026-10-05, after the operator applied it):** `Cluster` "in healthy
  state", pod `postgres-1` running the digest-pinned image, PVC `postgres-1` 10Gi
  `Bound` on `local-path`; Services `postgres-rw`/`-ro`/`-r` and Secrets
  `postgres-app`/`-ca`/`-replication`/`-server` exist. `postgres-app` keys are exactly:
  `dbname` (`disp_db`), `host` (`postgres-rw`), `port` (`5432`), `username`
  (`disp_user`), `user`, `password`, `uri`, `jdbc-uri`, `pgpass`. In `disp_db`:
  PostgreSQL 16.15, extensions `plpgsql` + `vector` 0.8.6 (so the bootstrap hook ran),
  and `disp_user` is not a superuser. Not yet exercised: an actual `learning`
  migration against it (T5).
- **Not done here, flagged for T13:** no backups. CNPG's scheduled backups to an
  object store (R2 would fit, see T8) are the main thing the operator buys over a
  `StatefulSet`, and nothing is configured. Until then, the only copy of the data is
  one `local-path` volume on one node.

**Where this stands today (original text, partly superseded above):** `docker-compose.yml` runs Postgres as
`pgvector/pgvector:pg16` with a named volume (`pgdata:/var/lib/postgresql/data`) and
a `pg_isready` healthcheck. On the target k3s cluster, **no Postgres and no CNPG
operator exist yet at all** (verified directly — see Cluster facts). This task
starts from a completely clean slate, in two parts.

**What "done" looks like:**
1. The CNPG operator itself is installed cluster-wide (its own CRDs —
   `clusters.postgresql.cnpg.io` etc. — plus a controller `Deployment`, typically in
   a `cnpg-system` namespace). This is a one-time, cluster-level install, not
   something that belongs in `k8s/base/` alongside `disp`'s own namespaced
   resources — install it via CNPG's official install manifest or Helm chart
   (check https://cloudnative-pg.io/documentation/ for the current recommended
   method before implementing; don't assume a specific version).
2. A `postgresql.cnpg.io/v1 Cluster` custom resource in `mohsen-hassani-disp`
   requests however many Postgres instances (1 is enough for this workload — CNPG
   supports HA replica sets, but a personal single-user app doesn't need that
   complexity) using an image with the `pgvector` extension (CNPG supports custom
   images — needs a pgvector-enabled image reference, check CNPG's docs for
   whether their default image already bundles it or a custom `imageName` is
   required), backed by `local-path` (the only storage class this cluster has — see
   Cluster facts; fine for a single-instance non-HA setup). CNPG auto-generates a
   connection-credentials `Secret` and a stable Service DNS name once the `Cluster`
   reconciles — **don't hand-write a `postgres.Secret.yaml`**, read the generated
   one's exact name/keys (`kubectl get cluster <name> -o yaml` after creating it)
   and reference those in T4's `DISP_DATABASE_URL` instead of inventing one.

**Why this task exists:** `disp` needs a Postgres 16 instance with the `pgvector`
extension available (see `docker-compose.yml`'s image choice).

**Pattern to follow:** **no direct match in the research repos** — both
`sourcegraph/deploy-sourcegraph-k8s` and `bank-of-anthos` hand-roll their own
`StatefulSet`+`PVC`+`Service`+`ConfigMap` for Postgres (see the now-superseded
version of this task, preserved in git history if the hand-rolled shape is ever
wanted for comparison). CNPG was chosen instead in the 2026-09-01 discussion — it's
a purpose-built Postgres operator, not a generic pattern either reference repo
demonstrated, so this task is written from CNPG's own documentation, not from the
research.

**What we're changing from the source, and why:** the entire approach is a
deliberate upgrade over both reference repos' Postgres pattern — CNPG handles
backup scheduling, failover, and minor-version upgrades in ways a hand-rolled
`StatefulSet` doesn't attempt. The tradeoff: one more piece of cluster-wide
infrastructure (the operator itself) to install and keep updated, versus a plain
`StatefulSet` that's simpler to reason about but does none of that for you.

**Files to create/modify:** CNPG operator install (cluster-scoped, method TBD at
implementation time — likely not tracked under `k8s/base/` at all, since it isn't
namespaced to `disp`); `k8s/base/postgres/{postgres.Cluster.yaml,
kustomization.yaml}` for the `Cluster` custom resource. No `postgres.Secret.yaml` —
see above, CNPG generates its own.

---

### T4 — `api`/`worker` ConfigMap + Secret

**Resolution (2026-10-05) — supersedes the file list and content below where they differ:**
- **Object names:** ConfigMap **`api-configs`**, Secret **`api-secrets`** (the names T6/T7
  reference). The ConfigMap is a plain object in `k8s/base/api/` (no `configMapGenerator`:
  a hash suffix would break the fixed `envFrom` names). The Secret is applied by hand from
  `k8s/secrets/` (outside the kustomize root, so `kubectl apply -k` never touches it).
- **R2 vars are NOT in T4's files; T8 adds them.** T8 owns that decision (bucket and account
  id don't exist yet) and committing placeholders risks a pod that boots against a fake
  endpoint. `Settings` refuses to boot without a bucket and both keys, so until T8 lands any
  pod loading `api-configs`/`api-secrets` fails loudly at startup, which is the designed
  behaviour (M18 §3), not a T4 bug.
- **Ordering consequence for T5, found while writing this:** Alembic itself only reads
  `DISP_DATABASE_URL` (`migrations/env.py`), but the Job's second step,
  `procrastinate --app=disp.core.scheduler.app schema --apply`, imports
  `disp.core.scheduler`, which calls `get_settings()` at import time, so it needs the full
  validated `Settings`, R2 included. **T8 must be done before T5 is applied.**
- **`DISP_DATABASE_URL` is copied, not composed at runtime.** Per the original plan below:
  the gitignored `api.secret.yaml` holds
  `postgresql+asyncpg://disp_user:<password>@postgres-rw:5432/disp_db`, with user, password,
  host and dbname taken from T3's `postgres-app` Secret. CNPG does not rotate that password
  by itself. If it is ever changed, `api.secret.yaml` must be updated and re-applied, and
  `api`/`worker` restarted. (The alternative, `secretKeyRef` + `$(VAR)` interpolation in each
  pod's `env`, avoids the copy but breaks the single-`envFrom` convention and must be repeated
  in T5/T6/T7. Not chosen.)
- **Validated, not applied (2026-10-05):** `kubectl apply -k k8s/overlays/prod
  --dry-run=server` and `kubectl apply -f k8s/secrets/api.secret.yaml --dry-run=server`
  both accepted. The real values were also loaded through the actual `Settings` class
  (with dummy R2 values) and pass every validator; without R2 it refuses to boot.
  To apply: `kubectl apply -k k8s/overlays/prod` (ConfigMap) and
  `kubectl apply -f k8s/secrets/api.secret.yaml` (Secret). The Secret file was generated
  locally (JWT secret and Fernet key freshly generated, DB password read from
  `postgres-app`) and is gitignored. Losing it means regenerating, which invalidates
  existing sessions/encrypted settings, so back it up outside the repo.
- **TLS:** the URL carries no `ssl` parameter. asyncpg's default (`prefer`) negotiates TLS
  with CNPG's server cert without verifying it. Not yet exercised against the live database;
  T5's Job is the first real connection.

**Where this stands today (original text):** A version of this existed at `k8s/configs/api.yaml`
and `k8s/secrets/api.secret{,.example}.yaml` before the directory reset. That
earlier work already fixed several real bugs (unquoted YAML booleans, secret
material sitting in a `ConfigMap`, a missing required `DISP_JWT_SECRET`) — this task
reproduces that fixed state inside the new T0 layout. (An earlier draft of this
roadmap also added `DISP_FILES_ROOT` here as a "missed field" — that's since been
superseded by the R2 decision; see T8, it doesn't belong in this ConfigMap at all
now.)

**What "done" looks like:** `k8s/base/api/api.ConfigMap.yaml` (non-secret) and
`k8s/secrets/api.secret.yaml` (real values, gitignored) together supply every
required env var from `config.py`'s `Settings`, correctly split by sensitivity, and
`kubectl apply` doesn't reject either object.

**Why this task exists:** `api` and `worker` (T6, T7) both load `Settings` from the
same env vars at process startup (`env_prefix="DISP_"`) and crash immediately if a
required one is missing or malformed — this has to be right before either
Deployment can come up.

**Pattern to follow:** bank-of-anthos's `userservice.yaml` layered `envFrom` (a
shared ConfigMap + a service-specific one) — here, one `ConfigMap` + one `Secret`,
both referenced by **both** the `api` and `worker` Deployments' `envFrom`, since
they're the same image running the same `Settings` class with the same required
vars. No separate `worker.ConfigMap.yaml` needed.

**Content (`ConfigMap`, non-secret):**
```yaml
DISP_BASE_URL: https://disp.mohsen-hassani.com   # confirmed in the 2026-09-01 discussion; DNS already points here — see T10 sequencing note
DISP_ENV: production
DISP_COOKIE_SECURE: "true"                       # must move with DISP_ENV, see locked-in decisions
DISP_RATE_LIMIT_ENABLED: "true"
```
Plus the R2 non-secret vars from T8 (`DISP_FILES_BACKEND`, `DISP_FILES_S3_BUCKET`,
`DISP_FILES_S3_ENDPOINT_URL`, `DISP_FILES_S3_REGION`) — listed in full there rather
than duplicated here, since T8 owns that decision.

**Content (`Secret`, `stringData:`, real values only in the gitignored file):**
```yaml
DISP_DATABASE_URL: postgresql+asyncpg://<user>:<password>@<host>:5432/<db>   # DO NOT hand-write — copy user/password/host from the Secret CNPG's Cluster (T3) generates, once T3 is applied
DISP_JWT_SECRET: <generate: python -c "import secrets; print(secrets.token_urlsafe(48))">
DISP_SETTINGS_KEY: <generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
```
Plus the R2 secret vars from T8 (`DISP_FILES_S3_ACCESS_KEY_ID`,
`DISP_FILES_S3_SECRET_ACCESS_KEY`).

**What we're changing from the source, and why:** same as noted in T3 for
bank-of-anthos's secrets-in-ConfigMap anti-pattern — not repeating it here either.
Reusing the exact `.env.example` key-generation commands already documented at the
repo root rather than inventing new instructions, so there's one canonical way to
generate each secret across both the compose and k8s deploy paths.

**Files to create/modify:** `k8s/base/api/api.ConfigMap.yaml`,
`k8s/secrets/api.secret.example.yaml` (committed placeholders),
`k8s/secrets/api.secret.yaml` (gitignored real values).

---

### T5 — Migration Job

**Where this stands today:** Not created. Today, migrations run manually via
`./dev migrate [branch]` (wraps `alembic upgrade head`) against whatever
`DISP_DATABASE_URL` the operator's shell has — no k8s equivalent exists yet.

**What "done" looks like:** a `batch/v1 Job` manifest, using the same `disp` image
and the same `api-configs`/`api-secrets` env, that runs Alembic migrations for
**every** branch this repo ships, then applies the Procrastinate schema. Applying it
(`kubectl apply -f` / `kubectl create -f`, then `kubectl wait
--for=condition=complete`) is a **manual step an operator runs on purpose**, never
automatic.

**Found 2026-10-04 while smoke-testing the image** (throwaway Postgres + MinIO, the
image's own console scripts). An earlier draft of this task missed both points:
- **There are four branches, not three: `core`, `notes`, `plants`, `learning`.**
  Discover them the way `./dev migrate` does: `core` first, then every
  `src/disp/modules/*/` that has a `migrations/versions/` directory, inside the
  image at `/app/src/disp/modules/`. Don't hardcode the list. A missed branch
  doesn't crash the pod. It shows up later as "relation does not exist" errors on
  that module's endpoints. (`docker-compose.e2e.yml` hardcodes all four, which is
  right today and goes stale the same way.)
- **The Job must also run `procrastinate --app=disp.core.scheduler.app schema
  --apply`** after Alembic, or `worker` (T7) has no job tables to poll. That command
  is **not idempotent** (it fails with "already exists" on a second run), so guard
  it the way `./dev migrate` does: apply only if `to_regclass('public.procrastinate_jobs')`
  is null. Without the guard, every migration run after the first fails.
- Verified working inside the image, in this order: `alembic --name=<branch>
  upgrade head` for each branch, then the Procrastinate schema.

**Why this task exists:** T6/T7's pods need a schema that's already up to date when
they start — `disp` has no runtime auto-migration, by design (see locked-in
decisions above).

**Pattern to follow:** `sourcegraph/deploy-sourcegraph-k8s`'s
`components/utils/migrator/resources/migrator.Job.yaml` — `restartPolicy:
OnFailure`, `backoffLimit: 4`, `envFrom` pointing at the same config the app
services use, `args` invoking the migration command. Also worth the `pg_isready`
wait-loop pattern from bank-of-anthos's `init-db-job.yaml` if this Job might ever
run before T3's `StatefulSet` is fully ready — though since this Job is applied
manually and on-demand (never as part of an automatic rollout), an operator running
it will typically already know Postgres is up, so this may be unnecessary
belt-and-suspenders; decide at implementation time.

**What we're changing from the source, and why:** sourcegraph's migrator uses a
purpose-built dedicated migrator image; `disp` doesn't have one, so this Job uses
the regular `disp` image with `command: ["alembic", ...]` (or whatever `./dev
migrate`'s underlying invocation resolves to) instead — simpler, one fewer image to
build and push, appropriate since `disp`'s migration step is a thin Alembic
wrapper, not a separate service.

**Files to create/modify:** `k8s/base/migration-job/{migration.Job.yaml,
kustomization.yaml}`. **Not** included in the root `kustomization.yaml`'s default
apply set if that would make it run automatically — keep it a component the
operator applies explicitly (e.g. via its own `kubectl apply -f
k8s/base/migration-job/migration.Job.yaml`, not folded into a single "apply
everything" command).

---

### T6 — `api` Deployment + Service

**Where this stands today:** Not created.

**What "done" looks like:** a `Deployment` running the `disp` image
(`command`/default `CMD` from the root `Dockerfile`: `uvicorn disp.main:app ...`),
env from T4's `ConfigMap`+`Secret` (which now includes the R2 file-storage vars —
no volume mount needed, see T8), no `imagePullSecrets` (T2 skipped, images are public), correct probes, resource
requests/limits, and a hardened `securityContext`; plus a `ClusterIP` `Service` in
front of it for T10's `Ingress` to target.

**Why this task exists:** this is the actual application.

**Pattern to follow:** bank-of-anthos's `userservice.yaml` almost directly —
`envFrom: [configMapRef: api-configs, secretRef: api-secrets]`, `readinessProbe`
(`GET /health`) and `livenessProbe` (`GET /health/live`, port `8000`, per the
locked-in decision above), `resources.requests`/`limits`, and
`securityContext: {runAsNonRoot: true, readOnlyRootFilesystem: true, capabilities:
{drop: [all]}}` — the root `Dockerfile` already creates and runs as a non-root
`app` user (uid 10001), so `runAsNonRoot` costs nothing extra. Mount an `emptyDir`
at `/tmp`, as bank-of-anthos does, to give the process scratch space under the
read-only root filesystem.

**Verified 2026-10-04:** the `disp` image ran as `api` with `DISP_ENV=production`
under `docker run --read-only --tmpfs /tmp --cap-drop ALL` (the local equivalent of
`readOnlyRootFilesystem: true` + an `emptyDir` at `/tmp` + `drop: [ALL]`). Both
`/health` and `/health/live` returned 200, with the database ok. It was **not**
tested without the `/tmp` mount, so keep the `emptyDir`. (`/data/files` no longer
exists since R2, see T8.)

**What we're changing from the source, and why:** image reference points at
`registry.mohsen-hassani.com/mohsen_hassani/disp:<sha-tag>` per the locked-in
decision (never `:latest`). Earlier drafts of this task assumed a shared volume
mount here (see T8's history) — resolved to R2 instead, so this manifest ends up
closer to bank-of-anthos's `userservice.yaml` than originally expected, with no
extra volume beyond whatever `emptyDir` scratch space `readOnlyRootFilesystem`
needs.

**Files to create/modify:** `k8s/base/api/{api.Deployment.yaml,
api.Service.yaml, kustomization.yaml}`.

---

### T7 — `worker` Deployment

**Where this stands today:** Not created. `docker-compose.yml` runs this as the
same `disp` image with `command: ["python", "-m", "disp.worker"]`, no exposed port.

**What "done" looks like:** a `Deployment` (no `Service` needed — nothing calls this
process over the network) with the same env (`api-configs`/`api-secrets`, including
T8's R2 vars), and no `imagePullSecrets` (T2 skipped). No liveness/readiness probe, matching
current `docker-compose.yml` behavior (see locked-in decisions). No volume mount —
R2 access is over the network, identical from any pod, so `api` and `worker` no
longer need to be scheduled with access to the same filesystem the way a shared PVC
would have required. Use the same `securityContext` as T6, including
`readOnlyRootFilesystem` and an `emptyDir` at `/tmp`. **Verified 2026-10-04:**
`python -m disp.worker` ran under `--read-only --tmpfs /tmp --cap-drop ALL`,
registered all four periodic tasks (`core.sweep_files`, `notes.purge_deleted`,
`plants.daily_check`, `learning.daily_nudge`), and stayed up with no restarts.

**Known limit of "no probe" (T13 to decide):** Kubernetes restarts a *crashed*
worker, but it won't notice one that is *hung* and still running. The signal for
that already exists: `GET /health` reports `worker_last_seen`, the worker's last
check-in. It deliberately doesn't fail `api`'s readiness on it, which is right,
because a stalled worker shouldn't take the API out of service. Alert on that field
if hangs ever become a real concern. Don't reuse `/health` as a worker probe.

**Why this task exists:** runs `core.sweep_files` and any other Procrastinate-queued
background jobs against the same R2 bucket `api` writes to.

**Pattern to follow:** `sourcegraph/deploy-sourcegraph-k8s`'s
`base/sourcegraph/precise-code-intel/worker.Deployment.yaml` — a background worker
as its own `Deployment`, sharing config with a sibling service via the same
`envFrom` ConfigMap/Secret refs rather than duplicating them. This is the closest
published example found of exactly `disp`'s `api`/`worker` split.

**What we're changing from the source, and why:** nothing structurally novel now
that R2 removed the shared-volume requirement — this follows the sourcegraph
pattern directly, no deviation needed.

**Files to create/modify:** `k8s/base/worker/{worker.Deployment.yaml,
kustomization.yaml}`.

---

### T8 — File storage: Cloudflare R2

**Where this stands today:** `docker-compose.yml` mounts a single named volume
(`media:/data/files`) on both `api` and `worker` — trivial on a single Docker host,
since both containers run on the same machine and share the same volume driver. No
R2 bucket exists yet.

**What "done" looks like:** an R2 bucket created in the Cloudflare dashboard (or via
`wrangler`/Terraform if preferred — **not** something `kubectl` can do, this is a
Cloudflare-account-level action outside the cluster entirely), plus an R2 API
token (access key ID + secret access key) scoped to that bucket. Then, added to
T4's `ConfigMap`/`Secret`:
```yaml
# ConfigMap (non-secret)
DISP_FILES_BACKEND: s3
DISP_FILES_S3_BUCKET: <bucket name>
DISP_FILES_S3_ENDPOINT_URL: https://<cloudflare-account-id>.r2.cloudflarestorage.com
DISP_FILES_S3_REGION: auto        # matches config.py's own default for this field
```
```yaml
# Secret (stringData)
DISP_FILES_S3_ACCESS_KEY_ID: <R2 access key id>
DISP_FILES_S3_SECRET_ACCESS_KEY: <R2 secret access key>
```
`config.py`'s other S3 fields (`files_s3_force_path_style: bool = True`) already
default to values that work with R2 — confirm against Cloudflare's S3-compatibility
docs during implementation, but don't expect to need overrides. (Corrected
2026-10-05: this paragraph used to cite `files_s3_native_presign`, which no longer
exists in `Settings`; and `files_backend` is now `Literal["s3"]`, so setting
`DISP_FILES_BACKEND` is optional but harmless.) **T8 completes T4's objects and gates
T5:** see the T4 resolution. No `PersistentVolumeClaim`, no volume mount on T6/T7
at all.

**Why this task exists:** `disp`'s plant-photo uploads and any other `core.files`
object need to live somewhere both `api` (writes) and `worker` (sweeps/reads via
`core.sweep_files`) can reach — an object store both talk to over the network,
rather than a filesystem path both need mounted.

**Pattern to follow:** none from the research repos — see the resolution log under
D2. This is entirely a `config.py`-driven config change: `files_backend:
Literal["local", "s3"]` already supports this, so nothing here required touching
application code, only figuring out the right env vars.

**What we're changing from the source, and why:** n/a — no source pattern applies.

**Files to create/modify:** the R2 vars above folded into `k8s/base/api/api.ConfigMap.yaml`
and `k8s/secrets/api.secret{,.example}.yaml` from T4 — no new k8s objects, no new
directory.

---

### T9 — `web` Deployment + Service

**Where this stands today:** Not created. `docker-compose.yml` runs this as the
`disp-web` image (nginx, non-root, port `8080` internally).

**What "done" looks like:** a `Deployment` running
`registry.mohsen-hassani.com/mohsen_hassani/disp-web:<sha-tag>`, a `readinessProbe`/
`livenessProbe` against `GET / :8080` (matching `clients/web/Dockerfile`'s own
`HEALTHCHECK`), resource limits, and a `Service` for T10's `Ingress` to target. No
env vars needed — the built PWA talks to `/api` same-origin through the `Ingress`'s
own routing, not via any runtime config (see `CLAUDE.md`'s "Same-origin routing"
note — this is unchanged by the move to k8s, the same-origin requirement just needs
to be satisfied by the `Ingress` rules in T10 instead of Traefik's old
priority-routing labels).

**Why this task exists:** serves the actual frontend.

**Pattern to follow:** same container-spec hygiene as T6 (bank-of-anthos-style
probes/resources/`securityContext`) — `clients/web/Dockerfile` already runs as the
nginx image's built-in non-root `nginx` user, so `runAsNonRoot: true` is free here
too.

**`readOnlyRootFilesystem` needs an `emptyDir` at `/tmp`, or nginx won't start.**
Found 2026-10-04: under `docker run --read-only` the container exits immediately
with `mkdir() "/tmp/client_temp" failed (30: Read-only file system)`. This comes
from `clients/web/nginx.conf`, which moves the pid file (`pid /tmp/nginx.pid`) and
every temp path (`client_body_temp_path`, `proxy_temp_path`, `fastcgi_temp_path`)
into `/tmp`. That's deliberate, so nginx can run as non-root uid 101 (the defaults
under `/var/run` and `/var/cache` are root-owned), but `/tmp` must stay writable.
The log line `can not modify /etc/nginx/conf.d/default.conf` is harmless: the stock
image's IPv6 entrypoint helper skips itself on a read-only filesystem, and
`nginx.conf` sets its own `listen 8080`. Without `--read-only`, `GET /` and an SPA
deep link (`/plants`) both returned 200, running as uid 101.

**What we're changing from the source, and why:** nothing structurally novel here;
this is the most "by-the-book" component of the migration.

**Files to create/modify:** `k8s/base/web/{web.Deployment.yaml, web.Service.yaml,
kustomization.yaml}`.

---

### T10 — Ingress + TLS

**⚠️ Sequencing note:** the DNS record for `disp.mohsen-hassani.com` **already
exists and already points at this cluster** (confirmed in the 2026-09-01
discussion). That means the moment this `Ingress` is applied and cert-manager
issues a cert, it starts serving real public traffic on that hostname — there's no
"staging" grace period the way there would be if DNS still pointed elsewhere. Do
this task only after T5 (migrations applied), T6, T7, and T9 are confirmed actually
working — not as soon as their manifests merely exist.

**Where this stands today:** Traefik (external to this repo, in a separate `infra`
project, on the *other* machine) currently does path-priority routing for the
`docker-compose` deploy — `api` wins `/api`, `/health`, `/openapi.json`; `web` gets
everything else (`docker-compose.yml`'s `traefik.http.routers.*.priority` labels,
`M12`'s §24.4). This task reproduces that same split against the k3s cluster's
*own*, separate, already-installed Traefik instead.

**What "done" looks like:** one `networking.k8s.io/v1 Ingress` resource in
`mohsen-hassani-disp`:
```yaml
metadata:
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  ingressClassName: traefik
  tls:
    - hosts: [disp.mohsen-hassani.com]
      secretName: disp-tls   # cert-manager creates/manages this Secret automatically
  rules:
    - host: disp.mohsen-hassani.com
      http:
        paths:
          - path: /api
            pathType: Prefix
            backend: {service: {name: api, port: {number: 8000}}}
          - path: /health
            pathType: Prefix
            backend: {service: {name: api, port: {number: 8000}}}
          - path: /openapi.json
            pathType: Exact
            backend: {service: {name: api, port: {number: 8000}}}
          - path: /
            pathType: Prefix
            backend: {service: {name: web, port: {number: 8080}}}
```
Confirm at implementation time whether `networking.k8s.io/v1 Ingress`'s plain
`rules`/`paths` matching is expressive enough to reproduce the exact
priority-vs-prefix semantics `docker-compose.yml`'s Traefik labels use today, or
whether Traefik's own `IngressRoute` CRD (available since this is Traefik's
ingress controller, not a generic one) is worth using instead for closer parity —
both are valid with `ingressClassName: traefik`, `IngressRoute` just isn't portable
to a different ingress controller later.

**Why this task exists:** without it, neither service is reachable from outside the
cluster.

**Pattern to follow:** not sourced from the research repos — ingress/TLS is
inherently cluster-specific. Resolved instead by inspecting the live cluster (see
Cluster facts): reuse the existing `letsencrypt-prod` `ClusterIssuer` and `traefik`
`IngressClass` as-is, no new infrastructure.

**What we're changing from the source, and why:** n/a — no reference-repo pattern
applied here at all.

**Files to create/modify:** `k8s/base/ingress/{ingress.yaml, kustomization.yaml}`.

---

### T11 — pgweb — **Dropped**

**Resolution (D4, 2026-09-01):** not being ported to k8s. `docker-compose.yml` runs
`sosedoff/pgweb:latest` bound to `127.0.0.1:8081` only, reached via an SSH tunnel —
deliberately never public (`pgweb` has no built-in multi-user auth). The k8s
equivalent is `kubectl port-forward svc/<postgres-service-from-T3> 5432:5432` plus a
local `psql`/GUI client — one fewer standing component to run for a convenience
tool. No files, no further action for this task; kept in the roadmap only so the
decision and its reasoning aren't lost.

---

### T12 — Deploy trigger (CI → cluster) — GitOps

**Status detail:** blocked on **D5** — resolved to "GitOps controller" in principle
(2026-09-01 discussion), tool choice (Argo CD vs Flux) still open. Neither is
installed on the cluster yet.

**Where this stands today:** `.github/workflows/deploy.yml` builds+pushes both
images (sha tag + `:latest`). Its `deploy` job, which SSHes into the droplet and runs
`./scripts/deploy.sh <sha-tag>` (`docker compose pull && up -d`, polls `/health`,
rolls back to the previous tag on failure), was **disabled with `if: false` on
2026-10-04**. Pushes to `prod` now only publish images, with no compose deploy. The
job and `scripts/deploy.sh` are kept unchanged, so re-enabling is a one-line revert,
until T14 decides their fate.
None of this push-based, SSH-credential-bearing model carries over — the whole
point of picking GitOps here was to decouple GitHub Actions from holding cluster
credentials at all.

**What "done" looks like:** a GitOps controller (Argo CD or Flux — pick one when
this task is actually reached, evaluate current docs for each rather than assuming
today's feature set) installed in-cluster, watching this repo's `k8s/` directory
(or a subset of it — `migration-job/` should almost certainly stay excluded from
whatever the controller auto-syncs, per the locked-in "migrations stay manual"
decision), and some mechanism for the image tag to update on each build — most
GitOps setups pair with either the controller's own image-update automation (Argo
CD Image Updater / Flux's image-automation controller) or a CI step that commits
the new sha tag into the manifests, which the controller then picks up and applies.
Decide which of those two update mechanisms at implementation time.

**Why this task exists:** without this, every deploy after T0–T11 is manual
(`kubectl apply` by hand) — fine for the initial cutover, not sustainable long-term
given the existing automated pipeline this replaces.

**Pattern to follow:** neither reference repo's CI was in scope for the research
pass (both are install-manifest repos, not the CI pipelines of the products they
deploy) — this is genuinely new design work, not a lift from a source.

**What we're changing from the source, and why:** n/a.

**Files to create/modify:** `.github/workflows/deploy.yml` (likely trimmed
significantly — no more SSH/`docker compose` steps), `scripts/deploy.sh` and
`scripts/deploy-entrypoint.sh` (likely removed once T14 cuts over), plus whatever
the chosen GitOps controller needs (its own install manifest, an `Application`/
`Kustomization` CRD instance pointing at this repo).

---

### T13 — Production-readiness review

**Where this stands today:** N/A — capstone task, run once T1–T10 and T12 (T11 is
dropped, see above) are individually done.

**What "done" looks like:** a pass over every manifest checking, per the
bank-of-anthos checklist established across T6/T7/T9 (T3 follows CNPG's own
operator conventions instead, not this checklist — verify its `Cluster` resource
against CNPG's own production recommendations separately): every container has
`resources.requests`+`limits` set, every container that can be `runAsNonRoot` is,
`readOnlyRootFilesystem` is set wherever the app doesn't need runtime write access
outside its mounted volumes, every `Deployment` (except `worker`, by design) has
working liveness+readiness probes, and no `Secret` value or real domain/credential
has leaked into a committed `ConfigMap` or example file.

**Why this task exists:** individual tasks were written and likely implemented
somewhat independently; this is the check that the whole set is internally
consistent before real traffic touches it.

**Pattern to follow:** the checklist above, distilled from bank-of-anthos's
`userservice.yaml` and Online Boutique's `cartservice` container spec (both
verified via `gh api` to set the same five things: probes, resource limits, and
full `securityContext` hardening, with no exceptions across either repo's
services).

**What we're changing from the source, and why:** n/a — this task *is* the
enforcement of already-decided patterns, not a new one.

**Files to create/modify:** none new — edits to existing manifests as gaps are
found.

---

### T14 — Cutover from `docker-compose`

**Where this stands today:** `docker-compose.yml` + SSH deploy is the live
production path.

**What "done" looks like:** DNS/traffic actually points at the k8s `Ingress`
instead of the droplet's Traefik, and a decision has been made and executed on the
old path — either decommissioned (droplet torn down, `docker-compose*.yml` and
`scripts/deploy.sh` removed) or deliberately kept as a documented fallback for some
period.

**Why this task exists:** every prior task builds the new path in parallel; nothing
about T0–T13 actually retires the old one.

**Pattern to follow:** n/a — this is an operational cutover step, not a manifest
pattern.

**What we're changing from the source, and why:** n/a.

**Files to create/modify:** likely `docker-compose.yml`, `docker-compose.prod.yml`,
`scripts/deploy.sh`, `scripts/deploy-entrypoint.sh`, and `docs/operations.md`'s "SSH
deploy" section — but only once the k8s path has been running in production long
enough to trust it; don't delete the old path preemptively.
