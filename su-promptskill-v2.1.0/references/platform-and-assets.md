# 平台与素材

模型／平台硬限制、本 Skill 的规划偏好、推荐写法必须分开。参数集中在 profiles.json 或本次自定义 Profile，不在主规则重复。

默认保留 Seedance 2.5 名称和模型选择，不自动退回其他模型。2026-09-05 读取的官方产品页支持“Seedance 2.5、30 秒叙事”，官方体验 URL 使用既有模型 ID；完整 API 限制未在本次读取中完成核实，因此默认 verification.status=partial，不冒称全部参数已验证。10 Cut 是历史本地规划值，不是本次已核实的官方限制。
Seedance 2.0 兼容配置亦须按实际平台核实。generic-video 不虚构统一时长和 Cut 上限。

自定义 Profile 至少有 profile_id、planning_limits；已核实的平台同时记录 verification 的 status、platform、checked_at、sources。平台字段存在不代表程序已联网认证；必须有真实查证或用户确认依据。
可声明 request_constraints、max_prompt_characters 等实际条件。来源时长、模型请求时长各自保存；不把请求参数写进 Prompt。

素材按用户明确指定职责优先，再参考描述、可见／可听内容、元数据和顺序。标签原样保留，不把单人照片当成多个人物的身份凭据。
库存记录 tag、media_type、available 和观察依据；职责记录 tag、target_entity、role、采用维度和 applies_to_shot_ids。程序不自动观看照片或视频，available=true 必须来自实际观察或用户确认。

first_frame／last_frame 必须明确是首尾帧，不降级为普通外观参考；edit_source／extension_source 必须唯一且真实可用。角色互斥、数量、分辨率等按照实际平台规则复核，未核实不冒称就绪。
非核心、未引用的缺失素材不妨碍独立单元。正文仍引用不存在素材时，应由 Agent 修改主稿去掉引用；导出器不能偷偷改文字。

超字符限制只允许保真的语言优化或经许可的单元调整；不能自动删对白、事件、否定或必要状态。
本 Skill 不执行付费生成，不调用平台 API，也不把待生成的 operation 输出伪装成现有视频。
