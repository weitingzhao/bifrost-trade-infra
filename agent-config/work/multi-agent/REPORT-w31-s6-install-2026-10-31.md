# W-31 S6: ci-infra installed (2026-10-31)

Infra main `b8a0d0c` (M0) carries the S6 checker inputs: the document consumer registry
(`agent-config/landing/doc-consumers.yaml`, independently reviewed 2026-10-30), the
`landing:dev` v3 rule files for PROD and STG (six infra document patterns), and the
pinned tools image `bifrost-ci-infra-tools@sha256:4ff505208b6cd977e36b7fb29c0f9faa4824a4ed9f4beb6e2f1ffc94b591a23e`
built by `bifrost-build-ci-infra-tools-1793423668` from `3af09f7` (B).

Installed on cicd from M0 through PROD approvals: the build Pipeline (#219), the
resolve / clone / check Tasks and the `bifrost-ci-infra` Pipeline (#220 to #223), and
the `infra-ci` trigger (#224, owner-run). The PROD delivery role gained `patch` on
PipelineRuns for the B5 hold (#218).

This report is the single-parent document candidate R used for the step 5 positive
run of `bifrost-ci-infra` (`purpose=landing`, base M0, platform `9997c11`).
