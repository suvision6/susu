# Prompt Compiler

本文件是模型中立 Cut 正文、七维编译覆盖、state/delta 原则、受支持 adapter、anti-slop、字面保真和 Prompt 正文禁项的唯一规则源。

## 目录

- [编译顺序](#1-编译顺序)
- [编译覆盖面](#2-编译覆盖面)
- [State 与 Delta](#3-state-与-delta)
- [显式 Cut adapter](#4-explicit-cut-zh-v1)
- [内容映射](#5-内容映射)
- [受支持适配器](#6-受支持适配器)
- [Anti-slop 与 provenance](#7-anti-slop-与-provenance)
- [正文禁项](#8-禁止正文)
- [忠实性校验](#9-忠实性校验)

## 1. 编译顺序

1. 从标准化镜头建立模型中立的 Cut payload。
2. 从 `rendered_shot_description` 分离环境、摄影机描述、构图复述和可执行动作。
3. 用结构化 blocking、visible behavior、dialogue 与 continuity updates 补回主要描述中缺失的字面事实；`end_state` 保留在机器 provenance，不作为“镜头结束状态”写入正文。
4. 仅追加已通过审计的 emotion visualization。
5. 从 camera 读取角度、景别、运镜、构图、机位与 camera logic，不补默认摄影设计。
6. 应用 Profile 选择的受支持 adapter。
7. 对来源映射、对白和 metadata 泄漏做确定性复验。

## 2. 编译覆盖面

每个 Cut 以如下覆盖面检查信息是否已被来源或 reference 承载：

```text
Subject + Action + Scene + Camera + Lighting/Style + Audio + Constraints
```

这不是机械七栏模板。主体与主动作优先，所有有效槽位共同服务当前 Cut 的单一可见意图。只写来源实际提供或 reference role 明确承载的信息；没有灯光、风格、声音或约束就省略，不写默认值。

主要短语必须可见、可听，或可观察为运动、状态保持或物理变化。不得用抽象气氛替代执行信息。

每个 mode 都必须消费 `rendered_shot_description` 或可逐字段反查的结构化等价内容。若 reference 已承载静态状态，优先用 blocking、visible behavior、dialogue、continuity update 和 end state 表达动作与变化；只有来源未提供可分离的动态结构时，才以“来源动作与变化”逐字保留主要描述，防止主要动作丢失。

## 3. State 与 Delta

核心关系：

```text
reference/source carries state
prompt text carries delta
```

- `t2v`：来源文字承载完整可见状态；Prompt 把 scene context 独立写在 `场景` 行，把动作、必要连续性变化和可见道具写进对应 Cut 的 `画面内容`。
- `i2v`：image reference 承载已映射状态；不重述整张图，保留来源动作、时间、未承载 blocking、连续性变化、摄影机、声音与保持项。
- `v2v`：video reference 只按 role 提供已声明状态或运动；motion reference 不得提供身份，来源动作意图与变化仍需可反查。
- `r2v`：逐 tag 写明单一作用，Prompt 写未被 reference 承载的动作、blocking、对白关系与连续性 delta。
- `flf2v`：精确写出首帧 tag 与末帧 tag，保留二者之间来源已有的运动、对白时序、连续性变化与 Cut 链。
- `edit`：只把 `edit_deltas` 用作声明层修改，同时保留来源动作／时序、对白对象与连续性变化。
- `extend`：从已接受素材的观测结束状态继续，写来源延展动作与连续性 delta；不得补一个更方便的结束状态。

所有 reference tag 原样保留，不改写为通用 `@ImageN/@VideoN`。一个 Cut 只能使用 role map 中明确适用于该 source shot 且符合当前 Profile convention 的 tag。

## 4. `explicit-cut-zh-v1`

时长完整：

```text
总时长：11S
场景：赤狐岭 日 外，晨雾覆盖赤狐岭草坡。

Cut 1 : 0-5S
构图：【微仰视，大全景，极缓慢推进】晨雾横过草坡，人物立于树下。
画面内容：摄影机位于草坡低处，朝向树下人物；人物保持安静站姿。

Cut 2 : 5-11S
构图：【平视，全景，斯坦尼康跟随】人物从雾中进入并停下。
画面内容：摄影机位于人物侧前方，侧向跟住位移；人物接近目标时自然减速。
```

缺时长的合法单镜：

```text
总时长：来源未提供

Cut 1 : 时间未提供
...
```

未知时长明确保持“来源未提供”，不得伪造时间。正文不得重复来源镜号；来源映射只保留在表格 `来源镜号` 列和 plan timeline。

## 5. 内容映射

- 场景：读取 shot 自身材料及按 scene_id 关联的顶层 scene/location/time/environment；场号从人类可读场景名中移除，`reality_layer` 不写入正文。
- 构图：固定为 `构图：【angle，shot_size，movement】composition`；空字段省略，不补默认值。`position` 与 camera `logic` 不在这里重复。
- 画面内容：先写来源 `camera.position` 与 `camera.logic`，再写从 `rendered_shot_description` 去除场景、摄影机句和构图复述后的动作、表演、对白与必要声音。
- 对白：保留原 `text`，不得润色、合并、提前或改变说话人。
- 主体：读取来源 `visible_characters` 或独立输入的 `subjects`；若由 reference 承载则不重复描述。
- 主动作：优先读取 blocking、visible behavior 和显式 delta。
- 道具：读取 `visible_props`；主要描述已逐字包含时不重复。
- 连续性：静态 continuity 与 end state 保留在机器来源快照和 provenance；正文只写可执行的必要变化，不使用“现实层”“连续性初态”“镜头结束状态”等字段标签。
- 光线／风格：只读取来源显式值或 mode 允许的显式变化。
- 声音：逐字对白优先，再读取来源显式 audio/sound。
- 约束：只读取来源 constraints 与 role map 的 preserve 项。

结构化对象无法转为自然短句时，使用稳定紧凑 JSON 字面，不猜含义。

## 6. 受支持适配器

v1.0.0 支持：

- `explicit-cut-zh-v1`：完整场景行、阿拉伯数字 Cut 标题、统一构图行与单一画面内容行。
- `compact-cut-zh-v1`：保留同一信息与字段边界，使用紧凑排列；不恢复旧式重复字段。

adapter 只改变排列和标签，不改变分组、时长、Cut 数量或来源内容。

## 7. Anti-slop 与 provenance

Anti-slop 只约束下游新写的修饰性文字，绝不授权机械改写来源或已接受 decisions：

- `rendered_shot_description`、camera、blocking、visible behavior、dialogue、scene、audio、constraints、visible props、end state 等来源字段逐字保留有效内容。
- 来源对白“这是一部史诗”、物件“8K摄像机”或既有表演中的同字词不得删改。
- emotion visualization、edit delta、reference preserve 等 decisions 先保持原值；若含下游新增的疑似空泛强化词，拒绝该派生进入正文并给出诊断，不静默改写。
- 来源中的疑似词只产生 `SOURCE_ANTI_SLOP_REVIEW`，不得产生删字后的新来源版本。

执行模型可在不改变事实的前提下，把下游准备新写的“电影感、史诗、震撼、大师级、8K”等空泛质量按钮改为来源已支持的摄影机路径、物理光源、动作终点、声音或保持约束；来源不支持时不添加。

脚本只能按 provenance 区分来源携带与下游新增字面。只有无法追溯的下游新增强化词失败；“主要短语是否可观察”仍由模型语义审阅。

## 8. 禁止正文

Prompt 正文不得包含：

- 模型名称、profile ID、Skill 名称或版本；
- “我是 AI”“作为模型”等自我说明；
- 来源不存在的全局风格、灯光、天气、声音或负面指令；
- 自动增强冲突、电影感、人物张力或环境反馈；
- 管理过程、hash、校验意见和 source metadata；
- 不属于任何 Cut 的剧情头或剧情尾。
- `来源镜头`、`现实层`、`镜头结束状态` 字段标签；
- 独立的 `景别`、`角度`、`运镜手法` 行；
- 第二个 `画面内容` 或构图、场景、摄影机三要素的机械复述。

## 9. 忠实性校验

脚本可以证明：

- 编译使用的字段 hash；
- Cut 与 source shot 一一对应；
- 对白文本在对应单元正文中逐字存在；
- 生成器没有加入任意 Profile 文本；
- 正文没有已知模型身份和自我说明模式。
- 正文 reference tag 与当前 Cut role map 精确一致；
- 每个 Cut 的主要画面动作存在于正文，或由可逐字段反查的结构化等价内容承载；
- 必要 continuity update 未无痕丢失，同时静态状态不以旧字段标签回灌正文；
- 来源疑似词原样保留并进入审阅诊断；
- 下游新增且无法追溯的 anti-slop 强化词未进入正文。

模型必须审阅：

- 自然语言是否忠实表达来源动作和表演；
- 结构化补全是否重复或产生歧义；
- emotion visualization 是否越界；
- Prompt 是否适合所选模型执行。
- 编译短语是否都可见、可听或可观察为运动。

脚本不得用词面相似度冒充完整事实导演。
