# Model Profiles

本文件是运行时 Model Profile schema、默认 Profile、能力限制和 Profile 选择的唯一规则源。

## 1. 所有权边界

Model Profile 只描述视频模型的生成能力、输入限制和受支持的 Prompt 适配器。它不拥有：

- 哪些镜头语义兼容；
- 长镜独立阈值；
- v1 分组策略上限；
- 短尾处理；
- 情绪可视化规则；
- 任何来源剧情事实。

合镜策略只以 `grouping-rules.md` 为准。

## 2. Schema

```json
{
  "profile_id": "seedance-2.0-default",
  "model_name": "Seedance 2.0",
  "capabilities": {
    "max_clip_duration_seconds": 15,
    "supports_multi_cut": true,
    "supports_explicit_cut_timeline": true,
    "supports_dialogue": true,
    "supported_generation_modes": [
      "t2v", "i2v", "v2v", "r2v", "flf2v", "edit", "extend"
    ],
    "reference_tag_convention": {
      "convention_id": "seedance-indexed-at-v1"
    }
  },
  "prompt_adapter_id": "explicit-cut-zh-v1"
}
```

必需字段：

- `profile_id`：本次运行的稳定标识。
- `model_name`：仅用于 provenance 和 UI。
- `capabilities.max_clip_duration_seconds`：正数模型上限。
- `capabilities.supports_multi_cut`：是否接受一个 Prompt 内多个 Cut。
- `capabilities.supports_explicit_cut_timeline`：是否接受显式时间链。
- `capabilities.supported_generation_modes`：模型输入能力支持的 mode enum；不定义 mode 语义。
- `capabilities.reference_tag_convention`：模型／adapter 接受的 reference tag 语法；不定义 reference 角色。
- `prompt_adapter_id`：`prompt-compiler.md` 中受支持的适配器。

未知能力字段可保留在输出 metadata，不得自动解释为合镜许可。

## 3. 默认 Profile

未指定时使用上例 `seedance-2.0-default`。这是方便运行的默认值，不把 Skill 锁死到 Seedance。

脚本另提供 `generic-video` 内置 Profile，能力上限仍由其 profile 数据读取。用户可用 `--profile-file` 临时传入其他 Profile，无需修改 Skill 文件。

## 4. Reference tag convention

当前实现只接受有限 convention enum：

- `seedance-indexed-at-v1`：image 使用 `@ImageN`，video 使用 `@VideoN`，N 为正整数。
- `indexed-prefix-v1`：Profile 分别声明安全 `image_prefix` 与 `video_prefix`，tag 为对应 prefix 加正整数。

安全 prefix 只能由 ASCII 字母开头，后接 ASCII 字母、数字、短横线或下划线，长度受限；不得提供任意正则表达式。脚本使用 role map 的显式 `media_type` 选择校验分支，不从 tag 反推媒体类型。

Profile 只声明输入语法能力。tag 的存在性、角色、Cut scope 和逐字保留由 `input-normalization.md` 与 `prompt-compiler.md` 负责。

## 5. 有效上限

多镜单元必须同时满足：

- 分组策略上限；
- Profile 的模型时长上限；
- Profile 的多 Cut 能力。

模型上限更长不能放宽冻结的分组策略；模型上限更短必须进一步收紧可交付单元。单镜超过模型上限返回 `MODEL_DURATION_EXCEEDED`，不得缩短或拆分。

## 6. 正文隔离

`profile_id`、`model_name`、Skill 名称和任何“我是/作为模型”的说明只能存在于 metadata，禁止进入 `prompt_text`。

Profile 不能携带任意剧情前缀或后缀。运行时适配只能选择已知 adapter，防止模型身份或外部事实注入正文。

## 7. 校验

以下情况返回 `MODEL_PROFILE_INVALID`：

- 必需字段缺失；
- 时长上限不是正有限数；
- 能力开关不是布尔值；
- adapter 未被支持；
- `supported_generation_modes` 不是非空合法 enum 集合；
- `reference_tag_convention` 不属于有限 enum 或 prefix 不安全；
- profile 试图声明 grouping policy 字段。

禁止字段包括 `standalone_when_duration_gt_seconds`、`grouping_max_duration_seconds`、`preferred_group_size` 与任何语义兼容决策。
