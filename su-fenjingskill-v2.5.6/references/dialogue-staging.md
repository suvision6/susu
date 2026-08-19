# Dialogue Staging

本文件是对白发言权、观看对象、声音位置、人物空间关系与可选覆盖方法的唯一规则源。

## 1. 发言权不等于画面所有权

先回答“谁在说、观众看谁、声音从哪里来、为什么留在或离开当前观察位置”。普通对白由镜头单元的导演目的承接；只有特殊观看策略或空间风险出现时才建立 `dialogue_design`：

```json
{
  "mode": "listener_hold",
  "speaker_sequence": ["A", "B"],
  "listener_reaction_characters": ["B"],
  "axis_id": "AX001",
  "justification": "A 发言时留在 B 的反应；B 回答后仍不急于反打，以停顿维持压力。"
}
```

对象存在时，`speaker_sequence[]` 和 `justification` 说明真实发言顺序与观看选择。`mode` 是导演自定义的简短描述，不是封闭枚举。只有导演明确要求时才填写 `face_readable_speakers[]`、`listener_reaction_characters[]` 或 `axis_id`。

## 2. 观看与发言权

- 发言权不等于画面所有权。可以看说话者、倾听者、两人关系、空位、道具或声源。
- `script_voice_type` 只记录原剧本声音性质；`shot_delivery` 记录声音在当前镜头中的落位。二者禁止混为一层。
- `speaker_presentation` 说明当前画面如何呈现说话者，不要求正脸；侧面、背面、遮挡、轮廓或前景肩背都可以承担现场对白。
- 现场对白可以在林晓彤单人镜头中成为 `shot_delivery=os`，但来源仍是 `script_voice_type=scene_dialogue`，不能被改成 VO。
- 来源 `script_voice_type=vo` 的对白只能使用 `shot_delivery=vo`；不得改成现场对白或 O.S.。
- 说话者改变必须先拆成新的 `dialogue_turn` 事件，并默认形成切镜边界。继续同镜、焦点转移、人物调度、延迟反打和倾听者留镜都是需要举证的例外，不是默认答案。
- **短对白回合例外**：相邻两个 `dialogue_turn` 若满足以下条件，默认切镜可放宽为 `hold` 或 `reframe`，并登记 `non_cut_basis=dialogue_rhythm`：
  1. 说话者仅往返一次（A→B，且 A、B 各一句）。
  2. 两句对白总字符数 ≤ 40 或总时长 ≤ 6 秒。
  3. 无新动作发起者、观看尺度跳变、新认知落点、VO/OS 转换。
  4. 现场对白。
  若 `director_profile.rhythm=kinetic` 或 `camera_energy=assertive`，仍保留默认切镜偏好。
- **用户语义意图**：
  - 肯定语义（保留同镜）：不用切、保留同镜、就一镜、不切、留在当前镜头、继续看某角色、hold 等。
  - 否定语义（改为切镜）：要切、切开、换镜、不要留、还是切吧、分开等。
  Skill 识别到上述表达时，必须生成对应的 `viewing_decision.mode` 与 `non_cut_basis`，并在 Gate 2 确认轮向用户展示处理方案。
- 面孔可读性只有在当前场景确实依赖细微表情辨认时才是要求，不是对白的普遍前提。

## 3. 必须说明的不切理由

任何非 `cut` 的观看决策都必须包含具体 `director_reason`，比较“切”与“不切”的视听收益，不能只写类别词或“保持流畅”。涉及对白的非切还必须在 `dialogue_design.justification` 中写明：为何同镜承载多名说话者仍能清楚表达发言权、观看权与声音落位。该理由在 Gate 2 确认轮提交给用户确认。用户表达否定语义时，应切换为切镜并重新生成理由。

## 3. 可选覆盖方法

以下都是候选方法，不是强制公式：

