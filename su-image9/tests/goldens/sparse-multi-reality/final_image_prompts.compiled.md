# PAGE-01

DELIVERABLE:
Generate one wide horizontal 16:9 canvas containing a clean 3x3 storyboard grid.
Each of the 9 panels must also be a horizontal 16:9 storyboard frame.
Use the declared PAGE_SPATIAL_ANCHOR for spatial continuity across the entire 3x3 grid.
Preserve source-shot order and every source shot's original camera composition.
Do not redesign the room, exterior location, furniture footprint, terrain, road, doorway, vehicle position, or object positions in later panels.
Do not generate any text, labels, captions, panel numbers, scene headers, shot numbers, subtitles, arrows, or watermarks inside the image.

SYSTEM_STYLE_LAYER:
SYSTEM_STYLE_LAYER:
This entire generation must follow a single unified storyboard production style.

STYLE ANCHOR:
Treat this as a single cohesive storyboard drawn by one graphite storyboard artist in a single production session. For batch generation, all outputs must match the same storyboard artist, same production session, same medium, same stroke weight, same shading density, and same unfinished storyboard look.

MEDIUM:
Monochrome graphite storyboard / pencil pre-visualization drawing only. Hand-drawn pencil / graphite sketch only. Production storyboard sheet. Animatic frame design. Non-painting, non-rendered, non-illustration.

LINE RULE:
Thin graphite linework only. Visible sketch strokes allowed. Construction lines allowed. Rough drafting lines allowed. No inked comic outlines. No polished clean manga line art.

SHADING RULE:
Light hatching only. Mid-gray tonal range. Controlled medium contrast only. No pure black fill blocks. No heavy ink fill. No painterly shading. No soft airbrush gradients.

TEXTURE RULE:
Paper-like sketch texture. Slightly rough graphite grain. High-frequency pencil texture. Unfinished production drawing aesthetic.

RENDERING RULE:
No digital painting, no photorealism, no CGI, no cinematic lighting, no bloom, no HDR lighting, no volumetric god rays, no depth-of-field blur, no airbrush gradients, no rendered concept art look.

CONSISTENCY RULE:
All 9 panels must share identical drawing style, graphite medium, stroke weight, shading density, texture grain, tonal range, and rendering restraint. No stylistic variation between panels is allowed.

SOURCE_BINDING_LAYER:
This page is bound to source shots C001.
The structured panel plan is the only machine fact source; this Prompt must not override it.
Reference asset state: none.

SCENE_LAYER:
Scene S01; reality layer: 现实.
Source scene heading: 1 会客室 日 内.
Registered spatial axis: A与B保持同侧关系，A从起点移向终点，摄影机不跨轴。.
Registered fixed geometry: 门; 桌子.
Registered character placement: A: position 门口, facing B; B: position 桌边, facing A.

CAMERA_RULE_LAYER:
Preserve every source shot camera tag and source order; a derived angle may change only angle, shot size, or composition emphasis.
C001: source camera 平视, 双人中景, 固定镜头; Composition: （A在门口，B在桌边，两人相对。）; Camera motion idea: 固定镜头; Visible action state: A和B站在门口，A握着钥匙。

CONTINUITY_LAYER:
Visible character boundary: A、B.
Visible prop boundary: 钥匙.
Derived panels inherit the exact Beat, fact, action phase, emotional result, and continuity-state hash of their source panel.
Position and facing transitions follow only continuity_updates; never infer a distance endpoint from action keywords.
Render_delta=allowed means a derived panel may crop, obscure, or frame a subset of the source visible set; story_delta must remain none.

PAGE_SPATIAL_ANCHOR:
Use PANEL-1 / C001 as this page's declared spatial anchor.
Panel 1 still preserves its original director-approved source camera and composition; do not widen or redesign it to manufacture an anchor.
All angles remain on the registered side of the axis and may reveal only registered geometry.

