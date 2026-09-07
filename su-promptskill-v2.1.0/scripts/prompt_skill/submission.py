"""Submission conditions are separate from authored-content and file validity."""
from __future__ import annotations
import copy
import re
from decimal import Decimal
from pathlib import Path
from .common import DeliveryError, load_json

PROFILE_FILE = Path(__file__).resolve().parents[2] / 'profiles.json'


def resolve_profile(profile_id='seedance-2.5-default', profile_file=None):
    if profile_file:
        result = load_json(Path(profile_file).read_bytes())
    else:
        profiles = load_json(PROFILE_FILE.read_bytes())
        if profile_id not in profiles:
            raise DeliveryError(f'未知 Profile：{profile_id}')
        result = profiles[profile_id]
    if not isinstance(result, dict) or not result.get('profile_id'):
        raise DeliveryError('Profile 缺少 profile_id')
    result = copy.deepcopy(result)
    capabilities = result.get('capabilities', {})
    if 'planning_limits' not in result:
        result['planning_limits'] = {'duration_seconds': capabilities.get('max_clip_duration_seconds'), 'cuts': None}
    for key in ('duration_seconds', 'cuts'):
        value = result['planning_limits'].get(key)
        if value is not None and (isinstance(value, bool) or Decimal(str(value)) <= 0):
            raise DeliveryError('Profile 容量必须为正数或空值')
    return result


