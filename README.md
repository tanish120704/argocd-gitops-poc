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
should match the `main` branch commit. The earlier `helm-values-poc` repository
is separate; it has not yet been registered as an Argo CD Application.

## Updates

Edit the desired manifests, validate with `kubectl kustomize argocd`, commit,
and push. To upgrade Argo CD, replace the vendored manifest with an explicitly
versioned upstream release and review the release's upgrade guidance first.

Documentation: https://argo-cd.readthedocs.io/en/stable/getting_started/
