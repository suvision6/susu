# 输出合同

新构建统一使用：

- `prompt-plan/2.0.6`
- `prompt-compiler-inputs/2.0.6`
- `prompt-validation/2.0.6`
- `grouping-review/2.0.3`
- Skill `su-promptskill 2.0.6`

2.0.6 验证器严格只接受 2.0.6；2.0.4 及更早交付由对应归档版本复验。合镜审阅合同继续使用 `grouping-review/2.0.3`。

## 正式四文件

从输入文件名派生 ASCII kebab-case slug，并写出：

1. `<slug>-prompt-plan.json`
2. `<slug>-prompt-table.md`
3. `<slug>-prompt-table.xlsx`
4. `<slug>-prompt-validation.json`

不得新增 README、CHANGELOG 或其他正式交付文件。

Markdown 与 Excel 固定四列：`Prompt 段号 | 来源镜号 | 总时长（秒） | Prompt`。
Markdown 与 Excel 都保持每个 Prompt 单元一行。A 列段号、B 列完整来源镜号、
C 列总时长和 D 列完整 `prompt_text` 都只写一次。Excel D 列使用一个自动换行、
顶部对齐的单元格，不把 Prompt 拆成多条物理行。

## Plan 必需对象

除来源、Profile、units、diagnostics、validation 和 content hash 外，v2 必须包含：

- `task`、`operations[]`
- `story_contract`、`required_entities`、`dialogue_ledger`
- `asset_binding`
- `asset_inventory`、`asset_assignments`、`unused_assets`、`mapping_confidence`
- `request_configuration`
- `prompt_advisories`
- `submission_ready`

`compiler_inputs` 保存标准化来源、运行决策和 Profile 的不可变快照及 hash，供重编译复验。`request_configuration.raw` 原样保留参数，但不得进入正文。
`dialogue_ledger` 按来源 `dialogue_id` 去重；同一来源对白跨 Cut 拆分时，原文只登记一次，
并用 `source_shot_ids[]` 与 `segments[]` 保留全部片段顺序和声位。
每个 Prompt 单元必须保存有序 `prompt_blocks[]`，并逐字重建 `prompt_text`。
`asset_binding` 为 mapped 或 unmapped，只有 mapped 且当前单元存在适用映射时才
出现素材职责区块。
多镜输入的 decisions snapshot 必须包含与锁定来源 hash 一致、逐边界完整覆盖的
`grouping_review`，并声明 `scene-global-dp-v1`；显式 operations 各自提供，不从顶层静默继承。
每个多镜单元保存 `partition_strategy` 和逐边界 `boundary_evidence`，使最终分区
可由来源、审阅和 Profile 重算。

## 状态

- `PASS`：合同、Prompt 和四文件均通过。
- `WARN`：可交付，但存在非阻断 advisory 或提交前限制。
- `PARTIAL`：部分单元被局部阻断，其余有效单元继续交付。
- `FAIL`：合同、核心素材、编译或完整性错误。

局部错误只阻断对应 Prompt 单元或 operation。`submission_ready=false` 可与最佳 Prompt 共存，表示不能按当前素材/参数直接提交。

## 确定性与完整性

- 相同来源、decisions、任务、素材、参数和 Profile 必须生成字节一致的四文件。
- `content_hash` 必须覆盖 plan 中除自身外的机器事实。
- validate 必须从 `compiler_inputs` 重编译 Prompt 并验证所有 hash、文件清单、逐格内容、顺序和覆盖关系。
- validate 必须检测 plan、Markdown、Excel 或 validation 文件的任何篡改。
- 构建和验证前后来源 hash 必须一致。
- 已识别上游形状中的非空主体、调度、表演、对白、声音、摄影、连续性和执行事实
  必须投影到模型中立事实或具有明确非正文 owner；不得静默遗漏。
- nested 与顶层字段冲突必须诊断，不能拼接、猜测或由 `execution_text` 覆盖结构化 owner。
- 同一 Cut 的场景、摄影机位置、起始状态、终态、对白、声音和规范化事实句必须无重复；
  每个 Cut 最多一个顶层 `声音：`。
- Seedance 2.5 正文必须包含目标、主体／关系／场景、镜头脚本、声音与台词和最后的
  保持一致；只有素材职责按映射条件出现。普通生成每个 Cut 恰好一个主要状态
  变化，禁止退回逐字段堆叠。
- Validation 必须输出 `chinese_semantic_checks`，并以
  `PROMPT_AUDIT_TEXT_LEAK`、`PROMPT_CHINESE_ENUM_LEAK`、
  `PROMPT_BARE_SUBJECT_FRAGMENT`、`PROMPT_STATE_ROLE_DRIFT`、
  `PROMPT_ADJACENT_LEXICAL_DUPLICATION` 阻断审计泄漏、英文声位、裸主体、
  剪辑状态冒充画面状态和相邻机械复词。
- `【声音与台词】` 固定存在，但只登记跨 Cut 声音／台词关系和音频素材职责，不得
  复抄 Cut 声音或台词原文。没有额外跨 Cut 关系时使用非重复闭合说明；无来源声音
  或台词时使用统一无来源登记。`【保持一致】` 必须是最后区块。
- Excel 只有一个 `Prompt Table` 工作表，D 列宽 160–255；所有数据统一使用
  11pt，禁止根据内容缩小字号或启用 shrink-to-fit。行高按完整 Prompt 的实际换行
  需要展开，并保持自动换行、顶部对齐、冻结表头和筛选。

## CLI

`build` 与 `validate` 接口保持不变。`build` 未传 `--profile-id` 时使用
`seedance-2.5-default`；显式传 `seedance-2.0-default` 使用兼容行为。脚本不调用 Seedance API。
多镜 `build` 缺少或未完整通过 `grouping_review` 时直接退出非零，且不创建
输出目录或任何正式文件。
