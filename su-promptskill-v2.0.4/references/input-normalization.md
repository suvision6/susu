# 输入标准化

本文件定义 `prompt-plan/2.0.4` 的只读来源标准化。输入可以是剧本、分镜、JSON、Markdown、Excel、连续文字或用户直接提供的镜头与素材说明；来源 Skill 和版本只作 provenance。

## 锁源

构建前记录来源范围与 hash。标准化只能复制、解析和派生，不能修改原对象、源文件或上游交付。来源给出的身份、关系、事件、结局、对白、构图和时长优先于任何素材观察。

最低源镜字段为：稳定 `source_shot_id`、顺序、场景、主体/动作、画面、摄影机、声音/对白、持续时间及缺失状态。不存在的字段保持缺失，不猜测。

## 故事合同

标准化后生成：

- `story_contract`：地点、时间、人物、关系、目标、事件顺序、结局与必须保持的状态；
- `required_entities`：必须出现或保持身份一致的人物、群体、道具、地点和声音；
- `dialogue_ledger`：原文对白、说话人、源镜和已绑定音频。无原文时不得编造。

自然语言中的“镜头45”若是镜号或标签，必须原样保留，不能解释成 45 度机位。

## 任务合同

新合同使用：

```json
{
  "task": {
    "primary": "generate",
    "input_topology": "multimodal",
    "modules": ["multi-reference"]
  },
  "operations": []
}
```

`task.primary` 只允许 `generate | edit | extend`。`input_topology` 只允许
`text-only | image-reference | video-reference | audio-reference | multimodal`。
modules 可表达首帧、尾帧、多参考、关键帧、宫格、白模、声音编辑和长叙事等能力。

Seedance 2.5 在内部三类主任务之外，还要输出官方路由：

- `text-to-video`：无参考素材的生成；
- `reference-generation`：`reference_image | reference_video | reference_audio` 加生成意图；
- `video-editing`：reference roles 加编辑意图；
- `video-extension`：reference roles 加延长意图；
- `first-or-first-last-frame`：严格使用 `first_frame | last_frame`。

严格首帧／首尾帧输入与多模态 `reference_*` roles 互斥。若需要“首尾帧 +
多参考”的语义近似，所有素材使用 `reference_*`，再在 Prompt 中指定关键帧；
若需要严格锁定首尾帧，则只使用 `first_frame | last_frame`。

旧模式确定性映射：

| 旧 mode | primary | topology |
|---|---|---|
| `t2v` | generate | text-only |
| `i2v` | generate | image-reference |
| `v2v` | generate | video-reference |
| `r2v` | generate | multimodal |
| `flf2v` | generate | image-reference |
| `edit` | edit | video-reference |
| `extend` | extend | video-reference |

旧输入可转换，新构建只输出 v2。旧 v1 交付必须使用已备份的 1.3.1 验证器复验。

## Operations

一个 operation 只有一个 primary。多个有依赖顺序的任务写入 `operations[]`，使用稳定 `operation_id`、`order` 和 `depends_on_operation_id`。编辑后延长的第二步引用第一步输出，不能合并成单 Prompt 或备选版本。

多镜输入的 decisions 必须包含 `grouping_review`，并用
`source_observed_hash` 绑定标准化时实际观察到的来源 hash。显式 operations
各自携带审阅，不能依赖顶层静默继承。完整字段与派生规则见
[grouping-rules.md](grouping-rules.md)。

## 两遍素材理解

第一遍建立完整 `asset_inventory`：唯一 tag、`image | video | audio`、可访问性、尺寸/时长、核心性和可观察摘要。第二遍只深读已匹配、冲突、关键帧与当前场景素材。

职责写入 `asset_assignments`，含 target entity、role、采用维度、拒绝维度、适用源镜和是否由用户映射。映射优先级固定为：

1. 用户明确指定；
2. Prompt 中的职责描述；
3. 素材可见/可听内容；
4. 文件名与元数据；
5. 上传顺序。

用户标签逐字保留；tag 必须唯一。禁止用裸 Asset ID 进入 Prompt。单人素材默认不能证明多人主体；同一实体可使用多个视图。跨实体复用只在用户明确指定或素材本身明确包含同一群体时允许。

素材合同为条件输入：无素材时省略 `asset_binding`；显式映射时使用
`{"asset_binding":{"state":"mapped"}}`。为兼容 2.0.3，已有合法
`asset_assignments` 或 reference role map 可隐式归一化为 mapped。

若来源没有直接 `audio`／`sound` 字段，标准化器从只读 `beats[].facts`、
`covered_fact_ids`、`shot_phases[].sound_fact_ids` 与明确声音词句中恢复来源声音、
音效和静默事实；对白仍由 `dialogue` 独立管理，不重复派生。

库存完整时确定性生成 `unused_assets`；不完整时不虚构。记录 `mapping_confidence` 及其依据。

## 缺失与限制

- 非核心参考缺失：移除不存在的 Prompt 引用，继续编译并写 advisory。
- 唯一编辑母版、唯一延长源或核心身份缺失：只阻断对应单元/operation。
- 素材数量、尺寸或总时长超出 Profile：保留必要映射与最佳 Prompt，设置 `submission_ready=false`。

## 请求配置

`request_configuration.raw` 原样保存用户参数，`normalized` 保存规范值，检查
`model_id`、`ratio`、`duration`、`output_format`。参数不进入 `prompt_text`，也不触发 API 调用。
