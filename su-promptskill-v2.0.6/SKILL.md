---
name: su-promptskill
description: 将剧本、导演分镜、JSON、Markdown、Excel 与多模态参考只读编译为可提交的视频 Prompt 和确定性四文件；默认适配 Seedance 2.5，也支持 Seedance 2.0 与 generic-video。用于生成、编辑、延长、合镜审阅和交付复验；不得重新导演、改写对白或回写来源。
---

# 视频 Prompt 编译与交付

当前版本：`skill-version: 2.0.6`

## 使命与边界

把用户锁定的输入忠实编译为可直接提交的视频 Prompt，并交付
`prompt-plan/2.0.6` 四文件包。

**来源只读：不得修改或回写任何来源对象、文件或上游交付。**

用户在当前任务中交付并锁定的剧本、分镜或素材说明就是来源权威。来源可以没有
Skill 身份、合同名或版本，也可以来自未知或未来工具；不得因此拒绝、降级或要求
上游迁移。适配器只按实际字段形状工作，无法无损消费的已知非空事实必须明确阻断。

- 不重排、删除、拆分或新增源镜；每条源镜恰好映射一个 Cut。
- 不改变人物身份、关系、事件、结局、对白、构图、机位、运镜或表演意图。
- 素材观察只补可见或可听属性，不能覆盖来源事实。
- 不猜时长、对白、角色、素材编号或范围外剧情。
- 不把模型名、API 参数、分析、advisory 或 Markdown 外壳写进 `prompt_text`。
- 不要求修改来源 Skill，也不以来源合同或版本作为准入条件。
- 不把下游偏好的 schema、版本或字段命名反向变成用户或上游的义务。

## 工作流

### 1. 锁源并标准化

完整读取 [input-normalization.md](references/input-normalization.md)。
冻结来源并建立故事、实体、对白、任务与素材合同；素材按“用户指定 > Prompt
描述 > 内容 > 元数据 > 上传顺序”两遍理解，只有 mapped 职责进入正文。
上游按字段形状只读投影，版本只作 provenance；冲突或已知非空字段静默遗漏时
阻断。完整规则见 [source-fidelity-adapters.md](references/source-fidelity-adapters.md)。
画内／画外主体和剪辑边界各有 owner；`execution_text` 只允许登记为
`audit_only | fallback_unique_facts | blocked`。

### 2. 路由任务与操作

每个 operation 只能有一个主任务：`generate | edit | extend`。
编辑后延长拆为有序 operations；核心母版／延长源缺失时局部阻断。

### 3. 决定合镜并建立 Cut 链

完整读取 [grouping-rules.md](references/grouping-rules.md) 与
[cut-chain.md](references/cut-chain.md)。多镜必须逐边界提交完整
`grouping_review/2.0.3`，再由 `scene-global-dp-v1` 按语义与 Profile 容量确定分区；
每条源镜仍恰好一个 Cut。小数时长使用有序阶段，API 时长不反推时间戳。

### 4. 处理情绪

完整读取 [emotion-visualization.md](references/emotion-visualization.md)。
已有可见表演原样使用；只有明确情绪缺少行为时才允许带 provenance 的最小派生。

### 5. 选择 Profile 并编译

完整读取 [model-profiles.md](references/model-profiles.md) 与
[prompt-compiler.md](references/prompt-compiler.md)，并按需读取
[seedance-2-5-adapter.md](references/seedance-2-5-adapter.md)。默认
`seedance-2.5-default`；正文按目标、条件素材、主体场景、逐镜脚本、跨 Cut 声音关系、
最后保持一致组织。结构化字段各有唯一 owner，`execution_text` 只补独有事实；
不得自动选择镜头、表演、物理、灯光或风格。
Seedance 2.5 使用中文声位、完整主体句和精炼运镜句；单元目标不得借用剪辑入口或出口。

### 6. 交付与复验

完整读取 [output-contract.md](references/output-contract.md)。从输入文件名派生 ASCII kebab-case 前缀，输出：

- `<前缀>-prompt-plan.json`
- `<前缀>-prompt-table.md`
- `<前缀>-prompt-table.xlsx`
- `<前缀>-prompt-validation.json`

Markdown/Excel 保持 `Prompt 段号 | 来源镜号 | 总时长（秒） | Prompt` 四列。
每单元一行、D 列保存完整正文；验证器从锁定编译输入重建，不信任 plan 自报。

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
多镜输入的 `--decisions` 为必需；缺少或无效时命令退出非零且不创建输出目录。
候选维护证据位于 `reports/`，不属于正式四文件交付。
形状适配、冲突、重复对白和旧扁平输入回归见 `evals/output/`；评测文件同样不进入正式交付。

## 完成条件

- 来源 hash、顺序、一源镜一 Cut、任务、素材、对白、请求配置和事实 owner 可追溯。
- 已知非空执行字段不能静默丢失；正文无参数、模型名、诊断、裸 Asset ID 或风格注入。
- 每个 Cut 最多一个顶层“声音：”，无损合并该 Cut 的来源声音子项；
  `【声音与台词】`只登记跨 Cut 声音关系，不复抄 Cut 声音或台词原文。
- 每阶段一个主要变化，每条声音与视觉事实只有一个正文 owner。
- 中文正文无审计字段、英文声位枚举、裸主体残片、状态角色漂移或相邻机械复词。
- 四文件逐格一致、重复构建字节一致、篡改可检测。
