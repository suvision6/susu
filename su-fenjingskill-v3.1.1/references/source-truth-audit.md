# Source Truth & Internal Audit｜剧本事实与内部审计

本文件只拥有来源事实、反向覆盖和来源歧义边界。它不得决定镜头数量、切点、景别或导演方法。

## 1. 锁定来源

保留完整 locked text、输入类型、批准修正和来源哈希。逐场识别：

- 场景头、时间、地点和现实层；
- 人物、关系和在场状态；
- 逐字逐语言对白、说话者及来源声音身份；
- 动作、动作结果、因果、关键道具和不可逆状态；
- 场景进入状态、离开状态及跨场继承。

来源未明确的内容不得冒充事实。导演可以提出可逆调度和表演选择，但必须属于 director inference 或 assumption。

## 2. 来源单元

内部审计把锁定文本划为 source units，用于回答“原文去了哪里”，不回答“应该切几镜”。

每个非空叙事单元至少记录：

- unit_id；
- scene_id；
- line_start / line_end；
- kind：scene_heading | action | dialogue | stage_direction | source_sound | transition | metadata；
- exact_text；
- speaker / voice_type（适用时）；
- semantic_summary；
- coverage_status：covered | intentionally_withheld | intentionally_omitted；
- shot_refs[]；
- reason（有意处理时必需）。

metadata 和纯制作标签可以不进入成片，但必须能说明排除规则。对白、动作结果、因果、来源声音和现实层变化不得静默遗漏。

## 3. 对白与声音

- 一个完整来源发言只登记一次。
- 画面可在发言期间切换；playback 按镜头顺序拼接后必须逐字等于来源。
- stage direction 不计入口播文字，但必须进入动作、表演或停顿设计。
- source voice type 与当前镜头 delivery 分开：来源 V.O. 不得被摄影选择改成现场对白。
- 无法判断 V.O./O.S./mediated 时使用 unresolved 并写入真实待确认项，不猜测。

## 4. 反向审计

交付前从 locked text 反向检查，而不是只检查模型已经登记的对象：

1. 每个非空叙事单元是否登记；
2. exact_text 是否与锁定行一致；
3. 每个单元是否覆盖到镜头或有意处理；
4. 每条对白是否进入正式 dialogue inventory；
5. playback 是否完整、连续、不重复、不倒序；
6. 动作结果、因果、现实层和跨场状态是否在方案中成立；
7. director inference 是否被误写成来源事实。

## 5. 硬失败

- locked text 为空或哈希不匹配；
- source unit 漏失、行范围错误或 exact_text 不匹配；
- 对白、说话者、语言、来源声音、因果或动作结果被改写；
- 必须覆盖的单元既未覆盖也未有意处理；
- intentionally omitted / withheld 没有理由或破坏剧情事实；
- playback 不能重组为完整来源对白。

来源覆盖只存在于 director-workspace/3.1.0 和内部报告；不得增加正式 JSON 顶层字段、XLSX 工作表或第五个交付文件。
