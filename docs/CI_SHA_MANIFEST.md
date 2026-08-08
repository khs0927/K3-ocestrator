# CI action SHA manifest

GitHub Actions references are pinned to immutable commit SHAs. The comments in
the workflow files retain the corresponding major release for reviewability.

| Action | Release tag resolved | Commit SHA | Workflows |
|---|---|---|---|
| `actions/checkout` | `v4` | `11d5960a326750d5838078e36cf38b85af677262` | `ci.yml`, `live-provider-gate.yml` |
| `actions/setup-python` | `v5` | `a26af69be951a213d495a4c3e4e4022e16d87065` | `ci.yml`, `live-provider-gate.yml` |

The static validation script fails if a workflow reintroduces a mutable
`@vN` action reference. Refresh this manifest only after resolving the new tag
through the upstream GitHub repository and reviewing the resulting diff.
