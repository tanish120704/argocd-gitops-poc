# Tenant app-of-apps POC — unmodified source charts

The charts repository and existing tenant `values.yaml` files stay unchanged.
Grouping, incremental rendering, and Argo CD orchestration live in this repo.
The chart source is pinned in `releases/charts.json`.

## Group ownership

| Child Application | Wave | Services | Standalone templates | Resources per tenant |
| --- | --- | --- | --- | --- |
| Foundation | 0 | service-a, service-b, service-03 through service-12 | All six existing umbrella templates | 18 |
| Core Platform | 1 | service-13 through service-25 | None | 13 |
| Product Services | 2 | service-26 through service-40 | None | 15 |
| To Revisit | 3 | service-41 through service-50 | None | 10 |

These are synthetic POC assignments, defined once in `catalog/groups.yaml`.
Every service and root template must belong to exactly one group. The renderer
rejects duplicates, missing components, and unknown assignments.

```text
catalog/groups.yaml                   # Logical ownership; no chart moves
releases/charts.json                   # Immutable chart source commit
tenants/<tenant>/values.yaml           # Existing input, unchanged
tools/render_groups.py                # Incremental renderer
tools/test_groups.py                  # Service-change isolation verification
generated/
  state/<tenant>.json                  # Input fingerprints and artifact paths
  tenants/<tenant>/parent/*.yaml        # Four child Application definitions
  artifacts/<tenant>/<group>/<hash>/
    resources.yaml                    # Immutable rendered group contents
argocd/
  application.yaml                    # Self-managing control plane
  applicationsets/tenants.yaml         # Generates one parent per tenant
  parent-project.yaml                 # Parent may manage Applications only
  tenant-project.yaml                 # Children may manage tenant ConfigMaps
  application-health-patch.yaml        # Parent waits for child sync/health
.github/workflows/render-groups.yaml   # Generate output after input changes
```

## Render without changing source charts

The renderer reads the existing parent defaults, tenant values, and subchart
defaults. Each service is rendered independently from its original subchart,
with its parent/tenant overrides and shared global values. The root templates
are rendered using a temporary root-only chart copy. Nothing is written to the
charts checkout. This preserves all existing value names and resource names.

Fingerprints allow unchanged service output to be reused. A Service A value
change renders only Service A; unchanged services, root templates, groups, and
other tenants retain identical output. Group artifacts use content-addressed
paths; a child Application changes its source path only if that group's rendered
content changes. Artifacts are append-only so previous versions remain available.
Do not add timestamps or nondeterministic functions to configuration templates.

Group contents are plain YAML. Argo CD does not render Helm charts for tenants.
It still polls Git, compares manifests, and watches Kubernetes resources; grouping
is not a guarantee of zero controller work on unrelated Git commits.

## Local workflow

Requires Python 3.9+, Helm **v3.19.0**, and a clean checkout of the chart revision
recorded in `releases/charts.json`.

```sh
python3 -m venv .venv
.venv/bin/pip install -r tools/requirements.txt
.venv/bin/python tools/render_groups.py --charts ../helm-values-poc
.venv/bin/python tools/render_groups.py --charts ../helm-values-poc --check
.venv/bin/python tools/test_groups.py --charts ../helm-values-poc
```

Review and commit generated output alongside tenant changes when running locally.
The GitHub workflow also generates output after changes to tenant values, the
catalog, renderer, or pinned source revision. It commits only generated files.
Generated-only commits do not trigger the workflow again. Pull requests validate
and render without pushing. Fork pull requests do not receive the private chart
key and therefore require an authorized workflow run for full validation.

The `CHARTS_READ_KEY` Actions secret is a dedicated read-only deploy key for the
private charts repository. GitHub's repository token writes generated output to
this GitOps repository. Argo CD uses the existing read-only repository Secret;
private keys and real secrets never belong in values or generated ConfigMaps.

## Parent and children

The existing `tenant-tenant-one` and `tenant-tenant-b` Applications become parents
in project `tenant-parents`, with destination namespace `argocd`. Their generated
children are named `<tenant>-<group>` in project `tenants` and deploy into
`tenant-<tenant>`. Child project/destination choices are platform-controlled.

Parents have automated sync with **pruning disabled**. This preserves existing
ConfigMaps during migration from the old umbrella Application; children adopt
them in place and then own their updates and pruning. Old ConfigMap data and
resource names must be identical before and after migration. Parent deletion
and tenant offboarding are deliberate operator actions, not a supported automatic
data-retention workflow in this POC.

Children have automatic sync, self-healing, and pruning. Parent sync waves order
child Application creation/updates; custom Application health waits for child
`Synced` and `Healthy` status. Initial onboarding is sequential. Child Applications
still reconcile independently: these waves are not a transactional upgrade engine
or a guarantee of ordering for every arbitrary later commit. Content-addressed
paths make each group's intended manifest content explicit; Git revisions still
track `refs/heads/main` so newly committed artifact paths are discoverable.

The self-managing `argocd` Application is excluded from Application health
propagation to prevent a circular health dependency.

## Inspect

```sh
kubectl --context colima -n argocd get applications
kubectl --context colima -n tenant-tenant-b get configmaps
kubectl --context colima -n argocd port-forward --address 127.0.0.1 svc/argocd-server 8080:443
```

UI: https://localhost:8080 (self-signed certificate), user `admin`. Retrieve its
initial password locally:

```sh
kubectl --context colima -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 --decode
```

Each tenant still has 56 configuration snapshots, not running service workloads.
This POC does not establish production capacity for hundreds of tenants. Artifact
retention/garbage collection, data-aware offboarding, promotion policies, branch
protection, and stronger tenancy boundaries require explicit production design.
