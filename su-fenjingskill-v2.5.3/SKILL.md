---
name: su-fenjingskill
description: 将完整剧本、未编号剧本段落，或边界明确的连续场景片段转换为生产可执行的六列导演分镜和 shot-data/2.5.3 结构化交付。用于锁源、识别来源声音与屏幕事件、以切／留／镜内重构建立观看路径、完成三候选导演风格确认和 DOP 镜头设计，并落实轴线、视线、表演、阶段时长与必要连续性；不用于视频 Prompt、模型配置或合镜分组。
---

# 导演分镜

## 职责与边界

- 当前 Skill 与正式合同版本统一为 `2.5.3`；内部规则修订号为 `2.5.3-binding-integrity-r1`。该修订号进入 Gate 2 digest，因此旧规则修订产生的 Gate 2 确认全部失效。
- 接受完整剧本、未编号剧本段落，以及用户明确提交或锁定边界的连续台词／场景片段；不要求外部场号、剧本编号或既有 `scene_id`。
- 只有梗概、零散设想或无法确定连续原文边界时，拒绝正式拆镜；用户明确把该文本本身锁定为待拆片段后才可继续。
- 把锁定文本视为内容权威：逐字、逐语言保留对白，不翻译、转写或改换语言；不改变剧情事实、因果、人物关系、关键动作、道具状态与现实层。只有用户明确追加翻译需求时，译文才作为独立辅助内容出现，绝不替换来源对白。来源把两种语言并列却未明确原文／译文身份时必须暂停并请用户确认，不得凭排版、字符体系或上下顺序推断。
- 允许与来源一致、不制造新剧情事实的可逆表演和调度选择；把它们留在导演字段，不得冒充 source fact。
- 只负责导演分镜；不生成视频 Prompt，不配置模型，不规划下游 Cut 链或多镜生成分组。

## 必读路由

进入对应阶段前，完整读取其语义权威文件：

| 阶段 | 文件 | 唯一职责 |
| --- | --- | --- |
| 锁源与事实 | [source-and-beat.md](references/source-and-beat.md) | 输入边界、文本锁、source span、Beat、受保护事实与事实覆盖 |
| 屏幕事件与观看决策 | [screen-event-and-cut-map.md](references/screen-event-and-cut-map.md) | 屏幕事件、切／留／镜内重构及其与规划单元的确定关系 |
| 导演风格 | [director-profile.md](references/director-profile.md) | Gate 1、15 位导演路由、三候选比较、候选选择与唯一确认 |
| 规划与拆镜 | [shot-design.md](references/shot-design.md) | 整场理解、完整过程、切与不切、Gate 2、摄影机、调度与时长 |
| 角度与摄影机运动执行 | [angle-and-camera-execution.md](references/angle-and-camera-execution.md) | 角度、位置、构图与运动动机的一致性审计 |
| 对白调度 | [dialogue-staging.md](references/dialogue-staging.md) | 发言权、画面所有权、声音位置与特殊观看策略 |
| 情绪与表演 | [performance-arc.md](references/performance-arc.md) | 可见表演、阶段分析与跨镜继承 |
| 连续性 | [continuity-contract.md](references/continuity-contract.md) | 必要状态追踪、轴线、方向与动作接续 |
| 数据与交付 | [output-contract.md](references/output-contract.md) | shot-data/2.5.3 到四文件的交付映射、两 Gate digest、六列与报告 |

结构与语义按以下优先级裁决：

1. `scripts/contract_schema.py` 及其导出的 [shot-data.schema.json](references/shot-data.schema.json) 唯一拥有字段、必填／可选、基础类型和闭合对象结构。
2. 上表 owner reference 唯一拥有对应领域语义；不要在其他文件重定义 owner 细则。
3. [output-contract.md](references/output-contract.md) 只拥有结构化事实到 JSON、Markdown、Excel、报告和 CLI 的交付映射。
4. `scripts/storyboard_delivery.py` 执行跨对象、digest、连续性和导演可执行性审计；它不得创造与 Schema 或 owner reference 竞争的公开合同。