def submission_checks(source, master, context, profile, checked):
    inventory = context.get('asset_inventory', {})
    inventory = inventory.get('items', []) if isinstance(inventory, dict) else inventory
    if not isinstance(inventory, list):
        raise DeliveryError('素材库存不是列表')
    tags = {}; assignments = context.get('asset_assignments', context.get('reference_role_map', []))
    for item in inventory:
        if not isinstance(item, dict) or not isinstance(item.get('tag'), str) or not item['tag'] or item['tag'] in tags:
            raise DeliveryError('素材 tag 缺失或重复')
        tags[item['tag']] = item
    if not isinstance(assignments, list):
        raise DeliveryError('素材职责不是列表')
    operations = context.get('operations', [{'operation_id': 'OP001', 'primary': context.get('task', {}).get('primary', 'generate')}])
    op_map = {}; prior = set()
    for op in operations:
        oid = op['operation_id']; dependency = op.get('depends_on_operation_id')
        if dependency and dependency not in prior:
            raise DeliveryError('操作依赖未出现、顺序颠倒或形成循环')
        primary = op.get('primary', op.get('task', {}).get('primary', 'generate'))
        if primary not in {'generate', 'edit', 'extend'}:
            raise DeliveryError(f'未知操作类型：{primary}')
        op_map[oid] = dict(op, primary=primary); prior.add(oid)
    request = context.get('request_configuration', {})
    raw_request = request.get('raw', request) if isinstance(request, dict) else {}
    limits = profile.get('request_constraints', profile.get('capabilities', {}).get('request_constraints', {}))
    conditions = {}; verification = profile.get('verification', {})
    platform_verified = (verification.get('status') == 'verified' and bool(verification.get('checked_at'))
                         and bool(verification.get('platform')) and bool(verification.get('sources')))
    for unit in master.units:
        reasons = []; op = op_map[unit.operation]
        if not platform_verified:
            reasons.append('平台能力尚未完整核实；保留正文，不宣称可直接提交')
        if checked['units'][unit.id]['content_fidelity'] != 'agent_reviewed':
            reasons.append('本单元尚未完成来源双向复核，或存在机械检查错误')
        planning = profile.get('planning_limits', {})
        cap = planning.get('duration_seconds')
        if cap and unit.duration is not None and unit.duration > Decimal(str(cap)):
            reasons.append('单元超过当前 Profile 规划时长；不自动拆源镜')
        if planning.get('cuts') and len(unit.source_ids) > int(planning['cuts']):
            reasons.append('单元超过当前配置的 Cut 容量；这是本地规划条件，不冒称官方上限')
        if unit.duration is None:
            reasons.append('来源时长未知；正文保留顺序阶段，提交时长仍须确认')
        max_chars = profile.get('max_prompt_characters')
        if max_chars and len(unit.text) > int(max_chars):
            reasons.append('正文超过当前平台字符配置；不能删对白或事件来适配')
        applicable = [a for a in assignments if isinstance(a, dict) and
                      a.get('operation_id', unit.operation) == unit.operation and
                      ('*' in a.get('applies_to_shot_ids', ['*']) or set(unit.source_ids).intersection(a.get('applies_to_shot_ids', ['*'])))]
        used = {tag for tag in tags if tag in unit.text}
        assigned = {a.get('tag') for a in applicable}
        for tag in used - assigned:
            reasons.append(f'素材 {tag} 缺少当前单元的职责')
        unknown = set(re.findall(r'<<<[^<>\n]+>>>|@(?:image|video|audio|图片|视频|音频)[-_]?\d+', unit.text, re.I)) - set(tags)
        if unknown:
            reasons.append('引用了库存外素材：' + '、'.join(sorted(unknown)))
        for assignment in applicable:
            tag = assignment.get('tag'); item = tags.get(tag)
            critical = assignment.get('core') is True or assignment.get('role') in {'edit_source','extension_source'}
            if not item or item.get('available') is not True:
                if critical or tag in used:
                    reasons.append(f'核心或已引用素材不可用：{tag}')
            if item and item.get('available') is True and tag not in used and critical:
                reasons.append(f'正文缺少核心素材职责：{tag}')
        asset_limits = profile.get('asset_limits', profile.get('capabilities', {}).get('asset_limits', {}))
        used_items = [tags[tag] for tag in used]
        if asset_limits.get('max_total') is not None and len(used_items) > asset_limits['max_total']:
            reasons.append('当前引用素材总数超过已声明的平台限制')
        for media in ('image','video','audio'):
            items = [item for item in used_items if item.get('media_type') == media]
            spec = asset_limits.get(media, {})
            if spec.get('max_count') is not None and len(items) > spec['max_count']:
                reasons.append(f'{media} 素材数量超过当前配置')
            durations = []
            for item in items:
                if media == 'image' and any(k in spec for k in ('min_dimension_pixels','max_dimension_pixels','min_total_pixels','max_total_pixels','min_aspect_ratio','max_aspect_ratio')):
                    w, h = item.get('width'), item.get('height')
                    if not isinstance(w,(int,float)) or not isinstance(h,(int,float)) or min(w,h) <= 0:
                        reasons.append('图片尺寸尚未观察，不能完成平台校验'); continue
                    tests = [('min_dimension_pixels',min(w,h),False),('max_dimension_pixels',max(w,h),True),
                             ('min_total_pixels',w*h,False),('max_total_pixels',w*h,True),
                             ('min_aspect_ratio',w/h,False),('max_aspect_ratio',w/h,True)]
                    if any(key in spec and (value > spec[key] if maximum else value < spec[key]) for key,value,maximum in tests):
                        reasons.append('图片尺寸、像素或宽高比超出当前平台配置')
                if media in ('video','audio') and spec:
                    try:
                        d = Decimal(str(item.get('duration_seconds')))
                        if not d.is_finite() or d <= 0: raise ValueError()
                    except (ValueError, ArithmeticError):
                        reasons.append(f'{media} 素材时长尚未有效观察'); continue
                    durations.append(d)
                    if spec.get('min_item_duration_seconds') is not None and d < Decimal(str(spec['min_item_duration_seconds'])):
                        reasons.append(f'{media} 单段素材过短')
                    if spec.get('max_item_duration_seconds') is not None and d > Decimal(str(spec['max_item_duration_seconds'])):
                        reasons.append(f'{media} 单段素材过长')
            if spec.get('max_total_duration_seconds') is not None and sum(durations) > Decimal(str(spec['max_total_duration_seconds'])):
                reasons.append(f'{media} 总素材时长超出配置')
        if asset_limits and any(i.get('media_type') not in {'image','video','audio'} for i in used_items):
            reasons.append('已引用素材缺少有效媒体类型，平台素材检查未完成')
        roles = {a.get('content_role', a.get('role')) for a in applicable if a.get('tag') in used}
        if limits.get('strict_frame_roles_exclusive') and roles.intersection({'first_frame','last_frame'}) and roles.intersection({'reference_image','reference_video','reference_audio'}):
            reasons.append('当前平台配置不允许严格首尾帧与多参考角色混用')
        if op['primary'] in {'edit', 'extend'}:
            role = 'edit_source' if op['primary'] == 'edit' else 'extension_source'
            sources = [a for a in applicable if a.get('role') == role]
            if len(sources) != 1 or tags.get(sources[0].get('tag'), {}).get('available') is not True:
                reasons.append('缺少唯一且已观察可用的母版／延长源')
            elif tags[sources[0]['tag']].get('media_type') != 'video':
                reasons.append('视频编辑／延长源必须为已确认的视频素材')
            if op['primary'] == 'edit' and not op.get('edit_scope'):
                reasons.append('编辑范围与未修改范围尚未明确')
            if op['primary'] == 'extend' and (op.get('direction') not in {'forward','backward','向前','向后'} or not op.get('boundary_state')):
                reasons.append('延长方向或边界状态尚未明确')
        dependency = op.get('depends_on_operation_id')
        if dependency:
            output_tag = context.get('operation_outputs', {}).get(dependency)
            if not output_tag or tags.get(output_tag, {}).get('available') is not True or output_tag not in used:
                reasons.append('依赖步骤的实际输出尚未生成／观察，不能把计划当作视频素材')
        for key, choices_key in (('ratio','ratios'), ('resolution','resolutions'), ('output_format','output_formats')):
            if key in raw_request and limits.get(choices_key) and raw_request[key] not in limits[choices_key]:
                reasons.append(f'请求 {key} 不在当前平台配置中')
        if raw_request.get('model_id') and profile.get('model_id') and raw_request['model_id'] != profile['model_id']:
            reasons.append('请求模型与 Profile 不一致')
        if 'duration' in raw_request:
            try:
                value = Decimal(str(raw_request['duration']))
                maximum = limits.get('duration_seconds', {}).get('maximum', cap)
                minimum = limits.get('duration_seconds', {}).get('minimum', 1)
                if not value.is_finite() or (value != -1 and (value < Decimal(str(minimum)) or (maximum and value > Decimal(str(maximum))))):
                    reasons.append('请求时长不满足当前平台配置')
            except Exception:
                reasons.append('请求时长不可读')
        if 'generate_audio' in raw_request and not isinstance(raw_request['generate_audio'], bool):
            reasons.append('generate_audio 必须是布尔值')
        conditions[unit.id] = {'submission_ready': not reasons, 'reasons': reasons,
                               'platform_verification': verification.get('status', 'unverified'), 'operation': op}
    return conditions
