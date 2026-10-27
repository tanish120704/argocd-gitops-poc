#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
context="${1:-colima}"
kubectl --context "$context" apply -f argocd/namespace.yaml
kubectl --context "$context" apply --server-side -n argocd -f argocd/vendor/install.yaml
kubectl --context "$context" wait --for=condition=Established crd/applications.argoproj.io --timeout=60s
kubectl --context "$context" apply -f argocd/application.yaml
kubectl --context "$context" -n argocd rollout status deployment/argocd-server --timeout=300s
