import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from confined_files import SafeTree
import host


def blob(data):
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()


class BootstrapSelectionTests(unittest.TestCase):
    def test_resolved_system_timezone_bind_is_part_of_bootstrap_recovery(self):
        rows = [{'Config':{'Labels':None},'Mounts':[{'Type':'bind','Source':'/etc/localtime'}]}]
        zone = Path('/usr/share/zoneinfo/Etc/UTC')
        with patch.object(Path,'is_file',return_value=True),patch.object(Path,'resolve',return_value=zone):
            self.assertIn(zone,host.bootstrap_files(rows,[]))
    def test_runtime_bind_file_outside_admitted_bootstrap_roots_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'outside';source.write_bytes(b'private')
            rows = [{'Config': {'Labels': None}, 'Mounts': [{'Type': 'bind', 'Source': str(source)}]}]
            with self.assertRaisesRegex(ValueError, 'Unadmitted bootstrap'):
                host.bootstrap_files(rows, [])

    def test_git_submodule_or_escaping_path_is_not_a_source_blob(self):
        for row in [b'160000 commit '+b'a'*40+b' 0\tsubmodule\0',
                    b'100644 blob '+b'a'*40+b' 1\t../outside\0']:
            with self.subTest(row=row), patch.object(host, 'command', return_value=row):
                with self.assertRaises(ValueError):host.tree_manifest()


@unittest.skipUnless(sys.platform == 'linux' and getattr(os, 'geteuid', lambda: -1)() == 0,
                     'Bootstrap archive and cleanup use native root descriptors')
class HostBootstrapProofTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name);self.root.chmod(0o700)

    def test_partial_root_manifest_cannot_be_credited_as_full_host_recovery(self):
        proof = {'method':'full_host_online_sqlite_and_current_deployment_bootstrap',
                 'runtimeContainers':49,'protectedOverlays':45,
                 'trees':{'r000':{'source':'/home/rubiss'}},'optionalAbsentRoots':[]}
        (self.root/'capture.json').write_text(json.dumps(proof))
        with self.assertRaisesRegex(ValueError,'admitted full roots'):
            host.inspect_capture(self.root)

    def test_empty_key_root_cannot_be_credited_as_recoverable_bootstrap(self):
        trees={f'r{i:03d}':{'source':str(path),'proof':{'entries':{},'sqliteDatabases':{}}}
               for i,path in enumerate([*host.ROOTS,host.REPOSITORY/'.git/git-crypt'])}
        trees['r000']['proof'].update(entries={'.codex/auth.json':{'kind':'file','bytes':1}},
                                     sqliteDatabases={'.t3/userdata/statev2.sqlite':{}})
        proof={'method':'full_host_online_sqlite_and_current_deployment_bootstrap','runtimeContainers':49,
               'protectedOverlays':45,'trees':trees,'optionalAbsentRoots':['/root/.docker','/root/.ssh','/root/.config/gh']}
        (self.root/'capture.json').write_text(json.dumps(proof))
        with self.assertRaisesRegex(ValueError,'Git-crypt key files'):
            host.inspect_capture(self.root)

    def test_git_archive_matches_complete_blob_manifest_and_preserves_link_identity(self):
        regular = b'configuration';link = b'../outside'
        with tarfile.open(self.root/'source-tree.tar', 'w') as archive:
            entry = tarfile.TarInfo('config');entry.size = len(regular);archive.addfile(entry, io.BytesIO(regular))
            entry = tarfile.TarInfo('link');entry.type = tarfile.SYMTYPE;entry.linkname = link.decode();archive.addfile(entry)
        manifest = {'config': {'mode':'100644','bytes':len(regular),'blobSha1':blob(regular)},
                    'link': {'mode':'120000','bytes':len(link),'blobSha1':blob(link)}}
        with SafeTree(self.root) as tree:
            host.inspect_archive(tree, manifest)
            with self.assertRaises(ValueError):host.inspect_archive(tree, {'config':manifest['config']})
            manifest['link']['mode'] = '100644'
            with self.assertRaisesRegex(ValueError, 'type differs'):host.inspect_archive(tree, manifest)

    def test_filtered_secret_export_must_match_the_paired_unlocked_copy(self):
        plaintext=b'fixture secret';stored=b'fixture encrypted Git blob'
        (self.root/'files').mkdir();(self.root/'files/f000').write_bytes(plaintext)
        with tarfile.open(self.root/'source-tree.tar','w') as archive:
            entry=tarfile.TarInfo('service/.env.secret');entry.size=len(plaintext);archive.addfile(entry,io.BytesIO(plaintext))
        source=host.REPOSITORY/'service/.env.secret'
        raw={'service/.env.secret':{'mode':'100644','bytes':len(stored),'blobSha1':blob(stored)}}
        copies={'f000':{'source':str(source),'bytes':len(plaintext),'sha256':hashlib.sha256(plaintext).hexdigest()}}
        manifest=host.archive_manifest(raw,copies,[source])
        with SafeTree(self.root) as tree:
            host.inspect_archive(tree,manifest)
            (self.root/'files/f000').write_bytes(b'wrong secret')
            with self.assertRaisesRegex(ValueError,'Protected Git export differs'):
                host.inspect_archive(tree,manifest)

    def job(self, index, **changes):
        directory = self.root/f'202611{index:02d}T000000Z-{index:08x}';directory.mkdir(mode=0o700)
        for name in ['capture','restore']:
            (directory/name).mkdir();(directory/name/'fixture').write_bytes(b'private fixture')
        value = {'scope':'host','success':True,'phase':'complete','encryptedRepositoryCaptureVerified':True,
                 'restoreReadbackVerified':True,'snapshotId':f'{index:064x}', **changes}
        (directory/'job.json').write_text(json.dumps(value))
        snapshot = {'id':value['snapshotId'],'hostname':'ben-server','tags':['native-recurring','scope=host'],'paths':[str(directory/'capture')]}
        return directory,snapshot

    def test_cleanup_only_removes_old_proven_payloads_and_never_follows_saved_links(self):
        old,snapshot = self.job(1);self.job(2);self.job(3);current,_ = self.job(4)
        foreign,_ = self.job(5, scope='n8n');failed,_ = self.job(6, success=False)
        sentinel = self.root/'sentinel';sentinel.mkdir();(sentinel/'keep').write_bytes(b'intact')
        (old/'capture/link').symlink_to(sentinel, target_is_directory=True)
        repo = SimpleNamespace(run=lambda *args:json.dumps([snapshot]))
        with patch.object(host, 'HOST_STATE', self.root):
            result = host.cleanup_verified_payloads(self.root, current, repo)
            self.assertEqual(result['removedPayloadJobs'], [old.name])
            self.assertEqual(host.cleanup_verified_payloads(self.root, current, repo)['removedPayloadJobs'], [])
        self.assertFalse((old/'capture').exists());self.assertFalse((old/'restore').exists())
        self.assertTrue((old/'job.json').exists());self.assertTrue((old/'payload-removed.json').exists())
        self.assertTrue((foreign/'capture').exists());self.assertTrue((failed/'capture').exists())
        self.assertEqual((sentinel/'keep').read_bytes(), b'intact')

    def test_cleanup_retains_payload_without_its_matching_owned_nas_snapshot(self):
        old,snapshot = self.job(1);self.job(2);self.job(3);current,_ = self.job(4)
        snapshot['paths'] = ['/some/other/capture']
        with patch.object(host, 'HOST_STATE', self.root):
            result = host.cleanup_verified_payloads(self.root,current,SimpleNamespace(run=lambda *a:json.dumps([snapshot])))
        self.assertEqual(result['unprovenPayloadJobsRetained'], [old.name])
        self.assertTrue((old/'capture').is_dir());self.assertTrue((old/'restore').is_dir())

    def test_cleanup_rejects_symlink_payload_without_touching_its_target(self):
        old,snapshot = self.job(1);self.job(2);self.job(3);current,_ = self.job(4)
        (old/'capture/fixture').unlink();(old/'capture').rmdir()
        sentinel=self.root/'sentinel';sentinel.mkdir();(sentinel/'keep').write_bytes(b'intact')
        (old/'capture').symlink_to(sentinel,target_is_directory=True)
        with patch.object(host, 'HOST_STATE', self.root), self.assertRaisesRegex(ValueError,'not a directory'):
            host.cleanup_verified_payloads(self.root,current,SimpleNamespace(run=lambda *a:json.dumps([snapshot])))
        self.assertEqual((sentinel/'keep').read_bytes(),b'intact')


if __name__ == '__main__':unittest.main()
