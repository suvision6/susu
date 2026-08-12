---
name: su-promptskill
description: 独立的视频 Prompt 编译与四文件交付 Skill。接受完整或部分剧本、导演分镜、JSON、Markdown、Excel、连续文字和图片、视频、音频参考；默认按 Seedance 2.5 官方规则完成只读标准化、故事合同、两遍素材理解、生成/编辑/延长任务路由、一源镜一 Cut、结构化 Prompt 编译和确定性复验。也支持显式 Seedance 2.0 与 generic-video Profile；不得重新导演或回写来源。
---

# 视频 Prompt 编译与交付

当前版本：`skill-version: 2.0.0`

## 使命与边界

把用户锁定的输入忠实编译为可直接提交的视频 Prompt，并交付
`prompt-plan/2.0.0` 四文件包。

**来源只读：不得修改或回写任何来源对象、文件或上游交付。**

- 不重排、删除、拆分或新增源镜；每条源镜恰好映射一个 Cut。
- 不改变人物身份、关系、事件、结局、对白、构图、机位、运镜或表演意图。
- 素材观察只补可见或可听属性，不能覆盖来源事实。
- 不猜时长、对白、角色、素材编号或范围外剧情。
- 不把模型名、API 参数、分析、advisory 或 Markdown 外壳写进 `prompt_text`。
- 不要求修改来源 Skill，也不以来源合同或版本作为准入条件。

## 工作流

### 1. 锁源并标准化

完整读取 [input-normalization.md](references/input-normalization.md)。
先冻结来源，再建立 `story_contract`、`required_entities`、
`dialogue_ledger`、素材库存和职责映射。任务使用 `task.primary`、
`task.input_topology`、`task.modules[]`；旧 `generation.mode` 仅作为确定性输入兼容层。

素材理解分两遍：第一遍建立完整库存，第二遍只深读已匹配、冲突、关键帧和当前场景素材。映射优先级固定为“用户指定 > Prompt 描述 > 素材内容 > 文件名/元数据 > 上传顺序”。

### 2. 路由任务与操作

每个 operation 只能有一个主任务：`generate | edit | extend`。
白模重渲染属于生成；编辑后延长必须拆成两个有顺序依赖的 operations，第二步使用第一步输出作为新母版。核心母版或延长源缺失时局部阻断；非核心参考缺失时删除无效引用并写入 advisory。

### 3. 决定合镜并建立 Cut 链

完整读取 [grouping-rules.md](references/grouping-rules.md) 与
[cut-chain.md](references/cut-chain.md)。先判断语义兼容，再应用 Profile 上限。
Seedance 2.5 每单元最多 30 秒、10 Cut；Seedance 2.0 最多 15 秒、5 Cut。
源时长为可靠整数边界时可写数字时间段；非整数保留在机器时间线，Prompt 改用有序阶段，不四舍五入。API 目标时长永远不能反推 Prompt 时间戳。

### 4. 处理情绪

完整读取 [emotion-visualization.md](references/emotion-visualization.md)。
优先复用可见表演；只有明确抽象情绪缺少可见行为时才生成最小派生，并记录 provenance。

### 5. 选择 Profile 并编译

完整读取 [model-profiles.md](references/model-profiles.md) 与
[prompt-compiler.md](references/prompt-compiler.md)。默认 Profile 是
`seedance-2.5-default`，模型 ID 为 `doubao-seedance-2-5-260628`；显式选择
`seedance-2.0-default` 可恢复旧模型行为。

Seedance 2.5 编译时还要完整读取
[seedance-2-5-adapter.md](references/seedance-2-5-adapter.md)。用户已有素材标签逐字保留并通过库存成员关系校验；禁止裸 Asset ID。首帧、尾帧、母版、延长源与声音编辑各用精确职责表达。

### 6. 交付与复验

完整读取 [output-contract.md](references/output-contract.md)。从输入文件名派生 ASCII kebab-case 前缀，输出：

- `<前缀>-prompt-plan.json`
- `<前缀>-prompt-table.md`
- `<前缀>-prompt-table.xlsx`
- `<前缀>-prompt-validation.json`

Markdown/Excel 保持 `Prompt 段号 | 来源镜号 | 总时长（秒） | Prompt` 四列，表格 Prompt 单元格必须逐字等于纯 `prompt_text`。验证器从锁定来源、decisions、任务、素材、请求参数和 Profile 确定性重编译，不信任 plan 自报账本。

## 确定性脚本

构建：

```text
python <skill-root>/scripts/prompt_delivery.py build \
  --input <source.json> \
  --output-dir <new-delivery-directory> \
  [--decisions <decisions.json>] \
  [--profile-id seedance-2.5-default|seedance-2.0-default|generic-video] \
  [--profile-file <profile.json>]
```

复验：

```text
python <skill-root>/scripts/prompt_delivery.py validate \
  --input <source.json> \
  --output-dir <delivery-directory>
```

未指定 Profile 时使用 Seedance 2.5。脚本只构建和验证交付，不调用 Seedance API。

## 完成条件

- 来源输入前后 hash 一致，每条可处理源镜恰好覆盖一次。
- 任务、operations、素材职责、对白台账和请求参数均可追溯。
- `submission_ready` 如实反映官方素材限制和请求配置。
- `prompt_text` 可直接提交且无参数、模型名、advisory、裸 Asset ID 或包装泄漏。
- 四文件逐格一致、两次构建字节一致、篡改可被检测。
