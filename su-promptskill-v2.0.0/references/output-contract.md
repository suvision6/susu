# 输出合同

新构建统一使用：

- `prompt-plan/2.0.0`
- `prompt-compiler-inputs/2.0.0`
- `prompt-validation/2.0.0`
- Skill `su-promptskill 2.0.0`

v2 验证器不伪装兼容 v1；旧交付由备份的 1.3.1 验证器复验。

## 正式四文件

从输入文件名派生 ASCII kebab-case slug，并写出：

1. `<slug>-prompt-plan.json`
2. `<slug>-prompt-table.md`
3. `<slug>-prompt-table.xlsx`
4. `<slug>-prompt-validation.json`

不得新增 README、CHANGELOG 或其他正式交付文件。

Markdown 与 Excel 固定四列：`Prompt 段号 | 来源镜号 | 总时长（秒） | Prompt`。
两个表格的 Prompt 单元格必须逐字等于 plan 的纯 `prompt_text`，不能附加参数、标签说明或诊断。

## Plan 必需对象

除来源、Profile、units、diagnostics、validation 和 content hash 外，v2 必须包含：

- `task`、`operations[]`
- `story_contract`、`required_entities`、`dialogue_ledger`
- `asset_inventory`、`asset_assignments`、`unused_assets`、`mapping_confidence`
- `request_configuration`
- `prompt_advisories`
- `submission_ready`

`compiler_inputs` 保存标准化来源、运行决策和 Profile 的不可变快照及 hash，供重编译复验。`request_configuration.raw` 原样保留参数，但不得进入正文。

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

## CLI

`build` 与 `validate` 接口保持不变。`build` 未传 `--profile-id` 时使用
`seedance-2.5-default`；显式传 `seedance-2.0-default` 使用兼容行为。脚本不调用 Seedance API。
