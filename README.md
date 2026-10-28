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
`argocd/applicationsets/tenants.yaml` discovers `tenants/*/deployment.yaml` and creates
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

To onboard, add `tenants/<id>/values.yaml` and `deployment.yaml`, commit, and push. To update, edit that
tenant's values or the relevant shared chart/default. No generation step or manual
Application creation is needed. A group, rather than each individual service,
is the sync and chart-release boundary in this model.

## Ownership

Tenant parents use project `tenant-parents` and manage Application definitions
in `argocd`. Groups use project `tenant-groups` and directly manage tenant
ConfigMaps. Parent pruning stays disabled; group pruning and self-healing are
enabled. Tenant offboarding and data-retention policy remain explicit operator
operations outside this configuration-only POC.

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

## Single-Application umbrella tenant

`argocd/umbrella-tenant.yaml` deploys the complete root umbrella chart, including
all 50 service dependencies and six root templates, as one Application named
`umbrella-tenant`. Its Helm release is `umbrella-tenant` and its namespace is
`tenant-umbrella-tenant`. Tenant identity is specified directly in the Application's
Helm values. It has no child Applications and is outside ApplicationSet discovery.

Across Tenant One, Tenant B, the umbrella tenant, and the control plane, there
are **12 Applications** and **168 tenant ConfigMaps**. No service pods or DNS
are provisioned.

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

The standalone umbrella tenant renders the root chart directly; the group-specific internal ordering applies to tenants using the four-group model.

## Tenant chart selection

Each `tenants/<id>/deployment.yaml` selects `chartsRevision`, `valuesRevision`,
and optional `groupChartsRevisions`. The ApplicationSet passes this metadata to
the parent chart. Each group uses its selected revision for both the group chart
and the chart repository root defaults, while tenant overrides use `valuesRevision`.
For example, a Foundation feature commit can be tested on Tenant B without changing
the other three groups, Tenant One, or the standalone umbrella Application.
Commit a revision change and wait for it to reconcile before adding settings that
only the new chart supports.
