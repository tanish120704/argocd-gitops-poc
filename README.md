# Tenant app-of-apps with independently deployable services

There is no pre-rendering pipeline. Argo CD renders Helm directly. Existing
root chart values, tenant values, service charts, and standalone template content
remain unchanged.

## Hierarchy

```text
tenant-<tenant>                       # Tenant parent in project tenant-parents
  <tenant>-foundation                # Group in project tenant-groups
    six standalone ConfigMaps         # Deployed directly by Foundation
    <tenant>-service-a               # Leaf Application in project tenants
    <tenant>-service-b
    <tenant>-service-03 ... service-12
  <tenant>-core-platform
    <tenant>-service-13 ... service-25
  <tenant>-product-services
    <tenant>-service-26 ... service-40
  <tenant>-to-revisit
    <tenant>-service-41 ... service-50
```

Each tenant has one parent, four group Applications, and 50 service Applications:
**55 Applications per tenant**, or 54 excluding its parent. There is no extra
platform Application. Across the two sample tenants plus the Argo CD control
plane, there are **111 Applications** and still only **112 ConfigMaps**.

## Responsibilities and grouping

- `argocd/applicationsets/tenants.yaml` discovers `tenants/*/values.yaml`.
- `applications/tenant-parent` renders the four group Application definitions.
- The chart repo's `groups/<group>/values.yaml` lists member `_services`.
- Group charts have **no service dependencies**. A shared Application template
  points each service Application directly at its existing `charts/<service>`.
- Foundation also reuses the six existing root templates and deploys their
  resources directly into the tenant namespace.
- Each service Application exclusively owns that service's Kubernetes resources.

All Application-definition templates and group membership are platform-owned.
The `tenant-groups` AppProject permits Application objects in `argocd` and
ConfigMaps in tenant namespaces, making its source an administrative trust
boundary. Service Applications use the narrower `tenants` project. Tenant inputs
and changes to platform-owned sources require appropriate repository reviews.

## Values without changing tenant input

Groups load the chart repository root `values.yaml` and then the tenant file
through Argo CD multi-source value references. Each service Application receives
only its merged service block plus shared `global` via `helm.valuesObject`.
The standalone service chart then supplies its remaining defaults:

```text
Subchart defaults → root service defaults → tenant service overrides
```

For example, root `service-b.settings` and tenant `service-b.settings` become
`.Values.settings` inside the Service B chart. Root and tenant `global` values
become `.Values.global`. No tenant file is split or rewritten.

Foundation's standalone templates read their usual root keys (`platform`,
`routing`, `security`, etc.) and the same tenant identity. No extra platform
Application or service bundle is introduced.

## Independent updates and versions

A Tenant B Service B override changes only `tenant-b-service-b`'s Application
values. Foundation may become OutOfSync while it updates that child definition;
Service B then syncs its own resource. Other service definitions and Foundation's
standalone configuration stay identical. Shared `global` changes may legitimately
affect multiple services and the standalone configuration.

Each service has its own chart `targetRevision`, sync operation, health, and
resource ownership. Membership files define `_chartsRevision` as the default and
`_serviceRevisions` as an optional service-name-to-Git-revision map. These are
platform-owned deployment settings; service overrides remain in existing tenant
values. The POC defaults to `refs/heads/main`, so a shared chart change can affect
the corresponding service for all tenants. Production promotion should pin and
advance compatible revisions deliberately.

Shared repositories may trigger refresh/render checks for other Applications.
Refreshes do not imply manifest changes or deployments.

## Ordering and lifecycle

The tenant parent orders groups in waves 0–3. Within Foundation, standalone
ConfigMaps use default wave 0 and service Application definitions use wave 1.
Application health customization waits for children to report Synced and Healthy.
This provides initial parent-driven ordering; children subsequently reconcile
independently. It is not a transactional upgrade engine for arbitrary later
changes. ConfigMaps being Healthy is not evidence that real workloads are ready.

Group pruning is disabled during resource adoption, then restored after leaf
Applications own all service resources. Leaf Applications have pruning and
self-healing enabled. Tenant-parent pruning stays disabled; tenant offboarding
and data retention are explicit operator actions. Service Application definitions
do not have cascading-deletion finalizers in this POC, so deleting a definition
is not an automatic service-data cleanup mechanism.

## Onboard, update, and inspect

Add or edit `tenants/<id>/values.yaml`, commit, and push. There is no generation
step and no need for the developer to create Applications in Argo CD.

```sh
kubectl --context colima -n argocd get applications
kubectl --context colima -n argocd get application tenant-b-service-b
kubectl --context colima -n tenant-tenant-b get configmaps
```

Local verification requires Helm 3+, Python 3.9+, PyYAML, and a sibling chart
checkout:

```sh
python3 -m venv .venv
.venv/bin/pip install -r tools/requirements.txt
.venv/bin/python tools/verify_helm_groups.py --charts ../helm-values-poc
helm template parent applications/tenant-parent --set tenantId=tenant-b
kubectl kustomize argocd >/dev/null
```

Verification renders all 50 service Applications and then each service chart,
combines their ConfigMaps with the six Foundation ConfigMaps, and compares all
56 resources to the original umbrella render for each tenant. It also verifies
that a Service B-only override changes only its Application definition.

UI access:

```sh
kubectl --context colima -n argocd port-forward --address 127.0.0.1 svc/argocd-server 8080:443
```

Open https://localhost:8080, user `admin`, accepting the self-signed certificate.
Retrieve the initial password locally with:

```sh
kubectl --context colima -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 --decode
```

This remains a configuration POC: no service workloads or DNS are provisioned.
Application count and controller load must be measured before scaling to hundreds
of tenants. GitHub credentials remain read-only Kubernetes repository Secrets;
no generated-output CI key or pipeline is needed.
