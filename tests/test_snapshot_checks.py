"""Finite hand witnesses and mutations. No new answer-model calls."""
from copy import deepcopy
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import unittest

from hand_fixture import fixture
from snapshot_checks import InvalidSnapshot,bounded_shape,current,input_id,load_current,load_generation,preserved,sha,load_directory,prepared_snapshots
from view_checks import both_views,expected_input,original_view

def materialize(store,case,release,original):
    """Write only supplied hand-labelled values, never solve a source file."""
    payload=expected_input(case);generation=input_id(payload)
    root=Path(store)/'generations'/generation;root.mkdir(parents=True,exist_ok=True)
    meta={'generation':generation,'input':payload,'files':{}}
    for name,rows in [('release.jsonl',release),('original.jsonl',original)]:
        raw=b''.join((json.dumps(row,ensure_ascii=False)+'\n').encode() for row in rows)
        (root/name).write_bytes(raw)
        meta['files'][name]={'sha256':sha(raw),'rows':len(rows)}
    (root/'manifest.json').write_text(json.dumps(meta)+'\n',encoding='utf-8')
    return generation,root

def second_fixture():
    case,release,original=fixture()
    source=case.batches[0];record=source.records[0]
    record=replace(record,samples=(('S',('0|1',[11,20],[101,102,103])),))
    source=replace(source,records=(record,*source.records[1:]))
    case=replace(case,batches=(source,*case.batches[1:]))
    release[0]['samples'][0]['winner']['values']['AD']=[11,20,None]
    original[0]['samples'][0]['values']['AD']=[11,20]
    return case,release,original

