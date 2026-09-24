"""Credential-free regression fixtures, not video or semantic acceptance."""
import copy
from decimal import Decimal
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from prompt_core import assess, load_source, load_master, tag_present


def source(ids=('01',), seconds=('4',)):
    return {'sha256': 'fixture', 'shots': [
        {'id': sid, 'kind': 'shot', 'scene': 'S01', 'scene_id': 'S01',
         'duration': Decimal(sec) if sec is not None else None,
         'body': '甲仍持木匣，乙未接。', 'dialogue': [], 'raw': {}}
        for sid, sec in zip(ids, seconds)]}


def master(ids=('01',), seconds='4', used=(), unused=()):
    parts=['【生成目标】\n甲递匣而乙尚未接。']
    if used: parts.append('【参考素材职责】\n'+'\n'.join(t+'：仅采用明确身份。' for t in used))
    if unused: parts.append('【未采用素材】\n'+'、'.join(unused))
    parts += ['【主体、关系与场景】\n甲在桌西侧，匣仍由甲持有。',
              '【镜头脚本】\n'+'\n'.join(f'Cut {i}\n固定关系镜，乙仍未接物。' for i in range(1,len(ids)+1)),
              '【保持一致】\n人物身份、桌的位置不变。']
    return {'units':[{'id':'G01','operation_id':'OP001','mode':'generate',
                     'source_refs':list(ids),'duration':Decimal(seconds) if seconds else None,
                     'prompt_text':'\n\n'.join(parts)}]}


def context(n=30, used=('@图片1',), visible='absent'):
    cfg={'references':[{'tag':t,'role':'identity'} for t in used]}
    if visible!='absent': cfg['accessible_asset_tags']=visible
    return {'assets':[{'tag':f'@图片{i}','available':True} for i in range(1,n+1)],
            'inventory_complete':True, 'units':{'G01':cfg}}


def codes(result):return {i['code'] for i in result['issues'] if i['level']=='error'}


