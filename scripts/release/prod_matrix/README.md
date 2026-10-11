# PROD 写矩阵，第一轮

这一轮交的是工具，不是「授权问题已经问全」的结论。它清点发现接口给出的资源和子资源、全部命名空间、第 3 节的身份；只采集 `prod_targets.json` 里写明的显式问题，外加每个身份一次全通配；没问到的格子写成 `unknown-surface`。输出里没有拒绝结论，退出码不会是 0。

显式问题不展开候选名字，不拿发现接口的动词去乘，也不读取角色的 `resourceNames`。全通配问题由程序生成，不写进目标文件。

## 怎么跑

```
python3 scripts/release/prod_matrix/prod_measure.py replay --bundle <recorded bundle>
python3 scripts/release/prod_matrix/prod_measure.py collect --bundle-out <path>
python3 scripts/release/prod_matrix/prod_ratchet.py --check
```

`collect` 把 `kubectl` 放在 `PATH` 上。重放不调用它。提问数在第一批 SubjectAccessReview 之前打印；超过 2 万则一个请求都不发，退出码 2。只读请求另有 500 条上限。墙钟 10 分钟从第一个请求算起。

默认文件都在本目录：`prod_targets.json`、`prod_fixed_identities.json`、`prod_nontargets.json`、`prod_write_exceptions.json`、`prod_write_baseline.jsonl`。同名参数可以改路径。

棘轮只读本仓库 `k8s/` 下的 YAML 原文。它不渲染 kustomize 的 generators 和 patches，不展开 Helm values，也不扫描 `k8s/` 以外的清单。渲染结果、Helm 值和仓库外的对象属于现场测量。

## 字段表

`schema_version` 一律是整数 1。缺字段、未知字段、类型不对，都以 2 退出，并指出文件和字段。