发生规则竞争时依次保护：锁定来源与对白语言、人工 Gate 绑定、事件与剪切原子性、连续性、已确认 DOP 规划、场级风格锚点、统计复核。下游交付便利不得反向覆盖上游事实或确认。

## 工作流

### 1. 锁源与 Gate 1

1. 锁定全文、批准修正、边界与 hash；缺少外部编号时按来源顺序生成稳定内部 ID。项目可一次确认 `project_dialogue_language_policy`；各集默认继承，只有出现与项目策略不同的语言角色时才以本集 `dialogue_language_policy` 重新确认例外。没有项目策略时，检测到相邻双语台词候选便先锁定本集策略：原文与译文并列时使用 `original_with_translation`；两种语言都是角色实际说出的台词时使用 `multilingual_actual`。来源不能明确证明角色时暂停并取得用户确认，把确认同时写入 `approved_corrections`；语言角色未锁定不得进入 Gate 1。
2. 内部提取场景的风格需求；用户未指定导演时，按 [director-profile.md](references/director-profile.md) 默认展示主选、替代、对照三个完整候选。用户指定导演时直接编译该风格。
3. 用户选择候选后，单独展示最终 `director_profile`；STYLE／MORE 选择只是普通选择，不是 Gate，也不等于确认。
4. 只有用户看到最终 `director_profile` 后明确说“确认”，才把实际展示的 Gate 1 材料绑定到 digest；绑定成功后自动进入并展示 Gate 2，不等待“继续”。

### 2. 整场规划与 Gate 2

1. Gate 1 后建立 Beat、受保护 facts 与逐字锁定的 `script_voice_type`；VO、OS 与现场对白不得根据相邻人物或反应对象推断。
2. 把来源事实转译为原子 `screen_events[]`：先按发言权、主要观看主体、观看尺度、信息落点和动作发起者拆开，再讨论镜头。
3. 为同场每对相邻事件先建立默认 `cut` 边界；只有连续动作、遮挡证明、倾听者所有权、V.O./O.S.、共享调度、延迟反打或真正同时事件具有明确收益时，才以带 `non_cut_basis` 的 `hold | reframe` 撤销切点。
4. 把 Gate 1 profile 编译为场级视听语法：每场至少一个 `directing_plan.style_anchors[]`，明确时间组织、摄影机参与、空间揭示、表演距离和声音策略。逐镜 `style_anchor_ids[]` 可省略，只在关键应用、有意例外或命中风格复核时登记。
5. 为每个规划单元完成 DOP 设计：观看主体、景别、角度、机位、构图关系、透视、焦点、空间策略、运镜计划、起始画面、结束画面和动机。
6. 景别不由物理距离机械决定。空间两端人物可分别使用近景或特写；检查的是既定空间、视线、轴线、银幕方向和切换是否成立。
7. Gate 2 按场展示视觉与声音策略、屏幕事件、切／留／重构地图、DOP 镜头表和执行风险；全部场次展示完成后只确认一次，并自动生成最终交付，不等待“继续”。

### 3. 最终分镜与交付

1. Gate 2 确认后直接生成最终分镜，不等待“继续”，也不设置第三个人工 Gate；改变镜头单元、顺序、剪切点或任何核心 `visual_plan` 时重新 Gate 2。
2. 终稿逐镜严格落实已确认的 DOP `visual_plan`；`camera` 必须逐项绑定观看归属、主次主体、景别、角度、机位、构图、透视、焦点、空间策略、完整运镜计划、起止画面和动机。只能精化不与这些字段冲突的执行文字。
3. 每镜用有序 `shot_phases[]` 表达镜内时间。第五列自然语言必须依次读出初始画面、镜内动作／焦点／摄影机变化和结束画面，但不显示“起幅／过程／落幅”标签。
4. 第五列镜头头严格为 `【景别｜角度｜运镜】`：景别、角度、运镜只写各自纯摄影元素。机位、构图、主体、焦点与空间策略保留在 DOP 结构及自然语言画面内容中。除通用标准术语和原剧本输入中逐字出现的内容外，画面描述词默认使用中文；不得把内部英文枚举或字段名写入正文。正文不得出现“所在区域”“处于主要观看位置”等模板套话。第六列备注固定留空，作为人工预留列；声音、表演与连续性写入第五列或对应结构化字段。
5. 在 `source.delivery_slug` 中明确写入不超过 80 字符的 ASCII 小写 kebab-case 标识；四文件名固定由该值派生为 `{delivery-slug}-shot-data.json`、`{delivery-slug}-storyboard.md`、`{delivery-slug}-storyboard.xlsx` 与 `{delivery-slug}-storyboard-validation.json`。可从用户元数据或首行提取编号和已有罗马字；中文标题没有可靠罗马字时询问用户，不得假装脚本会自动生成拼音。
6. 读取 [output-contract.md](references/output-contract.md) 构建并独立校验四文件。JSON 是机器事实源；任何 FAIL 停止正式交付。WARN 仍写入完整四文件，但 `build` 返回退出码 `2`，自动化不得当作成功。

