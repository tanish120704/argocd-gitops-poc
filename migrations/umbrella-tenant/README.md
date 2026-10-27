# Umbrella tenant ownership migration

The existing `umbrella-tenant` Application becomes the parent of Foundation,
Core Platform, Product Services, and To Revisit. Its Application UID, tenant
namespace, Helm release name, tenant identity, and all 56 ConfigMaps are preserved.
No service Applications are created.

`argocd/umbrella-tenant.yaml` declares the parent explicitly to preserve its name.
`legacy-tenants/umbrella-tenant/values.yaml` is outside the normal ApplicationSet
`tenants/*/values.yaml` discovery, preventing a duplicate parent named
`tenant-umbrella-tenant`. It contains the original identity plus metadata
compatibility overrides. These keep all 12 Foundation services at their original
wave 0 and omit the six previously absent root configuration wave annotations.
Changing the legacy tenant to the new internal wave order is a separate change.

## Gates and execution

1. Save the live Application, namespace, and ConfigMap list as JSON. Extract the
   original inline Helm values to a YAML file. Retain immutable snapshots.
2. Run `tools/verify_umbrella_migration.py` before changing ownership. It requires
   exact equality between the old umbrella render, proposed group renders, and
   the live resources. It rejects duplicates, missing resources, data, labels,
   wave annotation changes, and other resource-field differences.
3. Commit the old Application with automated sync explicitly disabled and pruning
   disabled. Wait for the live spec to reflect that commit and any sync to finish.
4. Commit its new parent source with parent pruning disabled and `groupPrune:
   false`. Child Apps adopt the existing objects in group waves 0–3. Preserve
   release name `umbrella-tenant` and namespace `tenant-umbrella-tenant`.
5. Wait for all children to be Synced/Healthy. Verify every resource UID, payload,
   labels, non-tracking annotations, namespace UID, and existing Application UID.
   Verify each resource has its expected new group tracking owner.
6. Only after all checks pass, enable normal child pruning. Parent pruning stays
   disabled as it does for other tenants. Recheck final health and ownership.

Example verification (paths are local snapshots, never Kubernetes Secrets):

```sh
python tools/verify_umbrella_migration.py --charts ../helm-values-poc \
  --legacy-values /path/to/original-inline-values.yaml \
  --before /path/to/before-configmaps.json \
  --after /path/to/after-configmaps.json --report /path/to/audit.json
```

The comparison excludes Kubernetes server bookkeeping and exactly two annotations:
Argo CD's tracking ID and kubectl's last-applied configuration. These must change
when the resource owner changes. It does **not** ignore sync-wave annotations,
resource labels, or tenant data. Zero tenant configuration diff is therefore
separate from literal zero Kubernetes metadata writes.

## Rollback

`legacy-application.yaml` records the original source definition; it is not part
of the control-plane Kustomization. Rollback is an ownership transfer too:
disable automatic sync/pruning on all four child Apps through the parent and
wait for their operations to finish, then restore the original Application source
with pruning disabled. Let the old App adopt its original 56 objects, verify UIDs
and exact resource contents again, remove the four child Application objects
without cascading resource deletion, and only then restore legacy pruning.
Do not simply revert the parent while its children are still reconciling.

This POC contains ConfigMaps only. Its result establishes preservation of those
objects, not application traffic, database compatibility, or production zero downtime.
Real workload migrations additionally need full rendered-spec comparison, admission
mutation handling, readiness/traffic checks, and an observed rollback exercise.
