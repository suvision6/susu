# Package Verification｜3.1.4 projection-quality-02

隔离候选技术验证结果：**PASS**。当前版本、正式合同与内部合同均为 `3.1.4`；已安装并发布的全局 3.1.3 保持只读，3.1.4 尚未安装或发布。

## 已验证结果

- 单元与回归测试：148/148 PASS。
- Schema：`director-shot-data/3.1.4` 与 `director-workspace/3.1.4` PASS。
- Gate 0：节奏预设、目标时长、画幅、方向、对白速度与覆盖倾向进入 format hash 和四阶段失效矩阵。
- 对白剪辑：每个来源对白恰好进入一次 dialogue edit plan；静态 O.S. 留镜失败，持续产生新可见发展的留镜通过。
- 多人对白：倾听者和权力中心缺失时阻断。
- 画幅：9:16 横移不被类别禁用，但空泛画幅理由阻断；frame axis 与 Gate 2/正式 camera 双向一致。
- 时长：timing blocks 无缝覆盖 shot_flow；parallel 取最长、sequential 相加；中文对白按 Gate 0 参数重算。
- 对白速度：`su-dialogue-pace/1.0` 固定四类区间与默认值；非自定义预设不得改写区间，越界必须使用有明确作用域和理由的 override；每个对白时间块必须引用 `BASE` 或具体 override。
- 前端减冗：机位重复摄影头、构图／flow owner 复述同一事件、模板焦点和同场重复普通环境／焦点／出口均阻断；不设置通用字数上限。
- 景别术语：正式 camera 与 XLSX 只接受规范中文景别及 `→` 转写；“紧中景”触发 `SHOT_SIZE_TERM_NONSTANDARD`。
- 示例：厨房 `READY`；未知房间 `READY_WITH_ASSUMPTIONS`；双次四文件构建字节一致。
- XLSX：两张工作表、固定六列、十个全剧导演设计维度；标题区显示画幅、节奏、对白速度；实际 Calc 两页渲染无截字或遮挡。
- Yao validate：PASS；初始加载估算 1297/1300 tokens。
- Skill IR：PASS。
- Output Eval：38 cases，with-skill 100%，0 regression。
- Trust：0 secrets、0 network scripts、6/6 CLI help smoke PASS；权限元数据保留非阻断 warning，不进入创作或四文件。

## 迁移与版本边界

- `3.1.3 → 3.1.4` 只写新空目录，产出 schema-valid unresolved draft。
- 不猜节奏、画幅、对白速度、遗漏切点、frame axis 或 timing blocks。
- Gate 0、Gate 1、Gate 2 与 Alignment 全部失效，迁移 draft 不能正式构建。
- 历史 3.1.2→3.1.3 与更早迁移器继续保留原行为。

## 未完成的真实回归

EP02 不能继承 3.1.3 的 32 镜拓扑。必须先由用户为该项目确认 3.1.4 Gate 0 的节奏预设、目标成片时长、画幅和对白速度参数，再从锁定剧本重新建立 dialogue edit plan 与 topology。
