# Migration Guide｜3.1.2 → 3.1.3

su-fenjingskill 3.1.3 使用 `director-shot-data/3.1.3` 与 `director-workspace/3.1.3`。本次升级新增镜内 `shot_flow`、将 Gate 2 边界收敛为 `trigger + editorial_gain`，并把 XLSX 人类前端与后台 `execution_text` 分离。`camera-grammar-01` 继续新增 Gate 2 `viewing_design`、场级 `camera_grammar`，以及正式 `viewpoint`、framing、主体层级和画内／画外状态。

历史 3.1.2 四文件保持只读。禁止就地改版本号、覆盖历史 validation，或把迁移草稿直接当成 3.1.3 READY。

## 3.1.2 → 3.1.3 显式迁移

```bash
python -m scripts.migrate_contract_3_1_2_to_3_1_3 \
  --shot-data <historical-3.1.2-shot-data.json> \
  --workspace <historical-3.1.2-workspace.json> \
  --output-dir <new-empty-directory>
```

迁移器只接受不存在或空目录，并输出：

```text
{slug}-shot-data-3.1.3-draft.json
{slug}-director-workspace-3.1.3-draft.json
{slug}-migration-report.json
```

它保留来源、场景、镜头、时长与后台结构事实，但不猜测镜内 `shot_flow`，也不把旧四段式 boundary reason 冒充新的切点。所有新增观看字段使用显式 `unresolved` 迁移状态：不从旧双人景、平视或固定镜反推画面所有权，不猜 framing、可见／画外主体、读取尺度或摄影机响应。Gate 1、Gate 2、Alignment 和旧确认事件全部失效；完成 viewing、camera grammar、flow、`trigger + editorial_gain`、新审批与 Alignment 后才能进入正式 `build-all`。

## 历史 3.1.0 → 3.1.2 迁移

旧迁移器继续原样保留，用于历史数据分阶段进入 3.1.2；其输出仍不是 3.1.3 正式输入。

## 为什么必须显式迁移

旧数据通常缺少：

- 逐行 source ledger 和保守分类；
- 独立 source gaps / assumption obligations；
- scene/passage/fact 双向 topology；
- 当前内容对应的 Gate 与 Alignment 审批事件；
- 覆盖完整执行模型的 execution/alignment hash。

只替换 `contract_version` 不能创建这些证据。

## 生成 draft

```bash
python -m scripts.migrate_contract_3_1_0_to_3_1_2 \
  --shot-data <historical-3.1.0-shot-data.json> \
  [--workspace <historical-workspace-3.1.0.json>] \
  --output-dir <new-empty-directory>
```

输出：

```text
{slug}-shot-data-3.1.2-draft.json
{slug}-director-workspace-3.1.2-draft.json
{slug}-migration-report.json
```

迁移器拒绝非空目标目录，不覆盖输入。所有非空来源行保守地进入叙事台账；无法自动证明的分类、事实、passage、推断、假设和审批保持待人工补齐。迁移器会删除已废弃的旧管理字段，不把其内容自动搬入六列备注。

## 人工复核顺序

1. 确认权威语言、GLOBAL/scene scope 和逐行 exact accounting；
2. 形成完整 passages；
3. 为每个权威叙事 unit 建立 required fact owner；
4. 登记 source gaps 与 assumption obligations；
5. 绑定所有 shot、passage、fact 和 approved inference；
6. 建立每场 strategy、`camera_grammar`、topology 与逐单元 `viewing_design`，并验证 scene/passage/fact parity；
7. 执行正式 `viewpoint`、framing、主体可见性、景别、角度、运镜和 `shot_flow`，逐项对齐 Gate 2；
8. 依次执行 Gate 1、Gate 2 和 Alignment 审批；
9. 运行正式组合校验。

可使用：

```bash
python -m scripts.storyboard_review approve-gate1 ...
python -m scripts.storyboard_review confirm-gate2 ...
python -m scripts.storyboard_review approve-alignment ...
python -m scripts.storyboard_delivery validate --input <shot-data.json> --workspace <workspace.json>
```

## 原子正式构建

```bash
python -m scripts.storyboard_delivery build-all \
  --input <reviewed-shot-data.json> \
  --workspace <reviewed-workspace.json> \
  --output-dir <new-formal-directory>
```

正式构建在 sibling staging 目录生成并校验 JSON、Markdown 和 XLSX，最后写 validation，再原子提交整个目录。任一步失败，正式目标保持不存在或为空。不要再采用“先生成三文件、再单独补 XLSX”的两阶段流程。

## 兼容边界

`structure-validate` 只能诊断结构，输出 `STRUCTURE_ONLY`，绝不代表来源、审批或正式 readiness。下游若硬编码旧合同，应显式升级或阻断，不得把旧文件伪装成 3.1.2。
