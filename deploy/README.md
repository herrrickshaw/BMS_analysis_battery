# deploy/

Rescued 2026-07-17 from `event-driven-stock-analysis` before that repo was
archived — a repo hygiene audit found it was a single-burst-commit
architecture scaffold (3 commits, 48 hours, never touched again) with every
core service (`risk_calculator.py`, `rebalancing_engine.py`, `alert_engine.py`,
etc.) stubbed out as `NotImplementedError`. The K8s manifests and TOGAF
blueprint are real, standalone-useful reference material despite the rest
of that repo being vaporware.

- **`k8s-reference/`** — generic FastAPI+React K8s deployment/HPA/canary/
  ingress/kustomize manifests. This repo has no Kubernetes deployment
  config today; treat these as a starting template, not a working config —
  they reference container images, namespaces, and a Cassandra deployment
  from the other repo's context and will need adapting before use.
- **`TOGAF_ARCHITECTURE_BLUEPRINT.md`** — architecture design reference for
  a portfolio-rebalancing/risk-signal feature set (VaR, drift-based
  rebalancing, tax-loss harvesting). None of that logic is implemented
  anywhere yet; kept as design reference if those features are ever
  prioritized, not as a description of anything currently working.
