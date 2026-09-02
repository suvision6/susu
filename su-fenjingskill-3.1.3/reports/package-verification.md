# Package Verification｜3.1.3 camera-grammar-01

隔离候选验证结果：**PASS**。当前版本、正式合同与内部合同均为 `3.1.3`；未安装、未发布、未覆盖全局 3.1.2。

## 已验证结果

- 单元与回归测试：121/121 PASS。
- Schema：两份 Draft 2020-12 Schema PASS。
- 示例：厨房 `READY`；未知房间 `READY_WITH_ASSUMPTIONS`。
- EP02 真实回归：从锁定原剧本独立生成 32 镜、38 句对白、91/91 required facts、199 秒，`READY`，四文件 parity PASS；未复用归档镜头数据或 14 镜拓扑。
- 摄影语法：14 单人、9 双人、4 过肩、2 插入、1 主观、2 群像；这些是事件驱动结果，不是类别配额。
- XLSX 前端：两张工作表、固定六列、十个全剧导演设计维度；六段后台标签、机器 ID、Gate/hash 和空值泄漏为 0。
- XLSX 实际渲染：6 页 A4 横向，逐页无截字、遮挡或异常空白页；冻结窗格、筛选和打印区域已检查。
- EP02 重复构建：JSON、Markdown、XLSX、validation 字节一致。
- Yao validate：PASS；初始加载估算 1239/1300 tokens。
- Skill IR 与 OpenAI/generic 编译：PASS。
- Output Eval：31 cases，with-skill 100%，0 regression；4 个摄影案例使用可解析结构结果。
- 下游只读检查：su-promptskill 对全新 EP02 的 32 镜 shape adapter PASS；su-image9 为既有旧 shape 不兼容，本次未修改。
- Trust 静态扫描：0 secrets、0 network scripts、5/5 CLI help smoke PASS；权限元数据保留非阻断 warning，不进入创作或四文件。

## 内容边界

- payload 文件数由最终 `PACKAGE_MANIFEST.json` 机械统计；`PACKAGE_MANIFEST.json` 与 `CHECKSUMS.sha256` 为自引用排除项。
- 不包含 `__pycache__`、`.pyc`、`.pyo`、Git 元数据或工作区抓取文件。
- 风险、安全与治理内容不进入创作流程和四文件；报告只作为候选包技术验证记录。

## 原子与版本边界

- `build-all` 在 staging 中完成 JSON、Markdown、XLSX 和 parity 后才写 validation，再原子提交整个目录。
- 迁移、构建、导出和审批写入均拒绝覆盖已有目标。
- 3.1.2→3.1.3 只生成新目录 draft，不猜 shot_flow、新切点、画面所有权、framing 或可见／画外主体，所有 Gate 与 Alignment 重新确认。
- 安装和 GitHub 发布不属于本候选验证，需另行明确授权。