FIXED_GEOMETRY_LOCK:
Strict panel geometry blueprint, mandatory before drawing:
Treat the final canvas as a clean wide horizontal 16:9 layout.
Draw exactly nine separate straight rectangular panel frames with visible gutters.
Arrange the 9 panels in a clean 3x3 storyboard grid: three equal columns and three equal rows.
All 9 panels must have the same width, the same height, the same 16:9 aspect ratio, and aligned edges.
Each panel frame must remain a flat horizontal 16:9 rectangle.
Do not let any panel become square, vertical, tall, narrow, compressed, stretched, trapezoid, diagonal, rounded, or irregular.
Keep gutters and margins as empty separating space. If a close-up needs more room, use empty background or negative space inside that panel; never change the panel shape or aspect ratio.
Do not create 3:2, 4:3, A4, square, vertical, mixed-size, manga, comic, collage, or poster layouts.
Do not create a manga page, comic page, dynamic collage, masonry grid, mixed panel sizes, tilted frames, perspective-distorted frames, overlapping panels, or a poster composition.
The content inside a panel may crop or zoom, but the panel frame itself must remain a flat horizontal 16:9 rectangle.
Geometry correctness does not replace the SYSTEM_STYLE_LAYER. The 3x3 grid must remain geometrically strict while all panel contents remain in the same monochrome graphite storyboard production style.
Source-defined fixed geometry for this page: 门; 桌子.

VEHICLE_AND_AXIS_LOCKS:
Preserve registered eyelines, facing, side-axis relationships, and screen-left/screen-right continuity.
Do not introduce unregistered transport objects or alter any registered object state.

OBJECT_VISIBILITY_AND_BOUNDARIES:
Draw only these visible registered props when their source panel calls for them: 钥匙.
Offscreen voices and characters remain outside the frame unless that source panel lists them as visible.

PANEL_LAYER:
PANEL-1: Draw 平视, 双人中景, 固定镜头. Composition: （A在门口，B在桌边，两人相对。）; Camera motion idea: 固定镜头; Visible action state: A和B站在门口，A握着钥匙。 Visible characters: A、B. Offscreen characters must remain outside the frame: none. Visible registered props: 钥匙. Distance/position stage: none. Primary focus: A、钥匙. Must show: A、B、钥匙. May show: none. Must not show: none. Render delta: none; story delta: none. Camera rationale: 源镜头，保留导演原始构图与可见集合。 Do not add another action phase, character, prop, emotion result, or spatial fact.
PANEL-2: Draw action start moment derived from 平视, 双人中景, 固定镜头. Freeze the representative instant at the start of the action progression, before the main movement begins. Preserve the source state exactly: Composition: （A在门口，B在桌边，两人相对。）; Camera motion idea: 固定镜头; Visible action state: A和B站在门口，A握着钥匙。 Visible characters: A. Offscreen characters must remain outside the frame: none. Visible registered props: none. Distance/position stage: none. Primary focus: A. Must show: A. May show: B、钥匙. Must not show: none. Render delta: allowed; story delta: none. Camera rationale: 动作起点瞬间，保留动作开始前的代表性姿态。 Do not add another action phase, character, prop, emotion result, or spatial fact.
PANEL-3: Draw action process moment derived from 平视, 双人中景, 固定镜头. Freeze the representative instant in the middle of the action progression, showing clear movement direction. Preserve the source state exactly: Composition: （A在门口，B在桌边，两人相对。）; Camera motion idea: 固定镜头; Visible action state: A和B站在门口，A握着钥匙。 Visible characters: A. Offscreen characters must remain outside the frame: none. Visible registered props: none. Distance/position stage: none. Primary focus: A. Must show: A. May show: B、钥匙. Must not show: none. Render delta: allowed; story delta: none. Camera rationale: 动作过程瞬间，展示明确的方向和动势，但不到达终点。 Do not add another action phase, character, prop, emotion result, or spatial fact.
PANEL-4: Draw action end moment derived from 平视, 双人中景, 固定镜头. Freeze the representative instant at the end of the action progression, showing the result posture without adding emotional aftermath. Preserve the source state exactly: Composition: （A在门口，B在桌边，两人相对。）; Camera motion idea: 固定镜头; Visible action state: A和B站在门口，A握着钥匙。 Visible characters: A. Offscreen characters must remain outside the frame: none. Visible registered props: none. Distance/position stage: none. Primary focus: A. Must show: A. May show: B、钥匙. Must not show: none. Render delta: allowed; story delta: none. Camera rationale: 动作终点瞬间，保留结果姿态，不添加情绪后果。 Do not add another action phase, character, prop, emotion result, or spatial fact.
PANEL-5: Draw same-side profile view derived from 平视, 双人中景, 固定镜头. Use a profile view from the established side of the axis without reversing screen direction. Preserve the source state exactly: Composition: （A在门口，B在桌边，两人相对。）; Camera motion idea: 固定镜头; Visible action state: A和B站在门口，A握着钥匙。 Visible characters: A. Offscreen characters must remain outside the frame: none. Visible registered props: none. Distance/position stage: none. Primary focus: A. Must show: A. May show: B、钥匙. Must not show: none. Render delta: allowed; story delta: none. Camera rationale: 同侧侧面，强调运动方向或空间深度，不跨轴。 Do not add another action phase, character, prop, emotion result, or spatial fact.
PANEL-6: Draw registered-prop insert derived from 平视, 双人中景, 固定镜头. Use an insert of an already visible registered prop without changing its owner, position, state, or action stage. Preserve the source state exactly: Composition: （A在门口，B在桌边，两人相对。）; Camera motion idea: 固定镜头; Visible action state: A和B站在门口，A握着钥匙。 Visible characters: none. Offscreen characters must remain outside the frame: none. Visible registered props: 钥匙. Distance/position stage: none. Primary focus: 钥匙. Must show: 钥匙. May show: A. Must not show: B. Render delta: allowed; story delta: none. Camera rationale: 已登记道具插入，聚焦道具状态或持手，不新增剧情事实。 Do not add another action phase, character, prop, emotion result, or spatial fact.
PANEL-7: Draw same-side over-shoulder view derived from 平视, 双人中景, 固定镜头. Use an over-shoulder view only between the already visible characters; preserve eyelines and screen sides. Preserve the source state exactly: Composition: （A在门口，B在桌边，两人相对。）; Camera motion idea: 固定镜头; Visible action state: A和B站在门口，A握着钥匙。 Visible characters: A、B. Offscreen characters must remain outside the frame: none. Visible registered props: none. Distance/position stage: none. Primary focus: A、B. Must show: A、B. May show: 钥匙. Must not show: none. Render delta: allowed; story delta: none. Camera rationale: 双人过肩，保留说者与听者的空间关系和视线方向。 Do not add another action phase, character, prop, emotion result, or spatial fact.
PANEL-8: Draw same-side three-quarter view derived from 平视, 双人中景, 固定镜头. Use a three-quarter view from the established side of the axis while preserving eyelines and positions. Preserve the source state exactly: Composition: （A在门口，B在桌边，两人相对。）; Camera motion idea: 固定镜头; Visible action state: A和B站在门口，A握着钥匙。 Visible characters: A. Offscreen characters must remain outside the frame: none. Visible registered props: none. Distance/position stage: none. Primary focus: A. Must show: A. May show: B、钥匙. Must not show: none. Render delta: allowed; story delta: none. Camera rationale: 同侧三分之四角度，保留眼线和画面左右关系。 Do not add another action phase, character, prop, emotion result, or spatial fact.
PANEL-9: Draw same-axis wider composition derived from 平视, 双人中景, 固定镜头. Use a wider composition on the established side of the axis, revealing only registered geometry. Preserve the source state exactly: Composition: （A在门口，B在桌边，两人相对。）; Camera motion idea: 固定镜头; Visible action state: A和B站在门口，A握着钥匙。 Visible characters: A. Offscreen characters must remain outside the frame: none. Visible registered props: none. Distance/position stage: none. Primary focus: A. Must show: A. May show: B、钥匙. Must not show: none. Render delta: allowed; story delta: none. Camera rationale: 同轴更宽，展示已登记的空间边界与固定物，不改变人物关系。 Do not add another action phase, character, prop, emotion result, or spatial fact.

