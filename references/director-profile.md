# Director Profile

本文件是 Gate 1 导演风格选项、风格轴、风格优先级和风格如何参与镜头选择的唯一规则源。

## 1. 基本原则

导演风格是候选镜头的选择偏置，不是剧情改写器，也不是交付末尾附加的形容词。

先从锁定事实、表演和空间生成可行候选，再用风格决定：

- 切点密度与停留长度。
- 镜头能量及摄影机响应程度。
- 视觉距离与表演观察距离。
- 面部、身体、调度或群体关系的表演重心。
- 先建立空间还是在行动中揭示空间。
- 硬切、动作切、视线切、声音桥或长停留等转场语言。

风格不得改变事实、对白、人物关系、因果、现实层、动作结果或连续性。

## 2. Gate 1 风格选项

锁源并展示 `source_analysis` 后确认导演倾向：

- 用户未指定风格时，说明各选项如何改变观察距离、节奏、空间和转场倾向。
- 用户未指定风格时提供至少两个可比较选项。
- 用户已明确指定风格时，直接把它整理成一个可执行 profile，不强制制造第二个候选。
- 用户必须明确选择或确认；不得把先前描述、默认偏好或“继续”当作 Gate 1 确认。
- 有候选选项时，`selected_style_option_id` 引用已展示选项，正式 `director_profile` 与所选 profile 一致。
- 风格选项、选择结果或 profile 改变时，Gate 1 digest 失效。

## 3. 风格表达

`director_profile` 至少保留 `priorities[]` 与 `natural_language_intent`。以下轴只在有助于镜头选择时使用，不为完整表格强制填满：

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

可用值：

| 轴 | 值 |
| --- | --- |
| `rhythm` | `restrained | balanced | kinetic` |
| `camera_energy` | `static | responsive | assertive` |
| `visual_distance` | `observational | intimate | mixed` |
| `performance_focus` | `body | face | blocking | ensemble | mixed` |
| `space_strategy` | `establish_then_enter | embedded_reveal | subjective | mixed` |
| `transition_language[]` | `hard_cut | action_cut | gaze_cut | sound_bridge | long_hold | dissolve | fade` |

`priorities` 保留真正影响镜头选择的两三项自然语言倾向，不为凑数量拆句；`natural_language_intent` 保留用户原始导演意图。

转场语言到最终转场类型的术语映射只由 [shot-design.md](shot-design.md) 定义。这里表达总体倾向，不是具体场景转场的许可白名单。

## 4. 应用顺序

对每场戏执行：

1. 先识别完整行动、表演、声音和空间过程。
2. 生成保持不切与改变观察位置的候选方案。
3. 排除不可执行、改写剧情、破坏连续性或压扁表演的候选。
4. 用 `priorities` 和有意义的风格轴比较剩余方案。
5. 把场级选择写进 `directing_plan`，把具体剪切理由写进 Gate 2 的 `trigger + editorial_gain`。
6. 在整场完成后做观感回看，但不为统计数字返工镜头。

## 5. 禁止配额

禁止设定固定镜头、特写、运动镜头、长镜或任何景别的百分比目标。聚合统计只能帮助人工回看节奏，不能成为增删镜头的原因。

## 6. 组合示例

- 克制观察：更愿意不切，保留沉默与余波，让摄影机少于演员主动。
- 动态卷入：更愿意在动作、声音、视线、节奏和空间关系变化时响应，但每刀仍需具体收益。
- 亲密表演：更靠近细微可见行为，但不把固定微表情清单当作表演模板。

这些只是轴的组合示例，不是模板；同一 profile 在不同场景可产生不同镜头数量。