## 不可违反

- Beat、Fact、台词句数和人物数量都不等于镜头数。
- 每次说话者改变默认形成新事件与切镜边界；同一人物的一次完整发言不得按标点、停顿或排版机械拆分。
- 主要观看主体、观看尺度、认知落点或动作发起者改变时先拆事件；人物、物件细节与人物反应不得被一句“观看任务单一”强行合并。
- 普通剧情镜不得超过 10 秒。超过 10 秒只能使用有结构化收益和受保护事件范围的 `long_take`；若仍包含发言权、多个观看主体、尺度、认知落点或多个顺序动作变化，必须拆镜。
- `director_analysis` 不得进入 source facts 或对白。
- 每刀必须有具体触发和剪辑收益，不能只写类别词或“换景别”。
- 每个规划单元必须绑定一个或多个屏幕事件；逐镜风格锚点按需使用，不得为了填字段机械复制。
- `screen_event.beat_ids` 必须精确等于其 `covered_fact_ids` 所属 Beat；同场事件、规划单元内事件和 `shot_phases` 都必须保持 `event_order`，导演性倒序只能拆成多个规划单元并显式登记 `reorder`。
- 来源说话者及 `script_voice_type` 不得改写；来源 VO 永远不能被摄影设计改成现场对白或 O.S.。
- 人物台词必须保持原剧本中的文字与语言；未经用户明确追加翻译需求，不得翻译、音译、转写或用另一种语言替换。
- 双语并列台词不得凭中文在前、英文斜体、角色名写法或其他版式推定主次；未形成有效语言角色合同即 FAIL。
- 第五列除通用标准术语和原剧本逐字内容外默认使用中文；内部英文枚举、字段名和机器状态不得进入【画面内容】。
- 第六列备注必须为空字符串，作为人工预留，不得由 Skill 自动填写。
- 运动镜必须有触发、速度、路径和停止条件；固定镜头必须写明保持原因。
- 顺序事件必须进入不同阶段；影响后镜的人物、道具、视线、姿态或在场状态变化必须登记连续性更新。
- 同一镜头覆盖多个空间区域时必须有可执行空间策略；分别使用近景或特写时只检查轴线、视线与银幕方向，不做距离禁令。
- Gate 2 是核心视觉决策，不得称为“抽象规划”“大致方向”或暗示视角、景别、构图、主体、位置和运镜类别仍由终稿决定。
- 终稿任一 DOP 绑定字段与 Gate 2 `visual_plan` 不一致即 FAIL；不能靠同时改写事件列表、阶段列表、终稿 camera 或重算 digest 绕过规划审计。
- 剧情事实必须由镜头覆盖；覆盖关系不要求逐字段重复举证。
- 已追踪连续性必须继承；有意越轴或断裂必须明确声明。
- STYLE／MORE 选择不是 Gate；只有最终 `director_profile` 的一次 Gate 1 确认和整场规划的一次 Gate 2 确认。
- 两个 Gate 的确认都自动推进下一阶段；正常流程不得插入“继续”或第三次确认。“继续”只可恢复系统已明确声明的异常暂停，不能代替任一 Gate 的“确认”。
- 两个 Gate 只记录当前阶段的明确确认，不认证用户身份；受绑定内容变化时旧 digest 失效。
