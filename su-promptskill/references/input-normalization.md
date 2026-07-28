# Input Normalization

本文件是任意格式输入、运行模式、生成 Mode Gate、reference role map、结构化字段适配、局部标准化、来源只读和缺失字段诊断的唯一规则源。

## 目录

- [内容权威与只读](#1-内容权威与只读)
- [四种来源模式](#2-四种模式)
- [shot-data 结构化路径](#3-shot-data-结构化路径)
- [局部标准化结构](#4-局部标准化结构)
- [缺失与部分成功](#5-缺失与部分成功)
- [生成 Mode Gate](#6-生成-mode-gate)
- [精确 reference role map](#7-精确-reference-role-map)
- [Edit 与 Extend](#8-edit-与-extend-局部结构)
- [来源字面审计](#9-来源字面审计)
- [Canonical hash](#10-canonical-hash)

## 1. 内容权威与只读

当前用户提供的实际范围是本次任务唯一内容权威。标准化只建立下游工作副本：

- 不修改来源对象或来源文件。
- 不向来源增加 `prompt`、分组、Cut、Profile 或派生情绪字段。
- 不根据来源 Skill 版本重解释内容。
- 不要求补齐当前范围之外的镜头。
- 未识别字段保持未解释；不要删除或赋予新语义。

若来源声明非空 hash，校验声明值；格式非法或不匹配时记录 `SOURCE_HASH_INVALID` 或 `SOURCE_HASH_MISMATCH`，全局阻断并且不得静默重写。来源没有声明 hash 时继续处理，不因来源类型、Skill、合同或版本要求补造 hash。

来源 Skill、合同名称、合同版本和 Skill 版本只作 provenance。它们不得成为准入白名单，不得反向要求用户转换、降级或回到上游。

## 2. 四种模式

| `source_mode` | 输入 |
| --- | --- |
| `upstream_structured` | 任意 Skill、工具或流程产生的结构化镜头对象 |
| `partial_storyboard` | 单场、部分镜头或任意列数的分镜表切片 |
| `standalone_storyboard` | 完整或部分剧本、分镜 JSON、Markdown、Excel、表格或文本 |
| `direct_material` | 用户直接列出的镜头、时长、画面或连续文字材料 |

文件类型和版本都不是内容权威。JSON 中有可识别 `shots[]` 时直接按字段标准化；剧本、Markdown、Excel、表格或自然语言先由模型按字面解析为局部 JSON，再进入确定性脚本。

显式 `source_mode` 使用上表四个内部 enum。来源若携带未知值，原值只留在来源快照并返回非阻断 `SOURCE_MODE_UNRECOGNIZED`；运行模式按当前材料形状安全推断。出现任意结构化 provenance 字段时可记为 `upstream_structured`，其他未声明或未知模式默认 `standalone_storyboard`。

## 3. 结构化镜头路径

任何包含可识别 `shots[]` 的 JSON 对象都走结构化路径。例如以下身份都合法：

```json
[
  {
    "contract_name": "shot-data",
    "contract_version": "2.4.3",
    "source_skill": "su-fenjingskill",
    "source_skill_version": "2.4.3"
  },
  {
    "contract_name": "another-shot-contract",
    "contract_version": "future-version",
    "source_skill": "another-tool",
    "source_skill_version": "unknown"
  }
]
```

不得检查版本配对表，不得返回“上游版本不支持”，也不得把 identity mismatch 当成内容损坏。保留实际身份字段，并从当前对象可读字段建立工作副本。

适配要求：

1. `shots[]` 数组位置是当前来源顺序。
2. `shot_order` 必须与数组顺序一致；不一致返回 `SHOT_ORDER_INVALID`。
3. `duration_seconds` 是唯一时长事实。
4. `rendered_shot_description`、`visual_content` 或 `description` 是正文转绘的主要画面来源。
5. `camera`、`blocking`、`performance`、`dialogue`、`continuity`、`continuity_updates` 与 `transition_to_next` 用于字面补全和一致性审计。
6. `performance.visible_behavior` 必须原样保留。
7. 每条原始 shot 计算独立 canonical SHA-256，用于 Cut 反查。
8. 顶层存在 `scenes[]` 时，只读 `shots[].scene_id` 关联唯一 `scenes[].scene_id`；把 scene、location、time、time_of_day、reality_layer、environment、environment_description 中实际存在的字段合入局部 `scene_context`。没有场景目录时保留镜头自身 `scene_context`。
9. `visible_props` 与 `end_state` 必须进入局部副本和编译覆盖；若主要描述已逐字承载同一内容则不重复，但不得丢失。
10. 顶层身份、版本、project ID 与 content hash 只作 provenance；非空 `content_hash` 必须是 64 位小写 SHA-256 且与观测内容一致。

结构化输入不得被压扁为只读取固定列数的显示文本。上述字段即使为空，也要按来源原值进入标准化工作副本。

scene_id 不存在、重复或找不到时返回局部 `SCENE_CONTEXT_MISSING`／`SCENE_ID_DUPLICATE`，该镜继续使用自身已有物料；不得猜场景、回写来源或要求回到导演 Skill。

## 4. 局部标准化结构

不含可直接使用 `shots[]` 的其他模式先由执行模型建立：

```json
{
  "contract_name": "prompt-source",
  "contract_version": "1.0.0",
  "source_mode": "partial_storyboard",
  "source_scope": "当前输入范围",
  "shots": [
    {
      "source_shot_id": "LOCAL-SH001",
      "source_order": 1,
      "scene_id": null,
      "duration_seconds": 3,
      "camera": {},
      "blocking": [],
      "performance": {
        "emotion_intent": "",
        "visible_behavior": []
      },
      "dialogue": [],
      "continuity": {},
      "continuity_updates": [],
      "transition_to_next": {},
      "rendered_shot_description": "",
      "scene_context": {},
      "visible_props": [],
      "end_state": []
    }
  ]
}
```

没有正式镜号时按当前数组顺序生成 `LOCAL-SH001` 等局部 ID。局部 ID 只在本次任务有效，不冒充上游镜号。

## 5. 缺失与部分成功

缺少 `duration_seconds` 时：

- 保持 `null`，不得估算、四舍五入或从对白长度反推。
- 对该镜返回 `DURATION_MISSING`。
- 禁止该镜参与多镜单元。
- 允许编译不含伪时间的单镜 Prompt。
- 继续处理其他有完整时长的单元。

无法识别某一镜内容时，把 `INPUT_MATERIAL_UNREADABLE` 限定到该镜；仍处理其他镜。只有范围为空时返回 `SOURCE_SCOPE_EMPTY`。

不可读镜头仍保留 source ID、hash、时长和 Cut 覆盖，但其单元 `status=FAIL` 且 `prompt_text=""`。不得把“画面内容：来源未提供”当作可执行 Prompt；若仍有其他有效单元，顶层状态为 `PARTIAL`，若没有任何可执行单元则为 `FAIL`。

非正数、布尔值、NaN 与 Infinity 不是合法时长。不得自动取绝对值或替换默认值。

## 6. 生成 Mode Gate

必须先选择运行模式，再进入 Prompt 编译。使用中立 machine enum：

```text
t2v | i2v | v2v | r2v | flf2v | edit | extend
```

模式是本次运行输入，不是 Model Profile。优先读取本次 decisions 的 `generation.mode`，其次读取来源显式 `generation.mode`；两者均缺失且没有任何 reference tag 时，安全选择 `t2v`。

模式前置条件必须逐 source shot／Cut 检查，不能因为全局存在一条 reference 就让所有镜头通过：

- `t2v`：不得携带媒体 reference。
- `i2v`：当前 Cut 至少一个显式 image reference。
- `v2v`：当前 Cut 至少一个显式 video reference；运动参考不得兼任人物身份。
- `r2v`：当前 Cut 至少一个具有精确角色的 image 或 video reference。
- `flf2v`：当前 Cut 必须分别存在 image 类型 `first_frame` 与 `last_frame`，且使用不同 tag。
- `edit`：当前 Cut 必须有 `edit_source`、非空 `edit_scope` 和适用 delta；每条 delta 只修改声明层，并以非空字符串数组 `applies_to_shot_ids` 限定镜头。
- `extend`：当前 Cut 必须有 `extension_source`，并有 `accepted_material=true` 和非空 `observed_end_state`。

错误分两级：

- 未知 mode、Profile 不支持 mode、全局 generation 合同无法解析：设置 `global_blocked=true`，阻断全部正文。
- 可定位到 shot、role、tag、edit delta 或 extend scope：只把受影响镜号加入 `invalid_shot_ids`；该镜保留覆盖账本但不编译正文，其他镜头继续，整体为 `PARTIAL`。

edit 或 extend 的局部前置条件失败不要求回到上游导演 Skill。

## 7. 精确 reference role map

decisions 中使用：

```json
{
  "generation": {
    "mode": "i2v",
    "available_reference_tags": ["@Image1"],
    "reference_role_map": [
      {
        "tag": "@Image1",
        "media_type": "image",
        "role": "subject_identity",
        "applies_to_shot_ids": ["SH001"],
        "preserve": ["identity", "appearance"]
      }
    ],
    "edit_scope": [],
    "edit_deltas": [],
    "extend_context": {}
  }
}
```

tag 必须逐字保留，其合法语法由当前 Model Profile 的 `reference_tag_convention` 校验。每个 tag 在 role map 中只出现一次，并且必须先列入 `available_reference_tags`；不得猜测、自动创建、重写或大小写归一化标签。

允许的单一角色：

```text
subject_identity | appearance | pose | scene_state | style
motion_reference | camera_motion | audio_reference
first_frame | last_frame | edit_source | extension_source
```

每项必须明确 `applies_to_shot_ids`，不得使用无边界全局 scope。image/video 判断只读取显式 `media_type`，不得从 tag 名称猜测；Profile 只校验该 media type 下的 tag 语法。`media_type` 还必须与 role 的媒体能力相符。单一 reference 不得无约束控制身份、姿势、场景和风格；需要另一职责时提供另一明确 reference。

来源或 decisions 中出现但未同时满足 available tag、role map 与 Profile convention 的标签，返回 `REFERENCE_TAG_UNMAPPED` 或 `REFERENCE_TAG_INVALID`。Prompt 只能逐字使用通过验证且适用于当前 Cut 的 tag。

FLF2V 的 `first_frame` 和 `last_frame` 是端点状态，不是新增镜头。V2V 的 `motion_reference` 与 `camera_motion` 只控制运动，不携带人物身份。

## 8. Edit 与 Extend 局部结构

edit：

```json
{
  "edit_scope": ["lighting"],
  "edit_deltas": [
    {
      "layer": "lighting",
      "instruction": "把已声明主光改为冷色。",
      "applies_to_shot_ids": ["SH001"]
    }
  ]
}
```

每条 `layer` 必须存在于 `edit_scope`；`applies_to_shot_ids` 必须是非空、无重复、只含现有 source shot ID 的字符串数组。字符串、对象或其他类型使相关镜头局部阻断，非法 delta 原值仅留在 decisions snapshot 与诊断中，不得进入 generation context 或 Prompt。脚本只能证明声明一致；修改是否越层仍需模型语义审阅。

extend：

```json
{
  "extend_context": {
    "accepted_material": true,
    "observed_end_state": "来源素材可观察到的结束状态"
  }
}
```

`observed_end_state` 只作延展起点校验，Prompt 不把它改写成新的导演事实。

## 9. 来源字面审计

标准化不得对 `rendered_shot_description`、camera、blocking、visible_behavior、dialogue、scene、audio、constraints、visible_props、end_state 或其他来源字段做 anti-slop 删字、替换或清洗。

来源出现“电影感、史诗、震撼、大师级、8K”等疑似词时只记录 `SOURCE_ANTI_SLOP_REVIEW`，因为它们可能是对白、片名、物件名称或既有导演文字。来源值和字段 hash 必须保持不变；语义改写只能由执行模型在不改变事实的前提下审阅，脚本不作词面导演。

## 10. Canonical hash

JSON hash 使用 UTF-8、`sort_keys=true`、紧凑分隔符和禁止 NaN 的 canonical JSON。

- `source_content_hash`：来源声明值。
- `observed_content_hash`：删除顶层 `content_hash` 后对实际输入计算。
- `local_content_hash`：对本次实际输入完整内容计算。
- `source_shot_hash`：对单条原始镜头对象计算。

所有 hash 只用于追溯和校验，不赋予下游修改来源的权利。