<!-- field-table:start -->
| 文件 | 位置 | 字段 | 类型 | 必填 | 允许值 |
| --- | --- | --- | --- | --- | --- |
| prod_targets.json | root | schema_version | int | yes | 1 |
| prod_targets.json | root | questions | list:question | yes |  |
| prod_targets.json | question | identity_scope | object:scope | yes |  |
| prod_targets.json | question | group | str | yes |  |
| prod_targets.json | question | version | str | yes |  |
| prod_targets.json | question | resource | str | yes |  |
| prod_targets.json | question | subresource | str | yes |  |
| prod_targets.json | question | namespace | str | yes |  |
| prod_targets.json | question | scope | str | yes | cluster, namespaced |
| prod_targets.json | question | name | str | yes |  |
| prod_targets.json | question | verb | str | yes |  |
| prod_targets.json | scope | match | str | yes | all |
| prod_nontargets.json | root | schema_version | int | yes | 1 |
| prod_nontargets.json | root | entries | list:nontarget | yes |  |
| prod_nontargets.json | nontarget | group | str | yes |  |
| prod_nontargets.json | nontarget | resource | str | yes |  |
| prod_nontargets.json | nontarget | subresource | str | yes |  |
| prod_nontargets.json | nontarget | namespace | str | yes |  |
| prod_nontargets.json | nontarget | scope | str | yes | cluster, namespaced |
| prod_nontargets.json | nontarget | reason | str | yes |  |
| prod_write_exceptions.json | root | schema_version | int | yes | 1 |
| prod_write_exceptions.json | root | exceptions | list:exception | yes |  |
| prod_write_exceptions.json | exception | class | str | yes | field, trust-root |
| prod_write_exceptions.json | exception | identity | object:context | yes |  |
| prod_write_exceptions.json | exception | group | str | yes |  |
| prod_write_exceptions.json | exception | resource | str | yes |  |
| prod_write_exceptions.json | exception | subresource | str | yes |  |
| prod_write_exceptions.json | exception | namespace | str | yes |  |
| prod_write_exceptions.json | exception | scope | str | yes | cluster, namespaced |
| prod_write_exceptions.json | exception | name | str | yes |  |
| prod_write_exceptions.json | exception | verb | str | yes |  |
| prod_write_exceptions.json | exception | request_family | str | yes | authz |
| prod_write_exceptions.json | exception | field | str | yes |  |
| prod_write_exceptions.json | exception | check | str | yes |  |
| prod_write_exceptions.json | exception | expires | date | yes |  |
| prod_write_exceptions.json | exception | removes | str | yes |  |
| prod_write_exceptions.json | exception | reason | str | yes |  |
| prod_write_exceptions.json | context | kind | str | yes | anonymous, fixed-risk, group-member, node, serviceaccount, serviceaccount-unbound, user |
| prod_write_exceptions.json | context | user | str | yes |  |
| prod_write_exceptions.json | context | groups | list:str | yes |  |
| prod_write_exceptions.json | context | uid | object:uid | yes |  |
| prod_write_exceptions.json | context | extra | object:extra | yes |  |
| prod_write_exceptions.json | context | source | str | yes |  |
| prod_write_exceptions.json | uid | state | str | yes | known, unknown |
| prod_write_exceptions.json | uid | value | str | no |  |
| prod_write_exceptions.json | extra | state | str | yes | known, unknown |
| prod_write_exceptions.json | extra | value | object:extra-map | no |  |
| prod_fixed_identities.json | root | schema_version | int | yes | 1 |
| prod_fixed_identities.json | root | rows | list:fixed-row | yes |  |
| prod_fixed_identities.json | fixed-identity | id | str | yes |  |
| prod_fixed_identities.json | fixed-identity | record | str | yes | identity |
| prod_fixed_identities.json | fixed-identity | kind | str | yes | anonymous, fixed-risk, group-member, node, serviceaccount, serviceaccount-unbound, user |
| prod_fixed_identities.json | fixed-identity | user | str | yes |  |
| prod_fixed_identities.json | fixed-identity | groups | list:str | yes |  |
| prod_fixed_identities.json | fixed-identity | uid | object:uid | yes |  |
| prod_fixed_identities.json | fixed-identity | extra | object:extra | yes |  |
| prod_fixed_identities.json | fixed-identity | source | str | yes |  |
| prod_fixed_identities.json | fixed-identity | ask | bool | yes |  |
| prod_fixed_identities.json | fixed-risk | id | str | yes |  |
| prod_fixed_identities.json | fixed-risk | record | str | yes | risk |
| prod_fixed_identities.json | fixed-risk | kind | str | yes | anonymous, fixed-risk, group-member, node, serviceaccount, serviceaccount-unbound, user |
| prod_fixed_identities.json | fixed-risk | source | str | yes |  |
| prod_fixed_identities.json | fixed-risk | ask | bool | yes |  |
| prod_fixed_identities.json | fixed-risk | reason | str | yes |  |
| prod_fixed_identities.json | fixed-auth-chain | id | str | yes |  |
| prod_fixed_identities.json | fixed-auth-chain | record | str | yes | auth-chain |
| prod_fixed_identities.json | fixed-auth-chain | confirmed | bool | yes |  |
| prod_fixed_identities.json | fixed-auth-chain | by | str | no |  |
| prod_fixed_identities.json | fixed-auth-chain | at | str | no |  |
| prod_fixed_identities.json | fixed-auth-chain | evidence | str | no |  |
| prod_fixed_identities.json | uid | state | str | yes | known, unknown |
| prod_fixed_identities.json | uid | value | str | no |  |
| prod_fixed_identities.json | extra | state | str | yes | known, unknown |
| prod_fixed_identities.json | extra | value | object:extra-map | no |  |
| prod_write_baseline.jsonl | root | schema_version | int | yes | 1 |
| prod_write_baseline.jsonl | root | category | str | yes | admission, binding, configmap, expanded-resource, fixed-identity, manifest, missing-input, namespace-label, role, task |
| prod_write_baseline.jsonl | root | namespace | str | yes |  |
| prod_write_baseline.jsonl | root | type | str | yes |  |
| prod_write_baseline.jsonl | root | name | str | yes |  |
| prod_write_baseline.jsonl | root | role_ref | str | no |  |
| prod_write_baseline.jsonl | root | subjects | list:str | no |  |
| prod_write_baseline.jsonl | root | labels | json | no |  |
| prod_write_baseline.jsonl | root | aggregation_rule | json | no |  |
| prod_write_baseline.jsonl | root | rules | json | no |  |
| prod_write_baseline.jsonl | root | resources | list:str | no |  |
| prod_write_baseline.jsonl | root | content_sha256 | str | no |  |
| prod_write_baseline.jsonl | root | data_keys | list:str | no |  |
| prod_write_baseline.jsonl | root | service_account | str | no |  |
| prod_write_baseline.jsonl | root | validation_actions | list:str | no |  |
| prod_write_baseline.jsonl | root | spec_sha256 | str | no |  |
| prod_write_baseline.jsonl | root | reason | str | no |  |
| prod_write_baseline.jsonl | root | input | str | no |  |
| prod_write_baseline.jsonl | root | provider | str | no |  |
| prod_write_baseline.jsonl | root | record | json | no |  |
| prod_write_baseline.jsonl | root | source | str | no |  |
| bundle | root | schema_version | int | yes | 1 |
| bundle | root | started_at | str | yes |  |
| bundle | root | finished_at | str | yes |  |
| bundle | root | caller | object:context | yes |  |
| bundle | root | tool_version | str | yes |  |
| bundle | root | commands | list:command | yes |  |
| bundle | root | reviews | list:review | yes |  |
| bundle | context | kind | str | yes | anonymous, fixed-risk, group-member, node, serviceaccount, serviceaccount-unbound, user |
| bundle | context | user | str | yes |  |
| bundle | context | groups | list:str | yes |  |
| bundle | context | uid | object:uid | yes |  |
| bundle | context | extra | object:extra | yes |  |
| bundle | context | source | str | yes |  |
| bundle | uid | state | str | yes | known, unknown |
| bundle | uid | value | str | no |  |
| bundle | extra | state | str | yes | known, unknown |
| bundle | extra | value | object:extra-map | no |  |
| bundle | command | id | str | yes |  |
| bundle | command | request | object:command-request | yes |  |
| bundle | command | pages | list:page | yes |  |
| bundle | command | ok | bool | yes |  |
| bundle | command | status_code | int | yes |  |
| bundle | command | started_at | str | yes |  |
| bundle | command | finished_at | str | yes |  |
| bundle | command | retry_of | str | no |  |
| bundle | command-request | method | str | yes | GET, POST |
| bundle | command-request | path | str | yes |  |
| bundle | command-request | params | json | yes |  |
| bundle | page | body | json | yes |  |
| bundle | page | continue | str | yes |  |
| bundle | review | id | str | yes |  |
| bundle | review | request | object:sar-request | yes |  |
| bundle | review | request_hash | str | yes |  |
| bundle | review | response | object:sar-response | yes |  |
| bundle | review | retry_of | str | no |  |
| bundle | sar-request | apiVersion | str | yes | authorization.k8s.io/v1 |
| bundle | sar-request | kind | str | yes | SubjectAccessReview |
| bundle | sar-request | spec | object:sar-spec | yes |  |
| bundle | sar-spec | user | str | yes |  |
| bundle | sar-spec | groups | list:str | yes |  |
| bundle | sar-spec | uid | str | no |  |
| bundle | sar-spec | extra | json | no |  |
| bundle | sar-spec | resourceAttributes | object:resource-attributes | yes |  |
| bundle | resource-attributes | group | str | yes |  |
| bundle | resource-attributes | version | str | yes |  |
| bundle | resource-attributes | resource | str | yes |  |
| bundle | resource-attributes | subresource | str | yes |  |
| bundle | resource-attributes | namespace | str | yes |  |
| bundle | resource-attributes | name | str | yes |  |
| bundle | resource-attributes | verb | str | yes |  |
| bundle | sar-response | apiVersion | str | no |  |
| bundle | sar-response | kind | str | no |  |
| bundle | sar-response | request_hash | str | yes |  |
| bundle | sar-response | status | object:sar-status | no |  |
| bundle | sar-status | allowed | json | no |  |
| bundle | sar-status | denied | json | no |  |
| bundle | sar-status | evaluationError | str | no |  |
| bundle | sar-status | reason | str | no |  |
| output-row | root | kind | str | yes | named-exception, unclassified, unknown-surface |
| output-row | root | reason | str | yes |  |
| output-row | root | row_key | str | no |  |
| output-row | root | subject | object:context | no |  |
| output-row | root | executor | object:context | no |  |
| output-row | root | group | str | no |  |
| output-row | root | version | str | no |  |
| output-row | root | resource | str | no |  |
| output-row | root | subresource | str | no |  |
| output-row | root | namespace | str | no |  |
| output-row | root | scope | str | no | cluster, namespaced |
| output-row | root | name | str | no |  |
| output-row | root | verb | str | no |  |
| output-row | root | request_family | str | no | authz |
| output-row | root | only | str | no |  |
| output-row | root | exception_class | str | no | field, trust-root |
| output-row | context | kind | str | yes | anonymous, fixed-risk, group-member, node, serviceaccount, serviceaccount-unbound, user |
| output-row | context | user | str | yes |  |
| output-row | context | groups | list:str | yes |  |
| output-row | context | uid | object:uid | yes |  |
| output-row | context | extra | object:extra | yes |  |
| output-row | context | source | str | yes |  |
| output-row | uid | state | str | yes | known, unknown |
| output-row | uid | value | str | no |  |
| output-row | extra | state | str | yes | known, unknown |
| output-row | extra | value | object:extra-map | no |  |
<!-- field-table:end -->

## 汇总的前两行

```
authorization only; questions are the explicit list, not exhaustive
not-asked: N; names-not-enumerated: N; named-subresource-not-asked: N
```

只跑只读这一半时退出码是 3。命令失败、录制包不完整或超过预算时退出码是 2，2 先于 3。