- 正反打：强调发言权或权力交换，并保持轴线关系。
- 过肩：同时保留说话者与关系压力；前景人物可以回话。
- 倾听者留镜：让说话者的声音作用于对方。
- 双人／多人共享构图：让关系和调度在同一空间中发展。
- 连续重构：通过焦点、人物或摄影机移动转移观看重点。
- 画外对白：制造距离、缺席、威胁、信息不对称或声音先行。

三人及以上对白与双人对白使用同一规则：每次发言权交接默认切镜。可以不用机械轮流近景，但任何不切都必须登记 `non_cut_basis`、完整 `dialogue_design` 和可执行 DOP 方案，不能因为同框而忽略发言权和观看重点。

## 4. 画面内容中的对白

在最终镜头的【画面内容】段落中，对白应自然嵌入人物动作与表情之后、人物状态之前。撰写时保持：

```text
...人物动作与表情描写 → 人物台词 → 人物状态描写...
```

- 对白逐字保留，不得改写或省略。
- 对白的原始语言同样属于逐字锁定内容；未经用户明确追加翻译需求，不得翻译、音译、转写或换成另一种语言。用户需要译文时，译文作为独立辅助层，不替换【画面内容】中的来源台词。
- 双语并列来源先服从 Gate 1 已锁定的 `dialogue_language_policy`；版式、排列顺序和字符体系都不是原文身份依据。`original_with_translation` 只允许 `source_role=original_dialogue` 的正文进入本段；`multilingual_actual` 则逐条保留 `source_role=spoken_dialogue` 的实际多语对白。
- 台词前的动作和表情为台词的语气和节奏提供依据。
- 台词后的人物状态承接台词落下的瞬间，不额外补写“镜头结束”。
- 当对白与动作、走位、视线转移并行时，在画面内容中按真实时间关系连续描述，不拆分为独立的“调度段”和“表演段”。

## 5. 听者反应与连续表演

- 无新事实的短听者反应可以通过 `listener_ownership` 留在当前镜头，但必须说明观看继续归倾听者的具体收益。
- 动作、反应、停顿和台词构成连续过程时，优先在同一权威【画面内容】段落中承接。
- 发言权、声音、观看对象、尺度、认知落点或动作发起者变化时默认建立切镜边界；撤销边界必须写出具体 `non_cut_basis` 和不切收益。
- 同一句对白不得按标点、呼吸或排版换行拆镜。

## 6. Gate 2 与终稿兑现

Gate 2 展示所有发言权交接及其默认切镜；只有同镜包含多个对白轮次时才必须展开 `dialogue_design`，说明发言顺序、观看所有权、声音落位、非切依据和轴线执行。

终稿通过摄影机、【画面内容】段落、逐字对白和 `shot_delivery + speaker_presentation` 兑现规划。`shot_delivery` 闭合值为：

```text
onscreen | os | vo | mediated
```

`speaker_presentation` 闭合值为：

```text
primary_face | shared_face | foreground_back | onscreen_occluded | not_visible | mediated_source
```

`primary_face` 与 `shared_face` 表示面孔可读；`foreground_back` 与 `onscreen_occluded` 表示人在画面内但不要求正脸；`not_visible` 用于当前镜头看不见说话者；`mediated_source` 用于屏幕、广播等介质声源。

## 7. 失败条件

以下为 FAIL：

- 已登记的 `speaker_sequence[]` 与真实对白顺序不一致。
- 一个屏幕事件含多个说话者，或发言权交接既没有切镜也没有有效 `non_cut_basis + dialogue_design`。
- `script_voice_type`、`shot_delivery` 与人物呈现互相矛盾。
- 来源 VO 被改成现场对白或 O.S.，或来源现场对白被改写成 VO。
- 明确声明某人面孔可读，但终稿没有兑现。
- 轴线或空间连续性发生无理由断裂。
- 终稿改变了 Gate 2 已确认的观看策略或真实剪切点。
- 终稿把来源台词翻译、音译、转写或改换为另一种语言。

没有特殊观看风险时可以省略 `dialogue_design`；逐条对白仍必须保留来源声音身份、当前镜头落位与说话者呈现。
