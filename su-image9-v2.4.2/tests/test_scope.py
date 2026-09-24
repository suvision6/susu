"""Offline scope/binding regressions. Synthetic PNGs are NOT storyboards.

All simulated approvals below are test data, never user approval of real work.
"""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from master_io import FormatError, parse_master
from prepare_image_request import prepare_request, scoped_context, SCOPE_STRATEGY
from prepare_prompt_set import bundle_payloads, save_bundle, verify_saved_set, json_bytes, digest
from review_assets import (build_catalog, init_review, register_image, make_decision,
                           effective_status, write_manifest, selected_version, canonical)
try:
    from PIL import Image
except ImportError:
    Image=None


def fixture(structured=True):
    context=('### 核心命名人物身份锚\n甲短发，乙长发。\n\n'
             '### 整场空间骨架\n桌在窗旁，门在桌西侧。\n\n'
             '### 人物位置与状态更新\nARCHIVE_FUTURE：09时乙已持匣；此前甲持匣。\n\n'
             '### 参考采用与统一媒介\n无参考；铅笔草图。\n') if structured else '旧稿：甲短发。LEGACY_REQUIRED_STATE。\n'
    text='# 输入回归\n本轮来源：虚构测试；非用户剧本\n本轮范围：01—09\n本次任务：维护测试，不生图\n画幅与媒介：9:16；石墨\n\n## 共用视觉依据\n\n'+context
    text+='\n## 取帧安排\n\n| 源镜 | 必需时点（按镜内时间） | 基准时点 |\n|---|---|---|\n'
    for i in range(1,10):text+=f'| 镜头 {i:02d} | 时点{i} | 时点{i} |\n'
    text+='\n## 第 1 页\n本页范围：自动\n页面说明：初始甲持匣；PAGE_FUTURE：09才交接；顺序左到右上到下。\n'
    for i in range(1,10):
        state='CURRENT_EARLY：甲在门边仍持匣，乙尚未接。' if i==1 else f'OTHER_PANEL_{i}：当前时点{i}，见源镜。'
        text+=f'\n### 格 {i}\n对应来源：镜头 {i:02d}\n画面关系：基准\n所取时点：时点{i}｜{state}\n\n```text\n{state}摄影机在门侧平视，甲在画左，乙在画右；9:16。\n```\n'
    text+='\n## 执行与选用\n只做维护测试。\n'
    return text


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.d=Path(self.tmp.name);self.master=self.d/'master.md';self.master.write_text(fixture())
    def packet(self,panel='1'):
        return prepare_request(self.master,'1',panel,[],[],self.d/'packet.json')
    def bundle(self,folder='set',refs=None,purposes=None):
        out=self.d/folder;files,_=bundle_payloads(self.master,out,references=refs,purposes=purposes,require_selection=True)
        save_bundle(out,files);return out
    def test_single_current_only_archive_retained(self):
        before=self.master.read_bytes();p=self.packet()
        self.assertEqual(p['execution_scope']['status'],'explicit_sections_scoped')
        self.assertIn('CURRENT_EARLY',p['prompt']);self.assertIn('甲短发',p['prompt']);self.assertIn('桌在窗旁',p['prompt'])
        for s in ['ARCHIVE_FUTURE','PAGE_FUTURE','OTHER_PANEL_2']:self.assertNotIn(s,p['prompt'])
        self.assertIn('ARCHIVE_FUTURE',p['shared_context']);self.assertIn('PAGE_FUTURE',p['page_context']['body'])
        self.assertEqual(len(p['drawing_panels']),1);self.assertEqual(p['context_only_panels'],[])
        self.assertEqual(self.master.read_bytes(),before)
    def test_page_keeps_nine_current_frames(self):
        p=self.packet(None);self.assertEqual(len(p['drawing_panels']),9)
        self.assertIn('PAGE_FUTURE',p['prompt']);self.assertIn('OTHER_PANEL_9',p['prompt']);self.assertNotIn('ARCHIVE_FUTURE',p['prompt'])
    def test_reverse_call_order_does_not_mutate_state(self):
        late=self.packet('9');early=self.packet('1');self.assertNotIn('OTHER_PANEL_9',early['prompt']);self.assertNotEqual(late['prompt'],early['prompt'])
    def test_legacy_keeps_dependencies(self):
        self.master.write_text(fixture(False));p=self.packet()
        self.assertEqual(p['execution_scope']['status'],'legacy_full_context');self.assertEqual(len(p['context_only_panels']),8)
        self.assertIn('LEGACY_REQUIRED_STATE',p['prompt']);self.assertIn('PAGE_FUTURE',p['prompt']);self.assertIn('OTHER_PANEL_9',p['prompt'])
    def test_unknown_section_falls_back(self):
        self.master.write_text(fixture().replace('### 核心命名人物身份锚','### 特殊人物条件'))
        p=self.packet();self.assertEqual(p['execution_scope']['status'],'legacy_full_context');self.assertIn('ARCHIVE_FUTURE',p['prompt'])
    def test_duplicate_section_falls_back(self):
        self.master.write_text(fixture().replace('### 整场空间骨架','### 核心命名人物身份锚'))
        self.assertEqual(self.packet()['execution_scope']['status'],'legacy_full_context')
    def test_empty_section_falls_back(self):
        self.master.write_text(fixture().replace('甲短发，乙长发。',''))
        self.assertEqual(self.packet()['execution_scope']['status'],'legacy_full_context')
    def test_fenced_headings_not_selectors(self):
        text=fixture().replace('甲短发，乙长发。','甲短发，乙长发。\n```text\n### 不是分区\n```')
        self.master.write_text(text);p=self.packet();self.assertEqual(p['execution_scope']['status'],'explicit_sections_scoped');self.assertIn('不是分区',p['prompt'])
    def test_invalid_panel_and_source_output(self):
        with self.assertRaises(FormatError):self.packet('10')
        with self.assertRaises(FormatError):prepare_request(self.master,'1','1',[],[],self.master)
    def test_all_formats_equal(self):
        folder=self.bundle();packet=json.loads((folder/'Page-01-input.json').read_text())
        self.assertEqual((folder/'Page-01-prompt.txt').read_bytes(),packet['prompt'].encode())
        self.assertIn(packet['prompt'],(folder/'all-page-prompts.md').read_text())
        self.assertEqual(verify_saved_set(folder)['pages'],1)
        plan=json.loads((folder/'image-plan.json').read_text());self.assertEqual(plan['pages'][0]['execution_basis'],packet['execution_basis'])
        self.assertIn('ARCHIVE_FUTURE',plan['context'])
    def test_basis_mismatch_detected_after_hash_refresh(self):
        folder=self.bundle();manifest=json.loads((folder/'prompt-set-manifest.json').read_text())
        target=folder/'Page-01-input.json';p=json.loads(target.read_text());p['execution_basis']['prompt_sha256']='0'*64;target.write_bytes(json_bytes(p))
        for f in manifest['files']:
            if f['path']==target.name:f['sha256']=digest(target.read_bytes())
        (folder/'prompt-set-manifest.json').write_bytes(json_bytes(manifest))
        with self.assertRaises(FormatError):verify_saved_set(folder)
    def test_old_sets_without_basis_still_read(self):
        folder=self.bundle();manifest=json.loads((folder/'prompt-set-manifest.json').read_text())
        for item in manifest['pages']:item.pop('execution_basis')
        packet=json.loads((folder/'Page-01-input.json').read_text());packet.pop('execution_basis');(folder/'Page-01-input.json').write_bytes(json_bytes(packet))
        plan=json.loads((folder/'image-plan.json').read_text())
        for page in plan['pages']:page.pop('execution_basis')
        (folder/'image-plan.json').write_bytes(json_bytes(plan))
        for f in manifest['files']:f['sha256']=digest((folder/f['path']).read_bytes())
        (folder/'prompt-set-manifest.json').write_bytes(json_bytes(manifest))
        self.assertEqual(verify_saved_set(folder)['pages'],1)
    def test_legacy_catalog_hash_unchanged(self):
        data=parse_master(self.master,'image');item=build_catalog(data,'test')[0];panel=data['pages'][0]['panels'][0]
        spec={k:panel[k] for k in ['source_ref','relation','moment','body']}
        spec.update(shared_context=data['context'],page_context=data['pages'][0]['body'],director_sha256=None,frame_ratio=[9.,16.])
        self.assertEqual(item['spec_sha256'],hashlib.sha256(canonical(spec)).hexdigest())
    def test_strategy_change_invalidates_spec(self):
        data=parse_master(self.master,'image');old=build_catalog(data,'test')[0]
        data['pages'][0]['execution_basis']={'strategy':SCOPE_STRATEGY,'prompt_sha256':'new','references':[]}
        new=build_catalog(data,'test')[0];self.assertEqual(old['uid'],new['uid']);self.assertNotEqual(old['spec_sha256'],new['spec_sha256'])
    def test_no_image_approval(self):
        folder=self.bundle();p=folder/'prompt-set-manifest.json';m=init_review(p)
        with self.assertRaises(FormatError):make_decision(p,m,['01'],'approved','TEST fixture only')
    @unittest.skipIf(Image is None,'Pillow absent; synthetic asset test not run')
    def test_new_revision_pending_unchanged_image_preserved(self):
        folder=self.bundle();p=folder/'prompt-set-manifest.json';m=init_review(p)
        a=self.d/'synthetic.png';Image.new('RGB',(90,160),'white').save(a)
        register_image(p,m,'01',a);register_image(p,m,'02',a)
        make_decision(p,m,['01','02'],'approved','TEST ONLY simulated approval, not a real user decision')
        first=m['review']['panels'][0];second=m['review']['panels'][1]
        saved=folder/selected_version(second)['path'];before=saved.read_bytes()
        register_image(p,m,'01',a)
        self.assertEqual(first['selected_revision'],'r02');self.assertEqual(effective_status(p,first),'pending')
        self.assertEqual(effective_status(p,second),'approved');self.assertEqual(before,saved.read_bytes())
    @unittest.skipIf(Image is None,'Pillow absent; synthetic asset test not run')
    def test_reference_change_invalidates_carried_approval(self):
        ref=self.d/'ref.png';Image.new('RGB',(90,160),'white').save(ref)
        old=self.bundle('old',[ref],['identity only']);p=old/'prompt-set-manifest.json';m=init_review(p)
        register_image(p,m,'01',ref);make_decision(p,m,['01'],'approved','TEST ONLY simulated approval')
        write_manifest(p,m,p.read_bytes())
        new=self.bundle('new',[ref],['shape only']);n=init_review(new/'prompt-set-manifest.json',previous=p)
        self.assertEqual(n['review']['panels'][0]['versions'][0]['decision']['status'],'pending')
        self.assertEqual(effective_status(new/'prompt-set-manifest.json',n['review']['panels'][0]),'stale')
    @unittest.skipIf(Image is None,'Pillow absent; synthetic asset test not run')
    def test_unchanged_binding_carries_review(self):
        old=self.bundle('old');p=old/'prompt-set-manifest.json';m=init_review(p)
        ref=self.d/'synthetic.png';Image.new('RGB',(90,160),'white').save(ref)
        register_image(p,m,'01',ref);make_decision(p,m,['01'],'approved','TEST ONLY simulated approval');write_manifest(p,m,p.read_bytes())
        new=self.bundle('new');n=init_review(new/'prompt-set-manifest.json',previous=p)
        self.assertEqual(effective_status(new/'prompt-set-manifest.json',n['review']['panels'][0]),'approved')


if __name__=='__main__':unittest.main()
