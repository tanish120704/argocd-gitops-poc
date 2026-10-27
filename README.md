# Argo CD GitOps POC

Argo CD runs in the existing local Colima Kubernetes cluster in namespace
`argocd`. The `argocd` Application tracks this repository's `main` branch and
`argocd/` directory, including its own Application definition. Automated sync,
pruning, and self-healing reconcile Git changes and cluster drift.

## Layout

- `argocd/vendor/install.yaml`: official, unmodified Argo CD **v3.5.6** standard installation.
- `argocd/kustomization.yaml`: desired Argo CD installation, namespace, and Application.
- `argocd/application.yaml`: self-managing GitOps Application.
- `scripts/bootstrap.sh`: one-time installation before Argo CD can reconcile Git.

Upstream source: https://raw.githubusercontent.com/argoproj/argo-cd/v3.5.6/manifests/install.yaml

This is a single-instance local POC with cluster-level permissions and no public
ingress. The UI is accessible through a loopback port-forward using the default
self-signed TLS certificate.

## Bootstrap and repository authentication

The private GitHub repository uses a read-only SSH deploy key. Its private key is
stored only in a Kubernetes repository Secret, outside Git. Before bootstrapping
a new cluster, generate a dedicated key pair outside this repository, register
its public key in GitHub repository settings as a read-only deploy key, and run:

```sh
kubectl --context colima apply -f argocd/namespace.yaml
kubectl --context colima -n argocd create secret generic argocd-gitops-repository \
  --from-literal=type=git \
  --from-literal=url=git@github.com:tanish120704/argocd-gitops-poc.git \
  --from-file=sshPrivateKey=/absolute/path/to/deploy-key
kubectl --context colima -n argocd label secret argocd-gitops-repository \
  argocd.argoproj.io/secret-type=repository
bash scripts/bootstrap.sh colima
```

Bootstrapping uses `kubectl` once to install the controller and its Application.
Thereafter, commit and push changes to `main`; Argo CD applies them from Git.
Repository credentials remain a bootstrap prerequisite and are not self-managed.

## Access

```sh
kubectl --context colima -n argocd port-forward --address 127.0.0.1 svc/argocd-server 8080:443
```

Open https://localhost:8080 and log in as `admin`. Retrieve the initial password
locally (do not commit it):

```sh
kubectl --context colima -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 --decode
```

## Verify

```sh
kubectl kustomize argocd >/dev/null
kubectl --context colima -n argocd get applications
kubectl --context colima -n argocd get pods
```

The `argocd` Application should report `Synced` and `Healthy`. Its revision
should match the `main` branch commit. Tenant Applications are generated automatically from `tenants/*/values.yaml`.

## Updates

Edit the desired manifests, validate with `kubectl kustomize argocd`, commit,
and push. To upgrade Argo CD, replace the vendored manifest with an explicitly
versioned upstream release and review the release's upgrade guidance first.

Documentation: https://argo-cd.readthedocs.io/en/stable/getting_started/

## Onboard a tenant entirely through Git

1. Create `tenants/<tenant-id>/values.yaml` containing:

   ```yaml
   global:
     tenant:
       name: tenant-two
       domain: tenant-two.example.com
   ```

2. Commit and push (or merge a pull request) to `main`.
3. The Git-managed `tenants` ApplicationSet discovers the file within roughly
   30 seconds, creates `tenant-<tenant-id>`, and syncs 50 service ConfigMaps and six umbrella ConfigMaps
   into namespace `tenant-<tenant-id>`. No Argo CD UI or CLI action is required.

Use a lowercase DNS label for `<tenant-id>` (letters, numbers, hyphens; start
and end with a letter or number), at most 46 characters to leave room for the
namespace and resource name prefixes/suffixes. Folder identity controls the
Application and namespace; `global.tenant.name` is the business-facing name.

`argocd/applicationsets/tenants.yaml` is the Git-tracked Application template.
Concrete Applications are generated in the cluster, rather than duplicated as
per-tenant YAML files in Git. Each Application uses two sources: the shared
chart repo and this repo's tenant values. Shared chart defaults load first,
then the tenant file overrides them. Both subcharts receive `global.tenant`.

The `tenants` AppProject limits tenant Applications to the two repositories,
tenant namespaces, ConfigMaps, and namespace creation. It must be extended
when the POC gains other resource types. Tenant domains are data only; this
POC does not configure DNS, ingress, or running service containers.

The chart repository has its own read-only GitHub deploy key, stored in the
`helm-values-repository` Secret in `argocd`. Rebuilding the cluster requires
recreating that repository credential, as with the GitOps repo credential.

Deleting a tenant folder causes the ApplicationSet to delete its generated
Application and its managed ConfigMaps. The automatically created namespace
remains. Treat folder deletion or renaming as tenant offboarding.

For this POC both sources track `main`, so shared chart changes affect all
tenants. Pin the chart source to an immutable tag or commit when controlled
tenant-by-tenant upgrades become necessary.

## Umbrella defaults and tenant overrides

The chart also renders `<release>-platform` from its root `templates/`
directory. Root `platform` settings have shared defaults; tenant values can
override them alongside `global.tenant` and service-specific settings.

- Tenant One inherits `support@example.com` and `featureEnabled: false`.
- Tenant B sets `support@tenant-b.example.com` and `featureEnabled: true`.

The platform ConfigMap and both service ConfigMaps use the same tenant name
and domain. The ApplicationSet is unchanged; all 56 ConfigMaps are part of
one tenant Application in its dedicated namespace.

## Expanded 50-service experiment

The shared chart now contains 50 subcharts (service-a, service-b, service-03
through service-50) and six standalone root templates. Each tenant Application
manages 56 ConfigMaps, for 112 across the two sample tenants. No service pods
are created; these snapshots exercise configuration inheritance at larger size.

Tenant One supplies identity only. Tenant B supplies sparse overrides for 10
services and all six root sections: platform, routing, notifications,
observability, security, integrations. The remaining 40 services inherit
shared defaults. Both samples include richer global tenant metadata.

Inspect `tenant-b-service-a` for zero retries and a disabled cache; inspect
`tenant-b-service-b` for an empty allowed-origins list. The `config.json` data
entry on every ConfigMap shows the entire effective configuration.

The chart repository's `scripts/verify.py` checks all 56 resources for either
local Helm output or a live `kubectl get configmaps -o json` snapshot. See its
README for setup and commands. ConfigMap settings are illustrative and are not
consumed by running workloads. This experiment validates configuration behavior;
it does not establish production capacity for hundreds of tenants.
