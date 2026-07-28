---
name: su-promptskill
description: 独立的视频 Prompt 编译与交付 Skill。接受任意格式的完整或部分剧本、分镜表、结构化 JSON、Markdown、Excel、单场镜头、连续文字段落和用户直接提供的镜头材料，不要求来源来自特定 Skill、合同或版本；完成只读来源标准化、语义合镜、一源镜一 Cut 时间链、受控情绪可视化、运行时 Model Profile 适配和四文件确定性交付。用于视频提示词、Seedance 或其他视频模型 Prompt、分镜合镜、Cut 链、任意 shot data 转 prompt_plan、部分分镜提示词与交付复验；不得用于重新导演或拆改源镜。
---

# 视频 Prompt 编译与交付

当前版本：`skill-version: 1.3.1`

## 使命

把当前输入物料忠实转绘为独立 `prompt_plan`。
允许组合连续源镜，但组合只改变 Prompt 单元组织，不改变源镜。

**来源只读：不得修改或回写任何来源对象、来源文件或上游交付。**

## 不可越界

- 不重排、删除、拆分或新增源镜。
- 不改变景别、构图、机位、运镜、表演意图、事实、对白、因果或时长。
- 不要求回流、回溯、降级或修改上游 Skill。
- 不以来源 Skill、合同名称或版本作为准入条件。
- 不因来源不完整而补写范围外剧情。
- 不把模型名称、自我说明或 Profile 元数据写进 Prompt 正文。

## 开始

1. 把用户指定范围锁定为本次唯一内容权威。
2. 判断输入属于结构化上游、部分分镜、独立分镜或直接材料。
3. 完整读取当前阶段对应 reference；不要用记忆替代文件。
4. 需要确定性交付时使用 `scripts/prompt_delivery.py`。

## 工作流

### 1. 标准化

完整读取 [input-normalization.md](references/input-normalization.md)。
结构化输入按现有字段适配；剧本、表格、Markdown、Excel 或文字段落先形成只读局部标准化 JSON。来源身份和版本只作 provenance，不决定能否进入。
先冻结运行模式与 reference role map；模式选择独立于 Model Profile。
只标记真实缺失，不猜时长、不补角色、不扩场景。

### 2. 决定合镜

完整读取 [grouping-rules.md](references/grouping-rules.md)。
先识别语义边界，再选择连续源镜组；时长求和只是约束，不是合镜理由。
把模型推理得到的分组证据写入 decisions 数据，交给脚本做确定性校验。

### 3. 建立 Cut 链

完整读取 [cut-chain.md](references/cut-chain.md)。
为每条源镜建立且只建立一个 Cut，按来源顺序累计时间。
任何未知时长保持未知，不伪造时间轴。

### 4. 处理情绪

完整读取 [emotion-visualization.md](references/emotion-visualization.md)。
先复用来源可见表演；仅在明确抽象情绪缺少可见行为时生成最小派生。
把派生行为与来源事实分开登记并完成语义自审。

### 5. 选择运行时 Profile

完整读取 [model-profiles.md](references/model-profiles.md)。
默认可用 Seedance 2.0 Profile；用户临时选择优先。
Profile 只能约束模型能力和格式适配，不能决定哪些镜头应合并。

### 6. 编译正文

完整读取 [prompt-compiler.md](references/prompt-compiler.md)。
逐 Cut 从对应源镜编译；不得跨 Cut 借动作、对白或摄影机事实。
所有 generation mode 都必须消费来源主要画面动作与必要连续性变化；reference 只承载其明确角色内的状态。
正文统一使用“总时长、场景、Cut、构图、画面内容”结构，不重复来源镜号，不写“现实层”或“镜头结束状态”字段。
先产出模型中立事实链，再应用 Profile 指定的受支持适配器。

### 7. 交付与复验

完整读取 [output-contract.md](references/output-contract.md)。
从输入文件名派生 ASCII kebab-case 前缀，生成 `<输入前缀>-prompt-plan.json`、`<输入前缀>-prompt-table.md`、`<输入前缀>-prompt-table.xlsx` 与 `<输入前缀>-prompt-validation.json`，再逐格复验。
复验从来源快照、decisions、generation context 与 runtime Profile 确定性重编译，不信任 plan 自报账本。
单元级问题留在对应单元；继续交付其他有效单元。

## 确定性脚本

构建：

```text
python <skill-root>/scripts/prompt_delivery.py build \
  --input <source.json> \
  --output-dir <delivery-directory> \
  [--decisions <decisions.json>] \
  [--profile-file <profile.json>]
```

复验：

```text
python <skill-root>/scripts/prompt_delivery.py validate \
  --input <source.json> \
  --output-dir <delivery-directory>
```

未提供 decisions 时，脚本按来源顺序建立安全的逐镜单元。
脚本负责结构、顺序、求和、映射、hash、来源覆盖与逐字重编译。
空间、时间、现实层、动作与叙事意图是否兼容，必须由模型按规则推理。

## 完成条件

- 每条可处理源镜恰好出现一次且可反查。
- 所有多镜单元都有显式语义兼容证据并通过硬约束。
- 已有 visible behavior 未被替换，派生情绪行为有明确 provenance。
- 不可读单元 Prompt 为空，其他可执行单元仍被交付。
- 验证状态和未解决限制如实写入 plan 与 validation report。