NEGATIVE_CONSTRAINTS:
NEGATIVE_CONSTRAINTS:
No photorealism, no film still look, no realistic skin texture, no cinematic lighting, no cinematic grading, no HDR lighting, no bloom, no volumetric god rays, no depth-of-field blur, no CGI, no 3D render, no digital painting, no digital illustration look, no rendered concept art, no polished illustration, no watercolor, no oil painting, no painterly shading, no soft airbrush gradients, no anime rendering, no manga page, no comic page layout, no inked comic outlines, no clean manga line art, no dynamic collage, no masonry grid, no poster composition, no color, no pure black fill blocks, no heavy ink fill, no text inside the image, no labels, no subtitles, no arrows, no watermarks, no square panels, no vertical panels, no tall panels, no narrow panels, no mixed-size panels.

# PAGE-02

DELIVERABLE:
Generate one wide horizontal 16:9 canvas containing a clean 3x3 storyboard grid.
Each of the 9 panels must also be a horizontal 16:9 storyboard frame.
Use the declared PAGE_SPATIAL_ANCHOR for spatial continuity across the entire 3x3 grid.
Preserve source-shot order and every source shot's original camera composition.
Do not redesign the room, exterior location, furniture footprint, terrain, road, doorway, vehicle position, or object positions in later panels.
Do not generate any text, labels, captions, panel numbers, scene headers, shot numbers, subtitles, arrows, or watermarks inside the image.

