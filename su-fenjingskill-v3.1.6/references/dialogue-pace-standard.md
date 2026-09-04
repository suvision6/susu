# Dialogue Pace Standard｜su-dialogue-pace/1.0

本标准是 su-fenjingskill 的内部对白时长标定标准，不宣称是统一行业规范。数值以用户提供的 Gemini 分析为起点，并按“台词语速、字幕阅读速度必须分离”“停顿不能重复计算”“具体表演允许显式覆盖”三项原则修订。

## 1. 测量口径

- 单位：中文实际口播汉字数／秒（CPS）。
- `rate_basis` 固定为 `articulation_rate_excluding_pauses`：基础字速不含标点、换气、反应或动作停顿。
- 强／弱标点停顿由独立秒数加入，因此禁止再使用已经包含停顿的整段平均语速冒充 articulation rate。
- 数字、英文、方言、吞字、重叠对白和无法按汉字等价计算的混合口播必须使用显式 override 或人工试读，不得静默按汉字数估算。
- 字幕 CPS 属于下游阅读指标，不参与台词口播时长。

## 2. 四种成片类型的固定区间

| rhythm_profile | 中文基础区间 | 默认值 | 弱停顿区间 | 默认弱停顿 | 强停顿区间 | 默认强停顿 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 十分钟以内短剧 | 4.3–5.5 字/秒 | 4.8 | 0.08–0.18秒 | 0.12秒 | 0.15–0.35秒 | 0.22秒 |
| 平台长剧集 | 3.3–4.3 字/秒 | 3.8 | 0.15–0.35秒 | 0.22秒 | 0.30–0.60秒 | 0.42秒 |
| 3–20分钟短片 | 2.3–3.3 字/秒 | 2.8 | 0.25–0.65秒 | 0.40秒 | 0.60–1.20秒 | 0.90秒 |
| 长片电影 | 2.7–3.7 字/秒 | 3.2 | 0.20–0.55秒 | 0.35秒 | 0.45–1.00秒 | 0.70秒 |

Gate 0 必须展示该类型的区间、默认值和本项目最终选值。没有其他信息时可以提出默认值，但仍需用户确认；不得只写“快速”“自然”或“作者化”。

## 3. 选值规则

1. `range_min_cps / range_max_cps / default_cps` 必须与本标准对应 profile 完全一致。
2. `selected_cps` 必须位于该区间内；默认使用表中默认值，但必须进入 Gate 0 确认。
3. `soft_pause_seconds / strong_pause_seconds` 必须位于本 profile 的对应停顿区间。
4. `custom` 必须自己声明区间、默认值、选值和依据；不能借 custom 绕过数值合同。
5. 超出基础区间必须建立 `pace_overrides[]`，写明 scope、选值、强弱停顿和当前表演理由。

## 4. 覆盖优先级

```text
项目 BASE
→ scene override
→ character override
→ dialogue override
```

每个 timing block 的 `pace_ref` 必须指向 `BASE` 或具体 override ID。validator 同时检查 scene／character／dialogue scope，再用该引用重算对白时间；只改变镜头文字而不改变 pace_ref 或 timing blocks 不能通过。

Override 不等于随意越界。合理理由包括：抢话、崩溃、气声、宣判、古装韵律、醉酒、喘息、专业术语、命令口吻、重叠对白或明确导演方法。禁止使用“节奏需要”“更有电影感”“人物很急”等空泛理由。

## 5. 时长计算

```text
dialogue_seconds = 汉字数 / selected_cps
                 + 弱标点数 × soft_pause_seconds
                 + 强标点数 × strong_pause_seconds

parallel block = 对白、动作、摄影、声音、反应、停留中的最大值
sequential block = 上述分量之和
shot duration = 全部 timing blocks 之和
```

括号表演说明不计入口播汉字，但其实际停顿、呼吸或动作必须进入 reaction／hold／action 分量。动作与对白同时发生时不能机械相加。

## 6. 使用边界

- 本标准给出可执行区间，防止 Agent 任意写一个字速。
- 区间不生成固定切点；切、留、正反打、过肩、单人或双人仍由 dialogue edit plan 决定。
- 任何项目都可以在明确理由和 Gate 0 确认后使用 override，但不能静默越界。
