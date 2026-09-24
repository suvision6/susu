# 2.4.2 验证记录

基线：suvision6/susu@868d795ee7a43d8ae41bdb465fc36d489b2cb77a，su-image9-v2.4.1。

命令：`python3 -m unittest discover -s <skill-root>/tests -v`。

18/18项离线回归通过，无失败、错误或跳过；测试时Pillow可用。覆盖整页/单格范围、当前时点与归档分离、逆序回补、旧稿及未知/重复/空小节兼容、围栏标题、源文件不覆盖、全页TXT/JSON/阅读稿同文、执行依据一致性、旧清单与原spec摘要兼容、策略/参考变更失效、缺图不批准、r02待审及未改图片保留。修改后的Python脚本通过语法检查。

测试中的纯色90×160 PNG只是文件与版本机制夹具，不是故事板，不是模型输出。测试里的approved及证据明确标为TEST ONLY模拟数据，不代表真实用户批准任何图像。

未调用生图/视频服务，未在用户Mac/Codex/CodeBuddy进行完整创作，未运行最终PDF渲染和客户端视觉验收。原coverage、主稿解析、画法与PDF排版后端直接继承，不将本次局部测试说成全面认证。

tests/acceptance-cases.md列出专业/视觉目标，尚需真实创作观察。脚本不认证身份、空间、时点语义或宿主实际传输；版本保留candidate。状态档案仍可在原主稿回读，但实际调用只应传prompt与真实附件。
