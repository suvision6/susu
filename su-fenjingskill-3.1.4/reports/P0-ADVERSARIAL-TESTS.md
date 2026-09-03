# P0 对抗测试记录

总体结果：**PASS**

## 结果矩阵

| 项目 | 结果 | 关键证据 |
| --- | --- | --- |
| P0-01 | PASS | SOURCE_NARRATIVE_CLASSIFICATION_FORBIDDEN, SOURCE_NON_NARRATIVE_CLASSIFICATION_UNAPPROVED |
| P0-02-formal | PASS | 202/202 required 路径被阻断，漏检 0 |
| P0-02-workspace | PASS | 327/327 required 路径被阻断，漏检 0 |
| P0-03 | PASS | camera/edit/continuity/motivation/duration 均使旧 Alignment 失效；第五列分叉被阻断 |
| P0-04 | PASS | ALIGNMENT_APPROVAL_EVENT_MISSING, ALIGNMENT_INVALIDATED, ASSUMPTION_OBLIGATION_UNRESOLVED, EXECUTION_LOCK_INVALIDATED, SOURCE_ALIGNMENT_INVALIDATED |
| P0-05 | PASS | TOPOLOGY_FACT_BINDING_DIVERGED, TOPOLOGY_PASSAGE_BINDING_DIVERGED |
| P0-06 | PASS | transaction=ROLLED_BACK，output_exists=False，parent_entries=0 |
| P0-07 | PASS | source-model:invalidated/invalidated/invalidated；method:invalidated/invalidated/invalidated；strategy:passed/invalidated/invalidated；topology:passed/invalidated/invalidated；execution:passed/confirmed/invalidated |

## P0-03 字段级观察

- `camera`：旧锁 `FAIL`；错误含 `EXECUTION_LOCK_INVALIDATED`；重新 lock 后 Gate 2=`confirmed`，Alignment=`invalidated`，正式状态=`FAIL`。
- `edit`：旧锁 `FAIL`；错误含 `EXECUTION_LOCK_INVALIDATED`；重新 lock 后 Gate 2=`confirmed`，Alignment=`invalidated`，正式状态=`FAIL`。
- `continuity`：旧锁 `FAIL`；错误含 `EXECUTION_LOCK_INVALIDATED`；重新 lock 后 Gate 2=`confirmed`，Alignment=`invalidated`，正式状态=`FAIL`。
- `motivation`：旧锁 `FAIL`；错误含 `EXECUTION_LOCK_INVALIDATED`；重新 lock 后 Gate 2=`confirmed`，Alignment=`invalidated`，正式状态=`FAIL`。
- `duration`：旧锁 `FAIL`；错误含 `EXECUTION_LOCK_INVALIDATED`；重新 lock 后 Gate 2=`confirmed`，Alignment=`invalidated`，正式状态=`FAIL`。

## P0-07 唯一失效矩阵

| 变化 | 预期 | 实际 |
| --- | --- | --- |
| source-model | invalidated / invalidated / invalidated | invalidated / invalidated / invalidated |
| method | invalidated / invalidated / invalidated | invalidated / invalidated / invalidated |
| strategy | passed / invalidated / invalidated | passed / invalidated / invalidated |
| topology | passed / invalidated / invalidated | passed / invalidated / invalidated |
| execution | passed / confirmed / invalidated | passed / confirmed / invalidated |

## 已废弃子系统移除

结果：**PASS**

- 历史未知字段被严格 Schema 拒绝。
- 备注中的普通现场词汇不触发专用关键字错误。
- canonical XLSX renderer 不生成旧字段名或旧章节标题。

测试入口：`tests/test_p0_regressions.py`。完整机器结果：`reports/P0-REGRESSION-REPORT.json`。
