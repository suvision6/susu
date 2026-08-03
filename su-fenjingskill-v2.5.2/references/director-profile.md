# Director Profile

本文件是 Gate 1 导演风格选项、候选选择与唯一确认、风格轴及导演库编译的唯一规则源。导演姓名只说明参考来源，不构成对在世或已故创作者的逐镜模仿指令。

## 目录

- [1. 风格的职责](#1-风格的职责)
- [2. Gate 1 内部需求提取](#2-gate-1-内部需求提取)
- [3. 默认三候选](#3-默认三候选)
- [4. 更多选择](#4-更多选择)
- [5. 用户已指定导演](#5-用户已指定导演)
- [6. 候选选择不是 Gate](#6-候选选择不是-gategate-1-只确认一次)
- [7. Profile 闭合轴](#7-profile-闭合轴)
- [8. 应用与边界](#8-应用与边界)

## 1. 风格的职责

导演风格是候选镜头的选择偏置，不是剧情改写器。先从锁定事实、表演与空间生成可行解，再用风格决定时间组织、摄影机参与、空间揭示、表演观看及转场语言。风格不得改变事实、对白、人物关系、因果、现实层、动作结果或连续性。

## 2. Gate 1 内部需求提取

从 `source_analysis` 与锁定来源内部提取以下八项，只用于候选检索，不新增顶层字段，也不进入 `shot_data`：

- 场景任务与类型变化。
- 时间压力与剪辑需求。
- 观众的观看位置。
- 摄影机参与程度。
- 空间揭示方式。
- 表演观看重点。
- 必须保护的动作、声音或表演过程。
- 误用某种风格最可能损失的来源价值。

随后读取 [director-style-reference.md](director-style-reference.md) 的紧凑索引。先筛选，再只读取需要展开的导演卡。

## 3. 默认三候选

用户未指定导演时，正式候选恰为三个：

- `STYLE-01`：主选。最直接服务场景核心任务。
- `STYLE-02`：替代。仍适配来源，但用另一种时间、摄影机或空间方法解决。
- `STYLE-03`：对照。仍可执行，主动暴露另一种观看代价与收益。

三个候选都必须适配来源，且任意候选相对其他候选，须在“时间与剪辑、摄影机、空间与调度、表演与观看”四项中至少两项存在实质差异。禁止为了凑数提供不适配来源的名导演。筛选不使用数字评分；同等匹配按索引中的稳定文件顺序决胜。

公开结构保持不变：

```json
{
  "option_id": "STYLE-01",
  "label": "倒计时交叉推进（参考克里斯托弗·诺兰）",
  "rationale": "适配依据：…\n时间与剪辑：…\n摄影机：…\n空间与调度：…\n表演与观看：…\n主要收益：…\n主要风险：…",
  "profile": {}
}
```

`label` 必须使用“策略名（参考导演）”。`rationale` 必须按上述顺序包含七段，不得省略或改名。导演知识必须先编译为可执行 profile，不能只写“像某导演”。

## 4. 更多选择

用户要求更多选择时：

1. 以 `MORE-01`、`MORE-02`……一次紧凑列出所有剩余合格风格，只包含策略名、参考导演、一句适配依据与一句主要风险。
2. `MORE-*` 只是发现索引，不写入 `director_style_options`，也不进入 Gate 1 digest。
3. 用户选择某个 `MORE-*` 后，读取对应导演卡并完整编译为 `STYLE-04`。
4. 最终正式材料包含原 `STYLE-01` 至 `STYLE-03` 加 `STYLE-04`。不替换、重排或偷偷改写原三项。

首版不支持双导演混合。若用户提出混合，要求其先确定一个主导演策略，再把另一种需求表达为场景专属 priority；不要声明成双导演风格。

## 5. 用户已指定导演

用户明确指定库内导演时，直接读取对应卡并编译一个 `director_profile`，允许省略候选数组与 `selected_style_option_id`；仍须展示完整 profile，并等待独立“确认”。同时保留“查看替代”入口。用户指定库外风格时，按同一闭合轴整理，不虚构导演卡或归因。

## 6. 候选选择不是 Gate，Gate 1 只确认一次

候选选择只是普通交互：

- “STYLE-02”“选第二个”“就这个”只确定候选，不通过 Gate。
- 选择 `MORE-*` 后编译为 `STYLE-04` 也不通过 Gate。
- 选择后展示最终 `director_profile`，包括闭合轴、一至三条场景专属 `priorities` 与 `natural_language_intent`。

最终 profile 展示后才进入唯一的 Gate 1 确认：

- 只有用户在看到最终 profile 后明确说“确认”，才写入 `selected_style_option_id`、正式 `director_profile` 和 Gate 1 digest。
- Gate 1 digest 绑定成功后自动进入并展示 Gate 2，不得停下等待“继续”。
- “继续”“可以看看”“先往下”不得视为确认；“继续”只可用于恢复系统已明确声明的异常暂停。
- 候选、选择、最终 profile、来源或 `source_analysis` 任一变化，旧确认与 digest 全部失效。

## 7. Profile 闭合轴

```json
{
  "rhythm": "restrained",
  "camera_energy": "responsive",
  "visual_distance": "mixed",
  "performance_focus": "face",
  "space_strategy": "embedded_reveal",
  "transition_language": ["gaze_cut", "long_hold"],
  "priorities": ["保留台词后的余波", "在动作中逐步显露空间"],
  "natural_language_intent": "克制地靠近人物，不抢表演。"
}
```

| 轴 | 值 |
| --- | --- |
| `rhythm` | `restrained \| balanced \| kinetic` |
| `camera_energy` | `static \| responsive \| assertive` |
| `visual_distance` | `observational \| intimate \| mixed` |
| `performance_focus` | `body \| face \| blocking \| ensemble \| mixed` |
| `space_strategy` | `establish_then_enter \| embedded_reveal \| subjective \| mixed` |
| `transition_language[]` | `hard_cut \| action_cut \| gaze_cut \| sound_bridge \| long_hold \| dissolve \| fade` |

`priorities` 必须为一至三条，只保留真正影响本场镜头选择的项目，不照抄导演卡、不为达到三条而填充；`natural_language_intent` 用普通导演语言总结最终观看方式。转场术语到最终类型的映射仍由 [shot-design.md](shot-design.md) 负责。

上述五个闭合轴、`transition_language[]`、`priorities[]` 与 `natural_language_intent` 全部必需；缺少任一字段或出现未定义字段都 FAIL。候选 profile 与最终 profile 使用同一闭合结构。

## 8. 应用与边界

Gate 1 确认后，必须在每场 `directing_plan.style_anchors[]` 中把 profile 编译为具体、可引用的场级锚点：

```json
{
  "style_anchor_id": "SA001",
  "profile_basis": [
    {"field": "camera_energy", "value": "responsive"},
    {"field": "priorities", "value": "保留台词后的余波"}
  ],
  "scene_application": "让摄影机只在人物目光或关系发生变化时重置观察位置，问话后的沉默保持不切。",
  "avoidance": "避免把 responsive 表面化为持续移动，也不靠统一平视伪装克制。"
}
```

- `style_anchor_id` 使用全片唯一的 `SAxxx`。
- `profile_basis[]` 至少引用一个已确认 profile 字段和值；字段可为闭合轴、`transition_language`、`priorities` 或 `natural_language_intent`，值必须完全匹配 Gate 1。
- `scene_application` 说明该场的时间、摄影机、空间、构图或表演观看如何执行这些值。
- `avoidance` 明确该场最容易出现的表面化模仿或误用。
- 每场 `directing_plan.style_anchors[]` 至少有一个场级锚点，并随 Gate 2 digest 一起确认。普通 `visual_plan` 可省略 `style_anchor_ids[]`；只有关键风格应用、有意例外或命中 `visual_uniformity_reviews[]` 时才逐镜引用。改变 profile 先使 Gate 1 失效；改变场级锚点、既有逐镜引用或复核引用使 Gate 2 失效。

对每场戏先识别发言权、主要观看主体、观看尺度、认知落点和动作发起者，建立默认切镜边界；最后才审查连续动作、遮挡证明或特殊表演是否足以用 `non_cut_basis` 撤销切点。profile 与场级锚点决定这些边界的节奏、距离和观看方法，不能用“停留感”减少必要覆盖。风格不设固定镜头、特写、运动镜头、长镜、景别或角度百分比；统计是 Gate 2 复核证据，不能为了满足比例而增删镜头。
