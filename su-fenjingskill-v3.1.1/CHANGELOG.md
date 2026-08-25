# Changelog

## 3.1.1 — Chinese Contract Synchronization Patch

### Changed

- Set the Skill package and source metadata to 3.1.1 while preserving the formal `director-shot-data/3.1.0` contract.
- Kept production risks in `production_risks[]` and outside the six-column remarks field.
- Preserved Chinese speaker-label separation, full-width punctuation fidelity, permissive playback-floor checks and CJK execution-text validation.
- Kept four files, two XLSX sheets, six columns, Gate behavior and reverse source coverage unchanged.

### Governance

- Version 3.1.1 is the user-selected release boundary.
- The prior 3.1.0 candidate and installed 3.1.0 baseline remain preserved in parallel.
- Any disagreement from automated semantic-version recommendations remains visible in the governed upgrade report.

## 3.1.0 — Scene-Mechanism and Director-Method Architecture

### Changed

- Replaced the universal minimum-shot start with a seven-layer source → mechanism → method → strategy → shot/edit → execution → delivery architecture.
- Unified the formal output contract and source Skill identity at director-shot-data/3.1.0 while retaining four files, two XLSX sheets, six columns, and READY / READY_WITH_ASSUMPTIONS / FAIL.
- Made director methods own time models, editing units, boundary priorities, hold conditions, montage/intercut behavior, viewpoint, space, performance, camera, sound, and continuity attitudes.
- Split intra-shot development from inter-shot editing; added jump cut, ellipsis, intercut, montage, sound lead/lag/break, and method-specific boundary reasoning.
- Added adaptive Gate 1 and mandatory Gate 2 without restoring old confirmation parsing or public digests.
- Moved reverse source coverage and review locks into internal director-workspace/3.1.0.

### Added

- Ten scene mechanisms with primary/secondary per-scene routing.
- Fifteen executable director-method cards.
- Internal source-unit, dialogue, Gate, method, strategy, and topology validator.
- Gate invalidation tests and artistic non-failure regressions.
- Chinese-context rules for speaker-label separation, full-width punctuation fidelity, natural execution prose, and permissive physical dialogue-playback checks.
- Structured `production_risks[]` with separate Markdown and XLSX presentation; production risks no longer enter the remarks column.
- Governed output-eval cases for contract identity, Chinese dialogue context, and production-risk routing.

### Removed

- Default cut, default hold, and universal minimum-shot logic.
- Six-axis profile as the final representation of director method.
- Any artistic hard failure based only on shot seconds, density, fixed camera, angle, movement, or composition.
- Internal source coverage and Gate material from formal delivery.

## 3.0.0 — Director & Cinematographer Rebuild

### Changed

- 认知架构从“来源锁定 → Gate → 屏幕事件 → 合同闭合”重构为“导演读场 → Blocking → 空间／视点 → 摄影 → 镜头动机 → 剪辑／声音 → 交付”。
- 将 Schema、脚本、校验和文件命名从最高优先级降为后端实现层。
- 删除默认双 Gate、stage digest、确认意图解析和强制三候选导演风格流程。
- 删除“说话者／观看主体／尺度变化先默认切镜”的核心假设。
- 镜头结构以 `motivation` 为中心；每镜说明为何存在、为何从此处观看、为何此时切或不切。
- 摄影设计增加机位、透视、构图、焦点、光线、色彩与声音视点的导演化判断。
- 连续性改为风险型台账；允许有动机的越轴、方向反转和跳切。
- 输入支持 `concept_board`，不再要求完整剧本或外部编号才能继续。
- 缺失信息改为假设清单与 `READY_WITH_ASSUMPTIONS`，WARN 不阻断交付。
- 输出合同精简为 `director-shot-data/3.0.0`。
- 保留六列交付：镜号、场景、原剧本段落、镜头时长、运镜＋主画面描述、备注。

### Added

- 导演宪法与镜头删除测试。
- Blocking、空间拓扑和观众位置方法。
- 摄影师视角的焦段／透视、构图、焦点、光线与色彩设计。
- 声音视点、画外空间和声画连接方法。
- Coverage 与设计型分镜的明确边界。
- 优雅降级协议、假设对象和软失败构建。
- 轻量 Schema、后端校验器、Markdown 构建器、artifact_tool XLSX 导出器和基础测试。

### Preserved

- 原剧本事实与逐字对白保护。
- 对白跨镜连续播放能力。
- 生产可执行的镜头时长、场面调度、连续性和六列表格。
- JSON、Markdown、XLSX、validation 多载体交付方向。

### Compatibility

- v2.5.8 原目录、旧合同和旧脚本不修改。
- v3 为并行重大版本，不覆盖旧项目。
