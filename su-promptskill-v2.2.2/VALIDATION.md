# 2.2.2 验证记录

基线：suvision6/susu@868d795ee7a43d8ae41bdb465fc36d489b2cb77a，su-promptskill-v2.2.1。

命令：`python3 -m unittest discover -s <skill-root>/tests -v`。

17/17项离线回归通过，无失败、错误或跳过。覆盖30张库存/3张可访问、各单元独立范围、旧库存兼容、未知与明确空范围、无效类型、重复/未知/不可用tag、编号前缀冲突、采用排除冲突、非相邻镜、声明边界、精确小数、超限、未知时长、对白次数声位及文件只读。修改后的Python脚本通过语法检查。

脚本检查声明与字面一致性，不认证素材真的上传、身份读对、语义分组最优或视频效果。没有调用生成接口，没有在用户Mac/Codex/CodeBuddy运行完整创作。原Excel和格式后端继承基线，未重做所有客户端显示验收。

专业样例见tests/acceptance-cases.md。实现完成不等于全部样片验收通过，因此发布为candidate。保留su-prompt-plan/2.2与su-prompt-validation/2.2；旧validate仍只查旧文件一致性，不追认新语义或素材范围。