SYSTEM_STYLE_LAYER:
SYSTEM_STYLE_LAYER:
This entire generation must follow a single unified storyboard production style.

STYLE ANCHOR:
Treat this as a single cohesive storyboard drawn by one graphite storyboard artist in a single production session. For batch generation, all outputs must match the same storyboard artist, same production session, same medium, same stroke weight, same shading density, and same unfinished storyboard look.

MEDIUM:
Monochrome graphite storyboard / pencil pre-visualization drawing only. Hand-drawn pencil / graphite sketch only. Production storyboard sheet. Animatic frame design. Non-painting, non-rendered, non-illustration.

LINE RULE:
Thin graphite linework only. Visible sketch strokes allowed. Construction lines allowed. Rough drafting lines allowed. No inked comic outlines. No polished clean manga line art.

SHADING RULE:
Light hatching only. Mid-gray tonal range. Controlled medium contrast only. No pure black fill blocks. No heavy ink fill. No painterly shading. No soft airbrush gradients.

TEXTURE RULE:
Paper-like sketch texture. Slightly rough graphite grain. High-frequency pencil texture. Unfinished production drawing aesthetic.

RENDERING RULE:
No digital painting, no photorealism, no CGI, no cinematic lighting, no bloom, no HDR lighting, no volumetric god rays, no depth-of-field blur, no airbrush gradients, no rendered concept art look.

CONSISTENCY RULE:
All 9 panels must share identical drawing style, graphite medium, stroke weight, shading density, texture grain, tonal range, and rendering restraint. No stylistic variation between panels is allowed.

SOURCE_BINDING_LAYER:
This page is bound to source shots C002.
The structured panel plan is the only machine fact source; this Prompt must not override it.
Reference asset state: none.

SCENE_LAYER:
Scene S01; reality layer: 回忆.
Source scene heading: 1 会客室 日 内.
Registered spatial axis: A与B保持同侧关系，A从起点移向终点，摄影机不跨轴。.
Registered fixed geometry: 门; 桌子.
Registered character placement: A: position 门口, facing B; B: position 桌边, facing A.

CAMERA_RULE_LAYER:
Preserve every source shot camera tag and source order; a derived angle may change only angle, shot size, or composition emphasis.
C002: source camera 同侧三分之四, 双人中景, 轻微横移; Composition: 可见主体：A、B；可见道具：钥匙。; Camera motion idea: 轻微横移; Visible action state: A到达桌边仍握着钥匙，B说：“到了。”

CONTINUITY_LAYER:
Visible character boundary: A、B.
Visible prop boundary: 钥匙.
Derived panels inherit the exact Beat, fact, action phase, emotional result, and continuity-state hash of their source panel.
Position and facing transitions follow only continuity_updates; never infer a distance endpoint from action keywords.
Render_delta=allowed means a derived panel may crop, obscure, or frame a subset of the source visible set; story_delta must remain none.

PAGE_SPATIAL_ANCHOR:
Use PANEL-1 / C002 as this page's declared spatial anchor.
Panel 1 still preserves its original director-approved source camera and composition; do not widen or redesign it to manufacture an anchor.
All angles remain on the registered side of the axis and may reveal only registered geometry.

FIXED_GEOMETRY_LOCK:
Strict panel geometry blueprint, mandatory before drawing:
Treat the final canvas as a clean wide horizontal 16:9 layout.
Draw exactly nine separate straight rectangular panel frames with visible gutters.
Arrange the 9 panels in a clean 3x3 storyboard grid: three equal columns and three equal rows.
All 9 panels must have the same width, the same height, the same 16:9 aspect ratio, and aligned edges.
Each panel frame must remain a flat horizontal 16:9 rectangle.
Do not let any panel become square, vertical, tall, narrow, compressed, stretched, trapezoid, diagonal, rounded, or irregular.
Keep gutters and margins as empty separating space. If a close-up needs more room, use empty background or negative space inside that panel; never change the panel shape or aspect ratio.
Do not create 3:2, 4:3, A4, square, vertical, mixed-size, manga, comic, collage, or poster layouts.
Do not create a manga page, comic page, dynamic collage, masonry grid, mixed panel sizes, tilted frames, perspective-distorted frames, overlapping panels, or a poster composition.
The content inside a panel may crop or zoom, but the panel frame itself must remain a flat horizontal 16:9 rectangle.
Geometry correctness does not replace the SYSTEM_STYLE_LAYER. The 3x3 grid must remain geometrically strict while all panel contents remain in the same monochrome graphite storyboard production style.
Source-defined fixed geometry for this page: 门; 桌子.

