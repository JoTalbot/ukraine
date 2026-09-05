# OBS-01 producer signal coverage matrix

The control plane consumes standard producer signals. This matrix is the explicit boundary between operational producers and support/control-plane workflows.

| Workflow | Role | Signal | Artifact | Coverage |
|---|---|---|---|---|
| `data-gov-discovery.yml` | primary ingestion/discovery producer | `ingestion` | `status-signal-ingestion` | standard signal |
| `ukraine-data-ci.yml` | data/quality CI producer | `quality` | `status-signal-quality` | standard signal |
| `entity-graph.yml` | graph producer | `graph` | `status-signal-graph` | standard signal |
| `kaggle-training.yml` | model-training producer | `training` | `status-signal-training` | standard signal |
| `edrsr-huggingface.yml` | EDRSR dataset publisher | `publication` | `status-signal-publication` | standard signal |
| `edrsr-texts.yml` | EDRSR full-text publisher | `publication` | `status-signal-publication-edrsr-texts` | standard signal |
| `discovered-open-data-huggingface.yml` | discovered open-data publisher | `publication` | `status-signal-publication-discovered-open-data` | standard signal |
| `failure-alerts.yml` | alerting/support | — | — | explicit exclusion |
| `kaggle-error-diagnostics.yml` | diagnostics/support | — | — | explicit exclusion |
| `kaggle-results-trigger.yml` | trigger/support | — | — | explicit exclusion |
| `kaggle-results.yml` | result collection/state support | — | — | explicit exclusion; training producer remains `kaggle-training.yml` |
| `pages-dashboard.yml` | presentation/deployment support | — | — | explicit exclusion |
| `recovery-checkpoints.yml` | recovery/control support | — | — | explicit exclusion |
| `release-control-plane.yml` | aggregation/control plane | — | — | explicit exclusion |
| `release-observability.yml` | release verification/control support | — | — | explicit exclusion |

## Invariants

- Producer signals are generated with `always()` so failed runs remain observable.
- Each producer signal carries source commit, workflow name, and workflow run ID.
- Producer workflows publish signal artifacts; they never write the canonical control-plane snapshot directly.
- Support workflows are not silently interpreted as producer health signals.
- A repository-level test enforces this matrix and fails when a workflow is added without classification or a producer loses its signal contract.

## Deliberate exclusions

`kaggle-results.yml` consumes and persists results from the Kaggle kernels launched by `kaggle-training.yml`. It is treated as collection/state support rather than a second `training` producer, preventing two independent workflows from racing to define the same training health signal.
