# Todo

Known gaps that are deliberately not done yet. Each one came out of the Kubernetes
production-readiness audit (`k8s/roadmap.md`, T13, 2026-10-05) and is described there in more
detail. Tick an item when it is done and say where.

- [ ] **Database backups.** Nothing backs up Postgres. The only copy of the data is one
  `local-path` volume on one node, and `ReclaimPolicy: Delete` means losing the PVC loses the data.
  - Fix: `spec.backup.barmanObjectStore` on the CNPG `Cluster` (`k8s/base/postgres/postgres.Cluster.yaml`)
    plus a `ScheduledBackup`, writing to R2. The operator is shared and pinned at 1.24, which supports
    this in-tree. The Postgres image already ships `barman-cloud-backup`.
  - Needs a **separate R2 bucket and a token scoped to it**. Do not reuse the files bucket:
    `core.sweep_files` deletes every object there that has no database row, so WAL and backup objects
    would be swept.
  - Check at implementation: R2 checksum behaviour with the bundled boto3 (the usual fix is
    `AWS_REQUEST_CHECKSUM_CALCULATION=when_required`), and pick a retention (`30d` proposed).
  - Restore into a scratch cluster before trusting it.
  - Once backups exist, revisit the automatic migration initContainer (`k8s/roadmap.md`, T5).

- [ ] **Worker hang detection.** Kubernetes restarts a crashed worker but cannot tell that a hung one
  is stuck, and `worker` has no probe by design. `GET /health` reports `worker_last_seen`, but that is
  the time of the last *succeeded job*, not a heartbeat: it is null until a job first succeeds, and a
  quiet hour is normal.
  - Fix: alert on `worker_last_seen` going stale, for example from the existing logging stack
    (`mohsen-hassani-logging`). That is outside this repo.
  - Do not reuse `/health` as a worker probe. A stalled worker must not take `api` out of service.

- [ ] **NetworkPolicy.** There are none. Any pod in any namespace can reach `postgres-rw:5432`
  (a password is still required).
  - Fix: allow Postgres ingress only from `api`, `worker` and the `migrate` initContainer (all the
    `api`/`worker` pods) in this namespace, plus the CNPG operator in `cnpg-system`. Verify the operator's
    status checks still work before applying.
  - Optional for a one-node personal deployment.

- [ ] **CNPG PodDisruptionBudget.** CNPG created `postgres-primary` (`minAvailable: 1`, 0 disruptions
  allowed). With `instances: 1` this blocks a node drain until the pod is deleted by hand.
  - Fix options: add a second instance (also gives failover), or set
    `enablePDB: false` on the `Cluster` (the field exists in the installed CRD, checked 2026-10-05
    with `k explain cluster.spec.enablePDB`) and accept that a drain takes the database down.
  - Expected today on a single node; revisit if the node is ever drained for maintenance.