VEHICLE_AND_AXIS_LOCKS:
Preserve registered eyelines, facing, side-axis relationships, and screen-left/screen-right continuity.
Do not introduce unregistered transport objects or alter any registered object state.

OBJECT_VISIBILITY_AND_BOUNDARIES:
Draw only these visible registered props when their source panel calls for them: 钥匙.
Offscreen voices and characters remain outside the frame unless that source panel lists them as visible.

PANEL_LAYER:
PANEL-1: Draw 同侧三分之四, 双人中景, 轻微横移. Composition: 可见主体：A、B；可见道具：钥匙。; Camera motion idea: 轻微横移; Visible action state: A到达桌边仍握着钥匙，B说：“到了。” Visible characters: A、B. Offscreen characters must remain outside the frame: none. Visible registered props: 钥匙. Distance/position stage: endpoint-transition: A.position 门口 -> 桌边 (evidence: B002-F01). Primary focus: A、钥匙. Must show: A、B、钥匙. May show: none. Must not show: none. Render delta: none; story delta: none. Camera rationale: 源镜头，保留导演原始构图与可见集合。 Do not add another action phase, character, prop, emotion result, or spatial fact.
PANEL-2: Draw same-side over-shoulder view derived from 同侧三分之四, 双人中景, 轻微横移. Use an over-shoulder view only between the already visible characters; preserve eyelines and screen sides. Preserve the source state exactly: Composition: 可见主体：A、B；可见道具：钥匙。; Camera motion idea: 轻微横移; Visible action state: A到达桌边仍握着钥匙，B说：“到了。” Visible characters: A、B. Offscreen characters must remain outside the frame: none. Visible registered props: none. Distance/position stage: endpoint-transition: A.position 门口 -> 桌边 (evidence: B002-F01). Primary focus: A、B. Must show: A、B. May show: 钥匙. Must not show: none. Render delta: allowed; story delta: none. Camera rationale: 双人过肩，保留说者与听者的空间关系和视线方向。 Do not add another action phase, character, prop, emotion result, or spatial fact.
PANEL-3: Draw speaker close-up derived from 同侧三分之四, 双人中景, 轻微横移. Isolate the speaking character on the established side of the axis; keep the addressee off-screen or only partially visible. Preserve the source state exactly: Composition: 可见主体：A、B；可见道具：钥匙。; Camera motion idea: 轻微横移; Visible action state: A到达桌边仍握着钥匙，B说：“到了。” Visible characters: A. Offscreen characters must remain outside the frame: none. Visible registered props: none. Distance/position stage: endpoint-transition: A.position 门口 -> 桌边 (evidence: B002-F01). Primary focus: A. Must show: A. May show: none. Must not show: B. Render delta: allowed; story delta: none. Camera rationale: 说话者近景，保留台词落点时的表情与语气线索。 Do not add another action phase, character, prop, emotion result, or spatial fact.
PANEL-4: Draw listener reaction close-up derived from 同侧三分之四, 双人中景, 轻微横移. Isolate the listening character on the established side of the axis; show reaction without advancing the dialogue fact. Preserve the source state exactly: Composition: 可见主体：A、B；可见道具：钥匙。; Camera motion idea: 轻微横移; Visible action state: A到达桌边仍握着钥匙，B说：“到了。” Visible characters: B. Offscreen characters must remain outside the frame: none. Visible registered props: none. Distance/position stage: endpoint-transition: A.position 门口 -> 桌边 (evidence: B002-F01). Primary focus: B. Must show: B. May show: none. Must not show: A. Render delta: allowed; story delta: none. Camera rationale: 听者反应近景，捕捉对话中的情绪反馈，不推进对白事实。 Do not add another action phase, character, prop, emotion result, or spatial fact.
PANEL-5: Draw action start moment derived from 同侧三分之四, 双人中景, 轻微横移. Freeze the representative instant at the start of the action progression, before the main movement begins. Preserve the source state exactly: Composition: 可见主体：A、B；可见道具：钥匙。; Camera motion idea: 轻微横移; Visible action state: A到达桌边仍握着钥匙，B说：“到了。” Visible characters: A. Offscreen characters must remain outside the frame: none. Visible registered props: none. Distance/position stage: endpoint-transition: A.position 门口 -> 桌边 (evidence: B002-F01). Primary focus: A. Must show: A. May show: B、钥匙. Must not show: none. Render delta: allowed; story delta: none. Camera rationale: 动作起点瞬间，保留动作开始前的代表性姿态。 Do not add another action phase, character, prop, emotion result, or spatial fact.
PANEL-6: Draw action process moment derived from 同侧三分之四, 双人中景, 轻微横移. Freeze the representative instant in the middle of the action progression, showing clear movement direction. Preserve the source state exactly: Composition: 可见主体：A、B；可见道具：钥匙。; Camera motion idea: 轻微横移; Visible action state: A到达桌边仍握着钥匙，B说：“到了。” Visible characters: A. Offscreen characters must remain outside the frame: none. Visible registered props: none. Distance/position stage: endpoint-transition: A.position 门口 -> 桌边 (evidence: B002-F01). Primary focus: A. Must show: A. May show: B、钥匙. Must not show: none. Render delta: allowed; story delta: none. Camera rationale: 动作过程瞬间，展示明确的方向和动势，但不到达终点。 Do not add another action phase, character, prop, emotion result, or spatial fact.
PANEL-7: Draw action end moment derived from 同侧三分之四, 双人中景, 轻微横移. Freeze the representative instant at the end of the action progression, showing the result posture without adding emotional aftermath. Preserve the source state exactly: Composition: 可见主体：A、B；可见道具：钥匙。; Camera motion idea: 轻微横移; Visible action state: A到达桌边仍握着钥匙，B说：“到了。” Visible characters: A. Offscreen characters must remain outside the frame: none. Visible registered props: none. Distance/position stage: endpoint-transition: A.position 门口 -> 桌边 (evidence: B002-F01). Primary focus: A. Must show: A. May show: B、钥匙. Must not show: none. Render delta: allowed; story delta: none. Camera rationale: 动作终点瞬间，保留结果姿态，不添加情绪后果。 Do not add another action phase, character, prop, emotion result, or spatial fact.
PANEL-8: Draw same-side profile view derived from 同侧三分之四, 双人中景, 轻微横移. Use a profile view from the established side of the axis without reversing screen direction. Preserve the source state exactly: Composition: 可见主体：A、B；可见道具：钥匙。; Camera motion idea: 轻微横移; Visible action state: A到达桌边仍握着钥匙，B说：“到了。” Visible characters: A. Offscreen characters must remain outside the frame: none. Visible registered props: none. Distance/position stage: endpoint-transition: A.position 门口 -> 桌边 (evidence: B002-F01). Primary focus: A. Must show: A. May show: B、钥匙. Must not show: none. Render delta: allowed; story delta: none. Camera rationale: 同侧侧面，强调运动方向或空间深度，不跨轴。 Do not add another action phase, character, prop, emotion result, or spatial fact.
PANEL-9: Draw registered-prop insert derived from 同侧三分之四, 双人中景, 轻微横移. Use an insert of an already visible registered prop without changing its owner, position, state, or action stage. Preserve the source state exactly: Composition: 可见主体：A、B；可见道具：钥匙。; Camera motion idea: 轻微横移; Visible action state: A到达桌边仍握着钥匙，B说：“到了。” Visible characters: none. Offscreen characters must remain outside the frame: none. Visible registered props: 钥匙. Distance/position stage: endpoint-transition: A.position 门口 -> 桌边 (evidence: B002-F01). Primary focus: 钥匙. Must show: 钥匙. May show: A. Must not show: B. Render delta: allowed; story delta: none. Camera rationale: 已登记道具插入，聚焦道具状态或持手，不新增剧情事实。 Do not add another action phase, character, prop, emotion result, or spatial fact.

NEGATIVE_CONSTRAINTS:
NEGATIVE_CONSTRAINTS:
No photorealism, no film still look, no realistic skin texture, no cinematic lighting, no cinematic grading, no HDR lighting, no bloom, no volumetric god rays, no depth-of-field blur, no CGI, no 3D render, no digital painting, no digital illustration look, no rendered concept art, no polished illustration, no watercolor, no oil painting, no painterly shading, no soft airbrush gradients, no anime rendering, no manga page, no comic page layout, no inked comic outlines, no clean manga line art, no dynamic collage, no masonry grid, no poster composition, no color, no pure black fill blocks, no heavy ink fill, no text inside the image, no labels, no subtitles, no arrows, no watermarks, no square panels, no vertical panels, no tall panels, no narrow panels, no mixed-size panels.
