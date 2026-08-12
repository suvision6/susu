# Emotion Visualization

本文件是来源可见表演优先级、抽象情绪外化条件、允许通道、禁止新增和派生审计的唯一规则源。

## 1. 决策顺序

逐镜执行：

1. 有非空 `performance.visible_behavior`：原样使用，不生成派生动作。
2. visible behavior 为空，但有明确 `emotion_intent`：允许最小 `emotion_visualization`。
3. 两者都没有：不增加情绪或表演。

不得为了“更有生命力”“更电影感”或模型偏好堆叠微动作。

## 2. 最小可见通道

只选择足以让当前抽象情绪可拍摄的一至两个低影响通道：

- 眉眼与视线；
- 下颌、嘴唇；
- 呼吸、吞咽；
- 肩颈、躯干；
- 手指、手掌；
- 重心、步伐；
- 已有人物距离中的轻微姿态变化；
- 已有动作内部的停顿或中断。

使用字面、可观察描述，避免比喻、象征和不可拍摄心理说明。不要引入毫米、角度、频率等伪精确数值。

## 3. 禁止新增

emotion visualization 不得新增或改变：

- 情绪阶段、情绪转折或强度走向；
- 人物目标、关系或说话内容；
- 地点、时间、现实层或人物位置；
- 道具、服装、伤势及其状态；
- 剧情动作、事件因果或结果；
- 景别、构图、机位、运镜、光线、天气、声音事件或转场。

不得让可见反应产生后续连续性负担，不得伪装为来源事实。

## 4. 决策数据

```json
{
  "emotion_visualizations": {
    "SH003": {
      "basis_emotion": "压抑和不安",
      "text": "呼吸变浅，视线短暂停在门口，下颌收紧。",
      "guardrails": {
        "adds_emotion_stage": false,
        "changes_goal_or_relationship": false,
        "changes_location_or_prop_state": false,
        "changes_plot_result": false,
        "adds_camera_or_environment_fact": false
      }
    }
  }
}
```

`basis_emotion` 必须逐字等于来源 `emotion_intent`。五项 guardrail 必须显式为 false。

## 5. Provenance

合法派生在 Cut 中登记：

```json
{
  "provenance": "derived_emotion_visualization",
  "basis_emotion": "来源抽象情绪",
  "text": "最小可见行为"
}
```

Prompt 可以使用 `text`，但输出合同仍把它标为下游派生。不得把该文字回写到 shot data 的 `visible_behavior`。

## 6. 失败处理

- 来源已有 visible behavior 又提供派生：`EMOTION_VISUALIZATION_FORBIDDEN`。
- 来源没有 emotion intent 却提供派生：`EMOTION_VISUALIZATION_WITHOUT_BASIS`。
- basis 不一致或 guardrail 不完整：`EMOTION_VISUALIZATION_INVALID`。

非法派生保持 decisions 原值和 hash，不做删字或改写；它带诊断且不进入 Prompt 正文。来源镜头和其他单元继续处理。

## 7. 语义责任

脚本只能验证触发条件、basis 字面一致、字段完整和 guardrail 声明。派生行为是否真的没有增加剧情或连续性事实，必须由执行本 Skill 的模型按本文件逐项审阅。
