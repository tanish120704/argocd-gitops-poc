# Tenant app-of-apps with direct Helm rendering

Argo CD renders Helm directly. There is no pre-rendering workflow, generated
Kubernetes manifest storage, configuration compiler, or generated-output commit.
Tenant values retain their existing shape and are edited directly in Git.

```text
Charts repo                                  This GitOps repo
values.yaml                                  tenants/<tenant>/values.yaml
charts/<service>/                            applications/tenant-parent/
templates/                                   argocd/applicationsets/tenants.yaml
groups/<group>/Chart.yaml
              \                              /
               Argo CD renders each Helm group
                             |
                   Tenant Kubernetes namespace
```

## Application tree per tenant

```text
tenant-<tenant>                 # Parent: renders only four Application objects
  <tenant>-foundation          # Wave 0: 12 services + six standalone templates
  <tenant>-core-platform       # Wave 1: services 13-25
  <tenant>-product-services    # Wave 2: services 26-40
  <tenant>-to-revisit          # Wave 3: services 41-50
```

ApplicationSet discovers `tenants/*/values.yaml` and passes the directory name
as `tenantId` to the `applications/tenant-parent` Helm chart. That chart renders
the four child Application definitions with their sync-wave annotations.
Each child reads three Git sources:

1. Its group chart in `helm-values-poc/groups/<group>`.
2. The chart repo root `values.yaml`, referenced as `$defaults/values.yaml`.
3. This repo's tenant values, referenced as `$tenantValues/tenants/<id>/values.yaml`.

The last two sources supply values only and render no resources themselves.
Subchart defaults load first, root defaults override them, then tenant values
win. Shared `global.tenant` reaches services and umbrella templates. No existing
root defaults, tenant values, service templates, or root templates were changed
for this migration.

## What a Service B change does

Service B belongs to Foundation. A tenant-specific Service B override changes
only that tenant's Foundation output; the other groups have no Service B
resource to render. A shared Service B chart/default change can affect Foundation
for every tenant, except where tenant overrides mask that particular default.
If a value change produces no manifest difference, there is nothing to sync.

Argo CD may refresh and render other Applications because repositories are
shared. Refreshing is not the same as becoming OutOfSync or deploying changes.
A shared `global` value used across groups can legitimately change all groups.
The parent normally stays Synced on service-value changes: its four Application
specifications are unchanged. Children reconcile independently after bootstrap;
sync waves are not a transactional ordering guarantee for every later change.

## Onboard and update

Add `tenants/<tenant-id>/values.yaml` with tenant identity and sparse service or
platform overrides, then commit and push to `main`. There is no generation step.
The ApplicationSet creates the parent and the parent creates the four children.
Use lowercase DNS labels for tenant directory names, up to 46 characters.
Both repos track `refs/heads/main` for this POC. Production promotions should pin
and deliberately advance compatible revisions.

## Verify locally

Requires Helm 3+, Python 3.9+, PyYAML, and sibling chart checkout:

```sh
python3 -m venv .venv
.venv/bin/pip install -r tools/requirements.txt
.venv/bin/python tools/verify_helm_groups.py --charts ../helm-values-poc
helm template tenant-b-parent applications/tenant-parent --set tenantId=tenant-b
kubectl kustomize argocd >/dev/null
```

Verification builds local group dependencies, compares all four group renders
to the original root chart for both tenants (56 resources each), and checks that
a Service B-only override changes only its Foundation ConfigMap. The chart repo's
`scripts/verify.py` also verifies live ConfigMaps against effective values.

## Operations

Parents use project `tenant-parents`, restricted to Application objects in
`argocd`. Children use project `tenants`, restricted to tenant namespaces and
ConfigMaps plus namespace creation. Existing read-only GitHub repository Secrets
provide access to both private repos. There is no CI deployment key requirement.

Parent auto-sync has pruning disabled to preserve resources during migration;
child auto-sync has pruning and self-healing enabled. Resource names and ownership
remain stable during the change from pre-rendered output to direct Helm. Tenant
offboarding remains an explicit operator task; this POC does not define data
retention or automatic namespace deletion.

`argocd/application-health-patch.yaml` allows the parent to wait for child sync
and health during its waves. The self-managing `argocd` Application is excluded
from this check to prevent a circular health dependency.

```sh
kubectl --context colima -n argocd get applications
kubectl --context colima -n argocd port-forward --address 127.0.0.1 svc/argocd-server 8080:443
```

UI: https://localhost:8080 (self-signed certificate), user `admin`. Retrieve the
initial password locally with:

```sh
kubectl --context colima -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 --decode
```

There are 56 ConfigMaps per tenant, not 50 running service workloads. This POC
validates configuration and deployment boundaries, not production capacity.
