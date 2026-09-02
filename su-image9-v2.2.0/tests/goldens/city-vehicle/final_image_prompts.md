# PAGE-01

DELIVERABLE:
@CANON(HARD_PHRASES)

SYSTEM_STYLE_LAYER:
@CANON(SYSTEM_STYLE_LAYER)

SOURCE_BINDING_LAYER:
This page is bound to source shots C001, C002.
The structured panel plan is the only machine fact source; this Prompt must not override it.
Reference asset state: none.

SCENE_LAYER:
Scene S01; reality layer: 现实.
Source scene heading: 1 城市街道 日 外.
Registered spatial axis: A与B保持同侧关系，A从起点移向终点，摄影机不跨轴。.
Registered fixed geometry: 道路边线; 路灯.
Registered character placement: A: position 路边, facing B; B: position 车头一侧, facing A.

CAMERA_RULE_LAYER:
Preserve every source shot camera tag and source order; a derived angle may change only angle, shot size, or composition emphasis.
C001: source camera 平视, 双人中景, 固定镜头; Composition: （A在路边轿车驾驶门外，B在车头一侧，两人同处轴线一侧。）; Camera motion idea: 固定镜头; Visible action state: A和B站在路边轿车旁，A握着车钥匙。
C002: source camera 侧面平视, 双人中景, 横移跟拍; Composition: 可见主体：A、B；可见道具：轿车、车钥匙。; Camera motion idea: 横移跟拍; Visible action state: A到达驾驶门边仍握着车钥匙，B说：“出发。”

CONTINUITY_LAYER:
Visible character boundary: A、B.
Visible prop boundary: 轿车、车钥匙.
Derived panels inherit the exact Beat, fact, action phase, emotional result, and continuity-state hash of their source panel.
Position and facing transitions follow only continuity_updates; never infer a distance endpoint from action keywords.
Render_delta=allowed means a derived panel may crop, obscure, or frame a subset of the source visible set; story_delta must remain none.

PAGE_SPATIAL_ANCHOR:
Use PANEL-1 / C001 as this page's declared spatial anchor.
Panel 1 still preserves its original director-approved source camera and composition; do not widen or redesign it to manufacture an anchor.
All angles remain on the registered side of the axis and may reveal only registered geometry.

FIXED_GEOMETRY_LOCK:
@CANON(GEOMETRY_BLUEPRINT)
Source-defined fixed geometry for this page: 道路边线; 路灯.

VEHICLE_AND_AXIS_LOCKS:
Preserve registered eyelines, facing, side-axis relationships, and screen-left/screen-right continuity.
Registered vehicles or transport objects: 轿车. Preserve their registered positions and states only.

OBJECT_VISIBILITY_AND_BOUNDARIES:
Draw only these visible registered props when their source panel calls for them: 轿车、车钥匙.
Offscreen voices and characters remain outside the frame unless that source panel lists them as visible.

