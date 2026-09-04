# Source Fidelity Adapters

本文件拥有上游形状识别、只读投影、事实所有权、冲突和静默遗漏边界。
它不决定导演事实、素材职责、合镜、模型 Profile 或输出样式。

## 1. 原则

1. 来源名称和版本只作 provenance；适配器按字段形状路由。
   缺少、未知或未来的来源名称、合同和版本不得阻断可识别形状。
2. 适配发生在深拷贝上，不改变来源对象、hash 或上游文件。
3. 结构化来源事实优先于人类渲染正文。
4. 一个事实只有一个 Prompt 正文 owner。
5. 已知非空字段不得静默变空。
6. 冲突必须诊断，不得拼接或选择更“好看”的版本。
7. 下游不得要求用户或上游迁移、改名、升版或补造 canonical 字段。

## 2. Director-shot-data 投影

识别 `shots[].staging`、`shots[].sound`、`shots[].camera`、
`shots[].continuity` 与 `shots[].execution_text` 的组合形状。

- staging 只提供当前源镜主体、走位和表演；`visible_subjects` 与
  `offscreen_subjects` 分别保留画内／画外职责，广义 `subjects` 只负责单元实体完整性；
- sound 只提供当前源镜对白片段、delivery、声音视点、音效、环境声和音乐；
- camera 只提供当前源镜摄影事实；
- continuity 只提供需要跨 Cut 继承的状态；
- execution text 是完整人类执行正文，但在 Prompt 编译时只作独有事实 fallback。
- edit 的入口、出口和下一关系只进入 `cut_design`，不得推导 camera start/end frame。

顶层 `source.dialogue_lines` 是对白字面和说话人权威。镜头片段不能改写文本、
说话人或来源 voice type。

## 3. Performance boundary

上游 staging performance 一经投影即为锁定 visible behavior。不得：

- 根据角色资料自动创建目标、策略、Beat 或潜台词；
- 强制加入眨眼、微眼跳、catchlight、吞咽、停顿或习惯动作；
- 把 Acting Profile 整段复制到每个 Cut；
- 把 Voice Profile 与 dialogue ledger 或音频职责重复输出；
- 用表演规则改变机位、灯光、色彩、素材或 Profile。

## 4. Execution boundary

第一可见画面、空间、朝向、视线、摄影、光学、物理、灯光、动作时点和声音
只有在来源或用户明确要求中存在时才可进入 Prompt。不得使用固定焦段表、固定距离、
导演／摄影师名、默认切法、默认无字幕／无音乐／禁口型或通用质量后缀补空缺。

首帧画面状态与首帧素材职责是两个事实域：前者来自导演来源，后者来自 mapped asset role。
未知 execution 区块不得通过整段 fallback 绕过结构化 owner。

## 5. Validation states

- `SOURCE_PRESENT`：来源结构存在且已投影；
- `REFERENCE_CARRIED`：显式 mapped 素材只按声明维度携带；
- `NOT_APPLICABLE`：当前镜头不需要该事实；
- `SOURCE_NOT_PROVIDED`：来源未提供，不补写；
- `MODEL_REVIEW_REQUIRED`：语义价值需人工／模型复核，不能伪装成确定性失败。

这些状态是审查语言，不自动增加正式 Plan 字段。若未来进入机器合同，必须另行版本化。
