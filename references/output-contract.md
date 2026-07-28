# Output Contract

本文件是正式四文件交付、`prompt-plan/1.0.0`、状态、诊断、hash、CLI 与复验行为的唯一规则源。

## 目录

- [正式交付](#1-正式交付)
- [prompt plan](#2-prompt_planjson)
- [Prompt 单元与局部失败](#3-prompt-单元与局部失败)
- [诊断与状态](#4-诊断与状态)
- [表格派生与逐格复验](#5-表格派生与逐格复验)
- [validation report](#6-prompt_validationjson)
- [Hash](#7-hash)
- [CLI](#8-cli)
- [确定性与语义边界](#9-确定性与语义边界)

## 1. 正式交付

一次 build 恰好交付四个正式文件：

```text
<input-slug>-prompt-plan.json
<input-slug>-prompt-table.md
<input-slug>-prompt-table.xlsx
<input-slug>-prompt-validation.json
```

`input-slug` 从实际输入文件名派生：ASCII 小写 kebab-case，并去除 `shot-data`、`storyboard`、`screenplay`、`script` 等来源类型后缀。输入名没有可用 ASCII 标识时，使用稳定的 `source-<hash前8位>`。四个文件名都必须包含 `prompt`。

不得创建第五个正式文件。`<input-slug>-prompt-plan.json` 是机器事实源；另外三个文件只能从同一个 plan 确定性派生。它们都属于 `su-promptskill`，不得替代、修改或回写来源材料。

Markdown 与 Excel 固定四列，列名和顺序不得变化：

```text
Prompt 段号｜来源镜号｜总时长（秒）｜Prompt
```

每个 Prompt 单元恰好对应一行。`来源镜号` 按 Cut 顺序连接，`Prompt` 逐字等于单元的 `prompt_text`；局部编译失败行保留来源覆盖，Prompt 单元格为空。

## 2. `<input-slug>-prompt-plan.json`

```json
{
  "contract_name": "prompt-plan",
  "contract_version": "1.0.0",
  "skill": {"name": "su-promptskill", "version": "1.3.1"},
  "delivery": {
    "slug": "ep15-dibati",
    "files": {
      "plan": "ep15-dibati-prompt-plan.json",
      "markdown": "ep15-dibati-prompt-table.md",
      "xlsx": "ep15-dibati-prompt-table.xlsx",
      "validation": "ep15-dibati-prompt-validation.json"
    }
  },
  "compiler_inputs": {
    "contract": "prompt-compiler-inputs/1.0.0",
    "normalized_source": {},
    "normalized_source_hash": "sha256",
    "decisions_snapshot": null,
    "runtime_decisions_hash": null,
    "runtime_profile": {},
    "runtime_profile_hash": "sha256"
  },
  "source": {
    "source_mode": "upstream_structured",
    "source_contract": "shot-data/2.4.3",
    "source_skill": "su-fenjingskill",
    "source_skill_version": "2.4.3",
    "project_id": "PROJECT-001",
    "source_content_hash": "sha256-or-null",
    "observed_content_hash": "sha256",
    "local_content_hash": "sha256",
    "source_read_only": true,
    "source_shot_count": 3
  },
  "generation": {
    "mode": "i2v",
    "mode_source": "decisions",
    "available_reference_tags": ["@Image1"],
    "reference_role_map": [],
    "edit_scope": [],
    "edit_deltas": [],
    "extend_context": {},
    "runtime_decisions_hash": "sha256-or-null",
    "global_blocked": false,
    "invalid_shot_ids": []
  },
  "model_profile": {},
  "prompt_units": [],
  "diagnostics": [],
  "validation": {},
  "content_hash": "sha256"
}
```

`compiler_inputs` 是复验所需的最小确定性输入快照：当前来源重新标准化后必须逐字段匹配 `normalized_source`，decisions 与 runtime Profile 必须匹配各自 hash；plan 的 `generation` 与 `model_profile` 也必须由这些输入重算一致。快照只服务下游复验，不改变来源所有权。

`source_contract`、`source_skill` 与 `source_skill_version` 记录实际来源 provenance，可以是任意值或空值；它们不构成版本配对校验，也不决定是否允许编译。

`generation.global_blocked` 只表示未知 mode、Profile 不支持 mode 或全局 generation 合同不可解析。可定位的 role、tag、edit、extend 错误必须写入 `invalid_shot_ids`，不得阻断其他镜头。

## 3. Prompt 单元与局部失败

```json
{
  "prompt_unit_id": "PU001",
  "source_shot_ids": ["SH001", "SH002"],
  "source_shot_hashes": ["sha256", "sha256"],
  "total_duration_seconds": 11,
  "grouping_reason": "来源中的对白—反应链连续",
  "standalone_reason": null,
  "semantic_compatibility": {},
  "timeline": [],
  "prompt_text": "",
  "prompt_validation": {
    "status": "PASS",
    "checks": {},
    "diagnostic_codes": []
  }
}
```

单镜单元的 `grouping_reason` 与 `semantic_compatibility` 为 null，并提供稳定 `standalone_reason`。短镜单独不是错误。

reference 或 mode 前置条件只对某源镜失败时：

- 把该镜隔离为单镜单元；
- 仍保留 source ID、hash、时长与唯一 Cut；
- `prompt_text` 为空，不伪造可执行正文；
- `prompt_validation.status=PARTIAL`；
- `diagnostic_codes` 包含 `GENERATION_CONTEXT_INVALID`；
- 其余合法镜头继续编译。

若原计划多镜组包含局部失败镜头，拆开的是下游 Prompt 分组，不是来源镜头；所有源镜仍按原顺序恰好覆盖一次。

来源镜头没有画面、blocking、visible performance、对白或其他可编译内容时，也隔离为单镜单元：保留覆盖与 Cut provenance，`prompt_text=""`，单元 `status=FAIL`，诊断为 `INPUT_MATERIAL_UNREADABLE`。不得生成“画面内容：来源未提供”的伪可执行正文。

## 4. 诊断与状态

```json
{
  "code": "DURATION_MISSING",
  "severity": "ERROR",
  "scope": "shot",
  "path": "shots[0].duration_seconds",
  "message": "来源未提供时长；该镜保持单镜且不生成伪时间。",
  "blocks": ["multi_shot_grouping", "timed_cut_timeline"]
}
```

诊断必须定位到 source、shot、group、unit、cut、prompt 或 package；合法单镜语义以 [grouping-rules.md](grouping-rules.md) 为准。

| status | 含义 |
| --- | --- |
| `PASS` | 全部确定性检查通过 |
| `WARN` | 可交付，只有非阻断语义审阅项 |
| `PARTIAL` | 至少一个局部单元失败，并且仍有其他可执行单元一致交付 |
| `FAIL` | 没有可执行单元、来源／Mode Gate 全局阻断、重编译不一致或四文件完整性失败 |

局部错误存在时，只要来源覆盖账本可建立，就不得把整个 plan 降为空。完全不可读时 build 仍可交付一致的四文件 FAIL 诊断包，但不得伪造 Prompt 单元。

## 5. 表格派生与逐格复验

Markdown 与 Excel 必须从 `prompt_table_rows(prompt_plan)` 的同一四列行集生成。复验必须同时证明：

- 当前来源重新标准化后逐字段匹配只读快照；
- decisions snapshot、generation context 与 runtime Profile hash／内容一致；
- 每个单元从上述输入重新确定性编译，`prompt_text` 逐字一致；
- 单元 `checks`、`status`、诊断账本及顶层 `validation` 均为重算结果；
- plan 中登记的四个动态命名文件都存在，命名与输入前缀一致；
- plan JSON 是确定性字节序列；
- Markdown 表头、行数及每个单元格等于 plan；
- Excel 表头、行数及每个单元格等于 plan；
- Markdown 与 Excel 彼此逐格一致；
- 表格文件字节等于当前实现对同一 plan 的确定性派生；
- `<input-slug>-prompt-validation.json` 的状态、行账本与文件 hash 等于当前 plan 和两个表格。

任一正式文件被篡改、缺失或换成非确定性派生时，validate 返回 `FAIL`，且不覆盖原文件。

不得把 plan 自报的 `prompt_validation`、`source_read_only`、顶层 `validation` 或重新计算后的 `content_hash` 当作通过依据。即使调用者从同一篡改 plan 重新派生四个表面一致文件，只要 Prompt 或账本不等于确定性重编译结果，validate 仍返回 `FAIL`。

## 6. `<input-slug>-prompt-validation.json`

正式报告包含：

- `prompt-validation/1.0.0` 合同身份；
- plan 的 `content_hash`；
- 与 plan 一致的 status 和 validation；
- 固定列名、行数及四列行账本；
- 实际动态命名的 plan、Markdown 与 Excel 文件 SHA-256；
- 删除报告自身 `content_hash` 后计算的报告 hash。

报告不记录时间戳、随机值、机器绝对路径，也不对自身文件做循环 hash。

## 7. Hash

Prompt plan 的 `content_hash` 必须按以下唯一流程计算一次：

1. 删除或忽略 plan 顶层已有 `content_hash`；
2. 对剩余完整 plan 做 canonical JSON；
3. 计算 SHA-256；
4. 把结果写回 `content_hash`，不得再次把该字段纳入输入。

来源 hash 的定义只以 `input-normalization.md` 为准。表格与报告使用实际交付字节的 SHA-256。所有输出禁止时间戳、随机数和运行机器路径。

## 8. CLI

正式构建：

```text
python scripts/prompt_delivery.py build \
  --input <source.json> \
  --output-dir <delivery-directory> \
  [--decisions <decisions.json>] \
  [--profile-id seedance-2.0-default] \
  [--profile-file <profile.json>]
```

正式复验：

```text
python scripts/prompt_delivery.py validate \
  --input <source.json> \
  --output-dir <delivery-directory>
```

`--profile-id` 与 `--profile-file` 互斥。未提供 decisions 时逐镜交付，不报“未合镜”错误。build 对 PARTIAL/FAIL 写完四文件后返回非零；validate 只读来源与交付目录，把复验结果写到标准输出。

## 9. 确定性与语义边界

脚本确定性校验输入身份、顺序、ID、时长、hash、分组求和、Cut 映射、时间线、reference scope、主要动作与连续性覆盖、正文标签、对白、metadata、重编译结果、四列和文件 hash。字面 provenance 与 anti-slop 只以 [prompt-compiler.md](prompt-compiler.md#7-anti-slop-与-provenance) 为准。

空间、时间、现实层、动作链、叙事意图、自然语言事实忠实与情绪外化仍由模型审阅；报告必须保留这一限制。