PANEL_LAYER:
PANEL-1: Draw 平视, 双人中景, 固定镜头. Composition: （A在路边轿车驾驶门外，B在车头一侧，两人同处轴线一侧。）; Camera motion idea: 固定镜头; Visible action state: A和B站在路边轿车旁，A握着车钥匙。 Visible characters: A、B. Offscreen characters must remain outside the frame: none. Visible registered props: 轿车、车钥匙. Distance/position stage: pre-transition: keep A.position at 路边 before C002. Primary focus: A、轿车. Must show: A、B、轿车、车钥匙. May show: none. Must not show: none. Render delta: none; story delta: none. Camera rationale: 源镜头，保留导演原始构图与可见集合。 Do not add another action phase, character, prop, emotion result, or spatial fact.
PANEL-2: Draw action start moment derived from 平视, 双人中景, 固定镜头. Freeze the representative instant at the start of the action progression, before the main movement begins. Preserve the source state exactly: Composition: （A在路边轿车驾驶门外，B在车头一侧，两人同处轴线一侧。）; Camera motion idea: 固定镜头; Visible action state: A和B站在路边轿车旁，A握着车钥匙。 Visible characters: A. Offscreen characters must remain outside the frame: none. Visible registered props: none. Distance/position stage: pre-transition: keep A.position at 路边 before C002. Primary focus: A. Must show: A. May show: B、轿车、车钥匙. Must not show: none. Render delta: allowed; story delta: none. Camera rationale: 动作起点瞬间，保留动作开始前的代表性姿态。 Do not add another action phase, character, prop, emotion result, or spatial fact.
PANEL-3: Draw action process moment derived from 平视, 双人中景, 固定镜头. Freeze the representative instant in the middle of the action progression, showing clear movement direction. Preserve the source state exactly: Composition: （A在路边轿车驾驶门外，B在车头一侧，两人同处轴线一侧。）; Camera motion idea: 固定镜头; Visible action state: A和B站在路边轿车旁，A握着车钥匙。 Visible characters: A. Offscreen characters must remain outside the frame: none. Visible registered props: none. Distance/position stage: pre-transition: keep A.position at 路边 before C002. Primary focus: A. Must show: A. May show: B、轿车、车钥匙. Must not show: none. Render delta: allowed; story delta: none. Camera rationale: 动作过程瞬间，展示明确的方向和动势，但不到达终点。 Do not add another action phase, character, prop, emotion result, or spatial fact.
PANEL-4: Draw action end moment derived from 平视, 双人中景, 固定镜头. Freeze the representative instant at the end of the action progression, showing the result posture without adding emotional aftermath. Preserve the source state exactly: Composition: （A在路边轿车驾驶门外，B在车头一侧，两人同处轴线一侧。）; Camera motion idea: 固定镜头; Visible action state: A和B站在路边轿车旁，A握着车钥匙。 Visible characters: A. Offscreen characters must remain outside the frame: none. Visible registered props: none. Distance/position stage: pre-transition: keep A.position at 路边 before C002. Primary focus: A. Must show: A. May show: B、轿车、车钥匙. Must not show: none. Render delta: allowed; story delta: none. Camera rationale: 动作终点瞬间，保留结果姿态，不添加情绪后果。 Do not add another action phase, character, prop, emotion result, or spatial fact.
PANEL-5: Draw same-side profile view derived from 平视, 双人中景, 固定镜头. Use a profile view from the established side of the axis without reversing screen direction. Preserve the source state exactly: Composition: （A在路边轿车驾驶门外，B在车头一侧，两人同处轴线一侧。）; Camera motion idea: 固定镜头; Visible action state: A和B站在路边轿车旁，A握着车钥匙。 Visible characters: A. Offscreen characters must remain outside the frame: none. Visible registered props: none. Distance/position stage: pre-transition: keep A.position at 路边 before C002. Primary focus: A. Must show: A. May show: B、轿车、车钥匙. Must not show: none. Render delta: allowed; story delta: none. Camera rationale: 同侧侧面，强调运动方向或空间深度，不跨轴。 Do not add another action phase, character, prop, emotion result, or spatial fact.
PANEL-6: Draw 侧面平视, 双人中景, 横移跟拍. Composition: 可见主体：A、B；可见道具：轿车、车钥匙。; Camera motion idea: 横移跟拍; Visible action state: A到达驾驶门边仍握着车钥匙，B说：“出发。” Visible characters: A、B. Offscreen characters must remain outside the frame: none. Visible registered props: 轿车、车钥匙. Distance/position stage: endpoint-transition: A.position 路边 -> 驾驶门边 (evidence: B002-F01). Primary focus: A、轿车. Must show: A、B、轿车、车钥匙. May show: none. Must not show: none. Render delta: none; story delta: none. Camera rationale: 源镜头，保留导演原始构图与可见集合。 Do not add another action phase, character, prop, emotion result, or spatial fact.
PANEL-7: Draw same-side over-shoulder view derived from 侧面平视, 双人中景, 横移跟拍. Use an over-shoulder view only between the already visible characters; preserve eyelines and screen sides. Preserve the source state exactly: Composition: 可见主体：A、B；可见道具：轿车、车钥匙。; Camera motion idea: 横移跟拍; Visible action state: A到达驾驶门边仍握着车钥匙，B说：“出发。” Visible characters: A、B. Offscreen characters must remain outside the frame: none. Visible registered props: none. Distance/position stage: endpoint-transition: A.position 路边 -> 驾驶门边 (evidence: B002-F01). Primary focus: A、B. Must show: A、B. May show: 轿车、车钥匙. Must not show: none. Render delta: allowed; story delta: none. Camera rationale: 双人过肩，保留说者与听者的空间关系和视线方向。 Do not add another action phase, character, prop, emotion result, or spatial fact.
PANEL-8: Draw speaker close-up derived from 侧面平视, 双人中景, 横移跟拍. Isolate the speaking character on the established side of the axis; keep the addressee off-screen or only partially visible. Preserve the source state exactly: Composition: 可见主体：A、B；可见道具：轿车、车钥匙。; Camera motion idea: 横移跟拍; Visible action state: A到达驾驶门边仍握着车钥匙，B说：“出发。” Visible characters: A. Offscreen characters must remain outside the frame: none. Visible registered props: none. Distance/position stage: endpoint-transition: A.position 路边 -> 驾驶门边 (evidence: B002-F01). Primary focus: A. Must show: A. May show: none. Must not show: B. Render delta: allowed; story delta: none. Camera rationale: 说话者近景，保留台词落点时的表情与语气线索。 Do not add another action phase, character, prop, emotion result, or spatial fact.
PANEL-9: Draw listener reaction close-up derived from 侧面平视, 双人中景, 横移跟拍. Isolate the listening character on the established side of the axis; show reaction without advancing the dialogue fact. Preserve the source state exactly: Composition: 可见主体：A、B；可见道具：轿车、车钥匙。; Camera motion idea: 横移跟拍; Visible action state: A到达驾驶门边仍握着车钥匙，B说：“出发。” Visible characters: B. Offscreen characters must remain outside the frame: none. Visible registered props: none. Distance/position stage: endpoint-transition: A.position 路边 -> 驾驶门边 (evidence: B002-F01). Primary focus: B. Must show: B. May show: none. Must not show: A. Render delta: allowed; story delta: none. Camera rationale: 听者反应近景，捕捉对话中的情绪反馈，不推进对白事实。 Do not add another action phase, character, prop, emotion result, or spatial fact.

NEGATIVE_CONSTRAINTS:
@CANON(NEGATIVE_CONSTRAINTS)
