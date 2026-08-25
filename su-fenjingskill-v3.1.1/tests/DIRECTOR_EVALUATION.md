# Director Evaluation｜3.1.0

机器测试只能证明来源、Gate、引用、播放和正式交付的确定性边界。以下评测需要导演、摄影师或具有剪辑判断能力的人工审阅。

## 评分维度

每项 0-2 分：

1. 剧本事实、因果、对白和声音完整；
2. 场景机制准确且不是题材标签；
3. 导演方法真实改变时间、边界、视点、空间、表演或声画；
4. 场级策略能解释机制与方法的结合；
5. 镜头拓扑与编辑关系不是默认 cut/hold/minimum-shots；
6. 摄影、调度、表演、声音和时长可执行；
7. 正式六列自然、可拍、无内部分析泄漏；
8. 正式四文件、两工作表和 3.1.0 合同稳定；制作风险不进入备注列。

任何来源改写、Gate 2 未确认或正式交付结构漂移直接判失败。

## 12 个创作案例

1. 厨房告别：是枝／诺兰／林奇三方法，同一来源必须产生实质不同拓扑。
2. 误会喜剧：图形舞台方法，验证 setup、误导、反应和反高潮。
3. 追逐营救：镜头内发现方法，验证方向、障碍、因果和镜内重构。
4. 门外威胁：镜头内发现方法适配 offscreen threat。
5. 家庭重逢：同一方法适配 relationship accumulation。
6. 聚餐类型转向：奉俊昊方法从喜剧转为群像权力／悬念。
7. 现实追逐到碎片记忆：同一主方法、逐场机制变化。
8. 长对白：完整长镜与 dialogue playback 多画面方案都必须成立。
9. 25 秒审讯长镜：不得因时长自动 FAIL。
10. 仪式／秘密行动：平行剪辑、声音桥、匹配和观念蒙太奇。
11. 来源遗漏：删除最后对白必须硬失败。
12. Near-neighbor：视频 Prompt 必须拒绝并保持正式分镜只读。

## 差异化判定

同一剧本的不同方法至少在以下三项中的两项不同：

- shot topology；
- time model；
- base editing unit；
- boundary priorities；
- audience knowledge path；
- space reveal；
- performance editing；
- sound-image relation；
- montage/intercut/jump/ellipsis usage。

只替换导演姓名、形容词、色彩、景别或运动术语，判 STYLE_ONLY_SWAP。

## 题材适配判定

同一方法处理不同机制时：

- 方法身份仍可辨认；
- 机制确实改变具体边界和节奏；
- 不把 action=快切、relationship=长镜、comedy=反应特写、suspense=隐藏全部信息当配方。

## Gate 判定

- 用户指定明确方法：Gate 1 可 user_specified。
- 未指定或有实质歧义：最多两个方法方案并确认 Gate 1。
- 所有新正式交付：Gate 2 confirmed。
- 来源或方法变化：两 Gate 失效。
- 机制、视点、时间或拓扑变化：Gate 2 失效。
- 仅精化执行文字：Gate 2 保持。

## 盲评

Yao Output Lab 的 A/B 包必须隐藏 v3.0.0 baseline 与 3.1.0 candidate 身份。审阅理由至少覆盖：剧本理解、方法差异、剪辑拓扑、可拍性和正式交付稳定性。未完成盲评必须标记 missing evidence，不计为人类同意。
