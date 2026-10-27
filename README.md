# Tenant parent plus four group Applications

Each ordinary tenant has **five Applications total**: one parent and four groups.
Services are Kubernetes resources inside their group, not individual Argo CD
Applications. There is no extra platform Application and no pre-rendering system.

```text
tenant-tenant-b
  tenant-b-foundation          # Directly deploys 12 services + six root templates
  tenant-b-core-platform       # Directly deploys 13 services
  tenant-b-product-services    # Directly deploys 15 services
  tenant-b-to-revisit          # Directly deploys 10 services
```

## Where grouping is defined

Service membership is the `dependencies` list in the charts repo's
`groups/<group>/Chart.yaml`. These small group charts reuse the existing
`charts/<service>` subcharts through local file dependencies. Foundation also
links to the existing six root templates. Argo CD builds missing local chart
dependencies as needed. No individual service Application definitions exist.

The group names and sync waves are in
`applications/tenant-parent/values.yaml`. The parent template renders four
Application objects, pointing to the four group charts. The ApplicationSet in
`argocd/applicationsets/tenants.yaml` discovers `tenants/*/values.yaml` and creates
one such parent per tenant. Parent-driven waves order the four group Applications;
subsequent group reconciliation remains independent rather than transactional.

## Values and updates

Each child loads the chart repo root `values.yaml` and then this repository's
`tenants/<id>/values.yaml`, using Argo CD multi-source values references. Both
files retain their existing structure. Helm merges subchart defaults, root service
defaults, and tenant overrides; shared `global.tenant` reaches every service and
Foundation's standalone templates. Each resource has one group Application owner.

A Tenant B Service B override changes the Service B resource in Tenant B's
Foundation Application. Other group Applications retain identical desired
resources unless the changed setting is shared and used there. Shared repository
commits may trigger checks or renders elsewhere without causing deployment.

To onboard, add `tenants/<id>/values.yaml`, commit, and push. To update, edit that
tenant's values or the relevant shared chart/default. No generation step or manual
Application creation is needed. A group, rather than each individual service,
is the sync and chart-release boundary in this model.

## Ownership and migration

Tenant parents use project `tenant-parents` and manage Application definitions
in `argocd`. Groups use project `tenant-groups` and directly manage tenant
ConfigMaps. The previous service Applications are removed only after their
ConfigMaps have been adopted by groups with identical names, UIDs, and data.
Parent pruning stays disabled; group pruning and self-healing are enabled after
the migration. Tenant offboarding and real data-retention policy remain explicit
operator operations outside this configuration-only POC.

Root `argocd/application-health-patch.yaml` allows parents to wait for group sync
and health; it avoids a circular health dependency for the self-managing Argo CD
Application.

## Verify and inspect

Requires Helm 3+, Python 3.9+, PyYAML, and a sibling charts checkout:

```sh
python3 -m venv .venv
.venv/bin/pip install -r tools/requirements.txt
.venv/bin/python tools/verify_helm_groups.py --charts ../helm-values-poc
helm template parent applications/tenant-parent --set tenantId=tenant-b
kubectl kustomize argocd >/dev/null
kubectl --context colima -n argocd get applications
```

The verifier compares all four group renders to the original root render for
both tenants (56 ConfigMaps each), rejects resource overlap, and confirms that a
Service B-only override changes only its Foundation ConfigMap.

## Migrated umbrella tenant

`argocd/umbrella-tenant.yaml` preserves the existing `umbrella-tenant` Application
as a parent with four group Applications. All 56 existing ConfigMaps remain in
`tenant-umbrella-tenant` with the same release name, data, and UIDs. Legacy values
live outside ApplicationSet discovery to preserve the parent's original name.
See [migration gates, compatibility settings, and rollback](migrations/umbrella-tenant/README.md).

Across all three tenants and the control plane, there are **16 Applications**
and **168 tenant ConfigMaps**. No service pods or DNS are provisioned.

## UI

```sh
kubectl --context colima -n argocd port-forward --address 127.0.0.1 svc/argocd-server 8080:443
```

Open https://localhost:8080 (self-signed certificate), username `admin`. Retrieve
the initial password locally:

```sh
kubectl --context colima -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 --decode
```

Both repos track `refs/heads/main` for the POC. Private Git access uses existing
read-only Kubernetes repository Secrets. No CI generation key is needed.

## Foundation's internal order

New tenants inherit Foundation's internal waves from the chart repo's
`groups/foundation/values.yaml`: shared standalone configuration at wave `-1`,
Service A at `0`, Service B at `1`, and Services 03–12 at `2`–`11`. No new
Applications are introduced, and existing tenant values are unchanged.

These resource waves operate inside each Foundation Application, independently
of the tenant parent's group waves. A tenant can override a service's `syncWave`
with a non-negative integer if a different order is explicitly intended. The
local verifier checks the order, zero handling, schema validation, metadata-only
overrides, unchanged group/data rendering, and unchanged behavior in other groups.

The current resources are ConfigMaps. A healthy ConfigMap confirms it was applied,
not that a service is running. Workload startup guarantees require real workload
health checks; sync waves are not continuous runtime dependency management.

The migrated umbrella tenant explicitly preserves its original wave metadata; it does not adopt the new internal order as part of the ownership migration.
