---
name: su-promptskill
description: 将用户锁定的剧本、既有分镜与素材说明忠实转成自然中文视频提示词。由 Agent 写 Markdown 主稿并对照来源复核，再派生 JSON、Excel 与验证报告。适用于生成、编辑、延长和局部续做；来源只读，不擅自重新导演，不改原文对白，不把文件通过冒充语义或平台已验证。
---

# 视频 Prompt 转写与交付

版本：**2.1.0**。定位：受约束的中文转写，不是代码驱动的导演系统。

## 完成什么

把本次范围内的人物、事件、摄影、表演、声音和素材职责，写成清楚、自然、可执行的 Prompt。
**对白保原文，描述保事实。** 用户明确的编辑授权只作用于指定范围。
原始文件始终只读；不要求上游改名、升级或补内部合同。

## 开始之前

先完整读取原始来源和当前用户要求，不以摘要、已有输出或自己的记忆代替原文。
选择路径：已有分镜保留镜号、顺序和一源镜一 Cut；没有分镜的文本按来源事件表达，不虚构景别、运镜或精确时长；编辑／延长按实际母版和依赖执行。
载体不是 JSON 时，Agent 读取原载体后可以建立只读副本，保留原文、源段定位及来源说明。`prepare` 不会自动理解任意 Excel 或复杂剧本，不能拿它的原文草稿冒充完整分镜适配。

先读 [来源与任务](references/source-and-task.md)；写作前读 [中文与保真](references/chinese-fidelity.md)。
多镜需要组织时读 [单元与连续性](references/units-and-continuity.md)。
有抽象情绪才读 [情绪外化](references/emotion-visualization.md)。
有素材或平台要求时读 [平台与素材](references/platform-and-assets.md)。
准备导出时读 [输出与验收](references/output-and-review.md)。维护报告和测试不属于每次任务必读内容。

## 工作顺序

1. **锁定范围。** 分清原始来源、用户授权变更、素材观察和当前输出。未知信息保持未知。
2. **理解事实。** 读完整执行片段，识别主体、先后、同时、条件、否定、空间、对白事件及已有摄影事实。来源的执行说明可能包含结构化字段之外的独有事实，必须回读，不整段丢弃。
3. **组织单元。** 不确定是否适合合镜，就安全地逐镜输出。实际合并的边界只需具体理由和来源绑定；真实矛盾不能通过回退掩盖。
4. **写 Markdown。** 主稿是唯一可编辑正文。可以调整语序、补全已有且无歧义的主语、拆分长句；不能增添剧情、摄影或表演。一个 Cut 可有多个来源明确的阶段，也可以只是持续观察。
5. **独立回读原文。** 先查来源有没有遗漏，再查正文有没有无依据新增。不要用自己的初次提取列表充当原文。核对对白事件、时间关系、否定、方向和当前范围，特别检查未知字段及执行正文。
6. **冻结后导出。** Agent 完成核对即可记录复核，不要求用户逐段点击批准。导出器不再重写中文。重新读取保存文件，分别报告内容、提交、文件和阅读状态。

问题只影响相关单元和真实依赖。默认最多两轮定向修订；未解决的关键问题保留待复核，其他已通过部分继续。

## 正文写法

Prompt 内只写当前单元的执行内容。全故事梗概用于理解，不直接复制为每段生成目标。
参考素材、跨 Cut 声音桥和保持一致区块按实际需要出现，不填空壳；来源没写声音不等于静音。
对白采用可核对的简短形式，例如 `林晓彤（画外）：“我明天走。”`；引号中的载荷不改字。
只对原文已有的源镜使用 Cut；非分镜事件型输入无需伪造镜头编号。多源镜单元按 `Cut 1`、`Cut 2` 与来源依次对应。
用户的素材 tag 原样保留，模型／API 参数留在提交配置中。

## 实际入口

运行环境 Python 3.10+，不调用外部模型，不要求网络或凭证。

```text
python <skill-root>/scripts/prompt_delivery.py prepare --input <source.json> --output-file <draft.md>
python <skill-root>/scripts/prompt_delivery.py review-template --input <source.json> --master <master.md> --output-file <review.json>
python <skill-root>/scripts/prompt_delivery.py build --input <source.json> --master <master.md> --review <review.json> --output-dir <new-directory> [--decisions <context.json>] [--profile-id seedance-2.5-default|seedance-2.0-default|generic-video]
python <skill-root>/scripts/prompt_delivery.py validate --input <source.json> --output-dir <delivery-directory>
```

`prepare` 只供初始化，不替 Agent 写自然中文。Agent 编辑草稿、回读原文，再填 review 的实际复核者、状态和具体结论。未复核时照样保存正文，但不能标可提交。
`build` 不传 `--master` 仍接受可识别旧输入，产生保守逐镜草稿；这是兼容入口，不是自动导演或已批准成稿。
实际平台有经核实的配置时，使用 `--profile-file <profile.json>` 代替 `--profile-id`。默认 2.5 配置的完整平台参数仍属部分核实，不自动切换模型。

正式四文件仍为 `<前缀>-prompt-plan.json`、`<前缀>-prompt-table.md`、`<前缀>-prompt-table.xlsx`、`<前缀>-prompt-validation.json`。
Excel 续行只用于阅读，不新增 Cut、不重复计算时长；Excel 失败不抹掉主稿。

## 完成边界

机械检查、Agent 语义复核、平台条件、文件完整性和实际阅读效果各自说明。
不能从 hash 一致推出剧情正确；不能从脚本通过推出视频效果；不能把复核模板的 pending 改成通过而没有回读原文。
本版本为有本地验证记录的候选版本，尚未宣称完成 60 次全新上下文评测或视频实测。不自动替换全局安装，不覆盖旧版交付。