class SnapshotChecks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Path(self.temp.name)
        self.case,self.release,self.original=fixture()
        self.generation,self.root=materialize(self.store,self.case,self.release,self.original)
        (self.store/'CURRENT').write_bytes((self.generation+'\n').encode())

    def tearDown(self):self.temp.cleanup()

    def test_hand_snapshot(self):
        snapshot=load_current(self.store,expected_input(self.case))
        self.assertTrue(both_views(self.case,snapshot))

    def test_prepared_is_checkable_without_current_change(self):
        case,release,original=second_fixture()
        generation,_=materialize(self.store,case,release,original)
        self.assertEqual(current(self.store),self.generation)
        self.assertTrue(both_views(case,load_generation(self.store,generation)))

    def staged_fixture(self):
        case,release,original=second_fixture()
        generation,root=materialize(self.store,case,release,original)
        staged=self.store/'internal-layout'/'opaque-prepared-name'
        staged.parent.mkdir();root.rename(staged)
        return case,generation,staged

    def test_arbitrary_staging_layout_is_allowed(self):
        before=load_current(self.store)
        case,generation,staged=self.staged_fixture()
        self.assertTrue(both_views(case,load_directory(staged,generation)))
        self.assertTrue(any(both_views(case,s) for s in prepared_snapshots(self.store,generation)))
        self.assertTrue(preserved(before,load_current(self.store)))
        with self.assertRaises(InvalidSnapshot):load_generation(self.store,generation)

    def test_missing_staged_artifact_is_not_prepared(self):
        _,generation,staged=self.staged_fixture()
        (staged/'original.jsonl').unlink()
        self.assertEqual(list(prepared_snapshots(self.store,generation)),[])

    def test_wrong_staged_digest_is_not_prepared(self):
        _,generation,staged=self.staged_fixture()
        with (staged/'release.jsonl').open('ab') as stream:stream.write(b'{}\n')
        self.assertEqual(list(prepared_snapshots(self.store,generation)),[])

    def test_correct_staged_hashes_do_not_prove_semantics(self):
        case,generation,staged=self.staged_fixture()
        wrong=json.loads((staged/'original.jsonl').read_bytes().splitlines()[0])
        wrong['reference']='WRONG'
        rows=(staged/'original.jsonl').read_bytes().splitlines()
        rows[0]=json.dumps(wrong).encode()
        raw=b'\n'.join(rows)+b'\n';(staged/'original.jsonl').write_bytes(raw)
        meta=json.loads((staged/'manifest.json').read_bytes())
        meta['files']['original.jsonl']['sha256']=sha(raw)
        (staged/'manifest.json').write_text(json.dumps(meta))
        snapshots=list(prepared_snapshots(self.store,generation))
        self.assertEqual(len(snapshots),1)
        self.assertFalse(any(both_views(case,s) for s in snapshots))

    def test_symlink_staging_directory_is_not_followed(self):
        _,generation,staged=self.staged_fixture()
        outside=self.store.parent/(self.store.name+'-outside')
        staged.rename(outside)
        try:
            staged.symlink_to(outside,target_is_directory=True)
            self.assertEqual(list(prepared_snapshots(self.store,generation)),[])
        finally:
            staged.unlink();outside.rename(staged)

    def test_symlink_staged_file_is_rejected(self):
        _,generation,staged=self.staged_fixture()
        view=staged/'original.jsonl';other=staged/'another-name'
        view.rename(other);view.symlink_to(other)
        self.assertEqual(list(prepared_snapshots(self.store,generation)),[])

    def test_fifo_staged_file_does_not_block_checker(self):
        _,generation,staged=self.staged_fixture()
        view=staged/'original.jsonl';view.unlink();os.mkfifo(view)
        self.assertEqual(list(prepared_snapshots(self.store,generation)),[])

    def test_bad_copy_does_not_mask_valid_staged_copy(self):
        case,generation,staged=self.staged_fixture()
        bad=self.store/'generations'/generation;bad.mkdir()
        (bad/'manifest.json').write_bytes(b'not JSON')
        self.assertTrue(any(both_views(case,s) for s in prepared_snapshots(self.store,generation)))

    def test_pinned_old_reader_after_pointer_change(self):
        case,release,original=second_fixture()
        generation,_=materialize(self.store,case,release,original)
        before=load_current(self.store)
        (self.store/'CURRENT').write_bytes((generation+'\n').encode())
        self.assertTrue(preserved(before,load_generation(self.store,self.generation)))
        self.assertTrue(both_views(case,load_current(self.store)))

    def test_reformat_old_manifest_is_not_immutable(self):
        before=load_current(self.store)
        manifest=json.loads((self.root/'manifest.json').read_bytes())
        (self.root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        self.assertFalse(preserved(before,load_current(self.store)))

    def test_missing_current(self):
        (self.store/'CURRENT').unlink()
        self.assertIsNone(current(self.store))
        with self.assertRaises(InvalidSnapshot):load_current(self.store)

    def test_partial_current(self):
        for raw in [b'',b'a'*64,b'a'*63+b'\n',b'../escape\n',b'A'*64+b'\n',b'a'*64+b'\r\n']:
            with self.subTest(raw=raw):
                (self.store/'CURRENT').write_bytes(raw)
                with self.assertRaises(InvalidSnapshot):current(self.store)

    def test_missing_artifacts(self):
        for name in ['release.jsonl','original.jsonl','manifest.json']:
            with self.subTest(name=name):
                path=self.root/name;raw=path.read_bytes();path.unlink()
                with self.assertRaises(InvalidSnapshot):load_current(self.store)
                path.write_bytes(raw)

    def test_truncated_view(self):
        path=self.root/'original.jsonl';path.write_bytes(path.read_bytes()[:-10])
        with self.assertRaises(InvalidSnapshot):load_current(self.store)

    def test_wrong_count_including_bool(self):
        path=self.root/'manifest.json';meta=json.loads(path.read_bytes())
        for count in [0,-1,True,'3',3.0]:
            with self.subTest(count=count):
                meta['files']['original.jsonl']['rows']=count
                path.write_text(json.dumps(meta))
                with self.assertRaises(InvalidSnapshot):load_current(self.store)

    def test_json_duplicate_key(self):
        path=self.root/'manifest.json'
        raw=path.read_text();path.write_text(raw[:-2]+',"generation":"'+self.generation+'"}\n')
        with self.assertRaises(InvalidSnapshot):load_current(self.store)

    def test_wrong_input_payload(self):
        case,_,_=second_fixture()
        with self.assertRaises(InvalidSnapshot):load_current(self.store,expected_input(case))

    def test_mixed_generation_metadata(self):
        path=self.root/'manifest.json';meta=json.loads(path.read_bytes());meta['generation']='f'*64
        path.write_text(json.dumps(meta))
        with self.assertRaises(InvalidSnapshot):load_current(self.store)

    def test_self_consistent_digest_does_not_prove_views(self):
        wrong=deepcopy(self.original);wrong[0]['reference']='AC';wrong[0]['alternate']=['GC']
        materialize(self.store,self.case,self.release,wrong)
        self.assertFalse(both_views(self.case,load_current(self.store)))

    def test_source_dictionary_order_is_preserved(self):
        wrong=deepcopy(self.original);wrong[0]['alternate']=['C','G']
        self.assertFalse(original_view(self.case,wrong))

    def test_loss_and_duplication_of_original_records(self):
        for wrong in [self.original[:-1],self.original+[self.original[0]],list(reversed(self.original))]:
            self.assertFalse(original_view(self.case,wrong))

    def test_wrong_original_observation(self):
        for key,value in [('GT','1|0'),('AD',[20,10]),('PL',[103,102,101])]:
            with self.subTest(key=key):
                wrong=deepcopy(self.original);wrong[0]['samples'][0]['values'][key]=value
                self.assertFalse(original_view(self.case,wrong))

    def test_origin_types_and_field_loss(self):
        for operation in ['bool_ordinal','bool_position','missing_pl','drop_sample']:
            with self.subTest(operation=operation):
                wrong=deepcopy(self.original)
                if operation=='bool_ordinal':wrong[0]['ordinal']=False
                elif operation=='bool_position':wrong[0]['position']=True
                elif operation=='missing_pl':del wrong[0]['samples'][0]['values']['PL']
                else:wrong[0]['samples']=[]
                self.assertFalse(original_view(self.case,wrong))

    def test_published_dictionary_permutation_is_allowed(self):
        changed=deepcopy(self.release);row=changed[0];row['alternate']=['TC','GC']
        sample=row['samples'][0]
        sample['winner']['values']={'GT':'0|2','AD':[10,None,20],'PL':[101,None,None,102,None,103]}
        sample['others'][0]['values']={'GT':'2|2','AD':[12,None,22],'PL':[111,None,None,112,None,113]}
        sample['others'][1]['values']={'GT':'0|1','AD':[30,40,None],'PL':[201,202,203,None,None,None]}
        materialize(self.store,self.case,changed,self.original)
        self.assertTrue(both_views(self.case,load_current(self.store)))

    def test_format_order_is_allowed(self):
        changed=deepcopy(self.original)
        for row in changed:row['format'].reverse()
        self.assertTrue(original_view(self.case,changed))

    def test_published_raw_index_shortcut(self):
        wrong=deepcopy(self.release);wrong[0]['samples'][0]['others'][1]['values']['GT']='0|1'
        materialize(self.store,self.case,wrong,self.original)
        self.assertFalse(both_views(self.case,load_current(self.store)))

    def test_changed_source_order_changes_id(self):
        value=expected_input(self.case);other=deepcopy(value);other['sources'].reverse()
        self.assertNotEqual(input_id(value),input_id(other))

    def test_input_extra_paths_are_not_permitted(self):
        value=expected_input(self.case);value['sources'][0]['path']='ignored'
        with self.assertRaises(AssertionError):input_id(value)

    def test_resource_shape_only_a_draft(self):
        self.assertTrue(bounded_shape(20000,22000))
        self.assertFalse(bounded_shape(100000,200000))
        self.assertFalse(bounded_shape(210000,210000))
        self.assertFalse(bounded_shape(True,0))

if __name__=='__main__':unittest.main()