class PromptTests(unittest.TestCase):
    def test_scoped_three_of_thirty(self):
        m=master(used=('@图片1',),unused=('@图片2','@图片3'));c=context(visible=['@图片1','@图片2','@图片3'])
        before=copy.deepcopy((m,c));r=assess(m,source(),c)
        self.assertEqual(codes(r),set());self.assertEqual((m,c),before)
        self.assertEqual(r['units'][0]['asset_access']['basis'],'explicit_declaration')
    def test_full_inventory_legacy(self):
        r=assess(master(used=('@图片1',),unused=tuple(f'@图片{i}' for i in range(2,31))),source(),context())
        self.assertEqual(codes(r),set());self.assertEqual(r['units'][0]['asset_access']['basis'],'legacy_inventory')
    def test_missing_scope_preserves_legacy_check(self):
        self.assertIn('UNUSED_ASSET_SET',codes(assess(master(used=('@图片1',)),source(),context())))
    def test_unknown_scope_not_empty_claim(self):
        c=context();c['inventory_complete']=False
        r=assess(master(used=('@图片1',)),source(),c)
        self.assertEqual(codes(r),set());self.assertEqual(r['units'][0]['asset_access']['basis'],'unknown')
    def test_explicit_empty_without_references(self):
        self.assertEqual(codes(assess(master(),source(),context(used=(),visible=[]))),set())
    def test_empty_scope_rejects_active(self):
        self.assertIn('ASSIGNMENT_NOT_ACCESSIBLE',codes(assess(master(used=('@图片1',)),source(),context(visible=[]))))
    def test_bad_scope_types(self):
        for value in [None,'@图片1',{},True,[1],[' @图片1']]:
            with self.subTest(value=value):
                c=context(visible=value)
                self.assertIn('ACCESSIBLE_ASSET_TYPE',codes(assess(master(used=('@图片1',)),source(),c)))
    def test_duplicate_unknown_unavailable(self):
        c=context(visible=['@图片1','@图片1','@图片999','@图片2']);c['assets'][1]['available']=False
        errors=codes(assess(master(used=('@图片1',)),source(),c))
        self.assertTrue({'ACCESSIBLE_ASSET_DUPLICATE','ACCESSIBLE_ASSET_UNKNOWN','ACCESSIBLE_ASSET_UNAVAILABLE'}<=errors)
    def test_tag_prefix_collision(self):
        self.assertFalse(tag_present('@图片1','@图片10：身份。'))
        self.assertTrue(tag_present('@图片1','@图片1作为首帧。'))
        m=master(used=('@图片10',));c=context(used=('@图片10',),visible=['@图片10'])
        self.assertEqual(codes(assess(m,source(),c)),set())
    def test_excluded_nonvisible_tag_rejected(self):
        m=master(used=('@图片1',),unused=('@图片2','@图片3','@图片30'))
        errors=codes(assess(m,source(),context(visible=['@图片1','@图片2','@图片3'])))
        self.assertTrue({'ASSET_NOT_ACCESSIBLE','UNUSED_ASSET_SET'}<=errors)
    def test_active_and_unused_conflict(self):
        self.assertIn('ASSET_ACTIVE_AND_UNUSED',codes(assess(master(used=('@图片1',),unused=('@图片1',)),source(),context(visible=['@图片1']))))
    def test_distinct_unit_scopes(self):
        m=master(used=('@图片1',));second=master(ids=('02',),used=('@图片2',))['units'][0];second['id']='G02';m['units'].append(second)
        c=context(visible=['@图片1']);c['units']['G02']={'references':[{'tag':'@图片2','role':'identity'}],'accessible_asset_tags':['@图片2']}
        self.assertEqual(codes(assess(m,source(('01','02'),('4','4')),c)),set())
    def test_nonadjacent_and_boundaries(self):
        s=source(('01','02','03'),('4','8','3'))
        r=assess(master(('01','03'),'7'),s,{'scope':['01','03']})
        self.assertIn('NON_ADJACENT',codes(r))
        m=master(('01','02','03'),'15')
        for kind in ['semantic_end','scene_change','time_break','reality_break','submission_split']:
            r=assess(m,s,{'boundaries':[{'after':'01','kind':kind,'reason':'explicit test boundary'}]})
            self.assertTrue({'SEMANTIC_END_CROSSED','SUBMISSION_SPLIT_CROSSED'}&codes(r))
        self.assertFalse(codes(assess(m,s,{'boundaries':[{'after':'01','kind':'historical_split'}]})))
    def test_precise_budget_and_limit(self):
        r=assess(master(('01','02'),'8.75'),source(('01','02'),('4.125','4.625')),{})
        self.assertFalse(codes(r));self.assertEqual(r['units'][0]['timeline'][-1]['end'],'8.750')
        self.assertIn('DURATION_LIMIT',codes(assess(master(seconds='31'),source(seconds=('31',)),{})))
    def test_unknown_duration_not_multigroup(self):
        self.assertIn('UNKNOWN_GROUP_DURATION',codes(assess(master(('01','02'),None),source(('01','02'),('4',None)),{})))
    def test_speech_one_time_and_voice(self):
        s=source();s['shots'][0]['dialogue']=[{'speaker':'乙','voice':'画外','text':'我没有接。'}]
        m=master();m['units'][0]['prompt_text']=m['units'][0]['prompt_text'].replace('乙仍未接物。','乙仍未接物。乙（画外，中文）说：{我没有接。}')
        self.assertFalse(codes(assess(m,s,{})))
        m['units'][0]['prompt_text']+='\n{我没有接。}'
        self.assertIn('DIALOGUE_DUPLICATED_OR_EXTRA',codes(assess(m,s,{})))
    def test_real_files_parse_and_no_rewrite(self):
        with tempfile.TemporaryDirectory() as t:
            d=Path(t);sp=d/'source.json';mp=d/'master.md'
            sp.write_text(json.dumps({'shots':[{'id':'01','scene_id':'S01','duration_seconds':4,'body':'甲仍持木匣。'}]},ensure_ascii=False))
            p=master()['units'][0]['prompt_text']
            mp.write_text('# 试验\n本轮来源：虚构回归\n本轮范围：镜头01\n\n## 单元 G01\n来源：["01"]\n预计时长：4\n操作：generate\n\n```text\n'+p+'\n```\n')
            before=(sp.read_bytes(),mp.read_bytes());s=load_source(sp);m=load_master(mp,s)
            self.assertFalse(codes(assess(m,s,{})));self.assertEqual(before,(sp.read_bytes(),mp.read_bytes()))


if __name__=='__main__':unittest.main()
