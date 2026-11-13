# SPDX-License-Identifier: MIT
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, sys.argv.pop(1) if len(sys.argv) > 1 else str(Path(__file__).parent))
import installed


class InstalledOutputsTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        self.build = self.work / 'build'
        self.build.mkdir()
        self.prefix = self.work / 'prefix'

    def fixture(self, root=None, destination='bin'):
        root = root or self.prefix
        (root / 'bin').mkdir(parents=True)
        self.file = root / 'bin/tool'
        self.file.write_text('installed executable\n')
        self.manifest = self.build / 'install_manifest.txt'
        self.manifest.write_text(str(self.file) + '\n')
        (self.build / 'CMakeCache.txt').write_text('CMAKE_INSTALL_PREFIX:PATH=' + str(root) + '\n')
        reply = self.build / '.cmake/api/v1/reply'
        reply.mkdir(parents=True)
        (reply / 'index-1.json').write_text(json.dumps({'objects': [{'kind': 'codemodel', 'jsonFile': 'model.json'}]}))
        (reply / 'model.json').write_text(json.dumps({'configurations': [{'targets': [{'jsonFile': 'tool.json'}]}]}))
        (reply / 'tool.json').write_text(json.dumps({
            'name': 'tool', 'type': 'EXECUTABLE', 'artifacts': [{'path': 'intermediates/tool'}],
            'install': {'destinations': [{'path': str(destination)}]},
        }))

    def read(self):
        return installed.read_outputs(self.build, self.prefix)

    def test_requested_prefix_keeps_existing_contract(self):
        self.fixture()
        (self.build / 'CMakeCache.txt').write_text('CMAKE_INSTALL_PREFIX:PATH=/usr/local\n')
        self.assertEqual(self.read(), {
            'files': ['bin/tool'],
            'targets': {'tool': {'type': 'EXECUTABLE', 'files': ['bin/tool']}},
        })

    def test_owned_bundle_and_absolute_file_api_destination(self):
        bundle = self.build / 'bundle'
        self.fixture(bundle, bundle / 'bin')
        self.assertFalse(self.prefix.exists())
        self.assertEqual(self.read(), {
            'files': ['bin/tool'],
            'targets': {'tool': {'type': 'EXECUTABLE', 'files': ['bin/tool']}},
        })

    def test_repeated_install_destinations_preserve_lock_multiplicity(self):
        self.fixture()
        target_file = self.build / '.cmake/api/v1/reply/tool.json'
        target = json.loads(target_file.read_text())
        target['install']['destinations'].append({'path': 'bin'})
        target_file.write_text(json.dumps(target))
        self.assertEqual(self.read(), {
            'files': ['bin/tool'],
            'targets': {'tool': {'type': 'EXECUTABLE', 'files': ['bin/tool', 'bin/tool']}},
        })

    def test_empty_requested_directory_does_not_hide_bundle(self):
        self.prefix.mkdir()
        bundle = self.build / 'bundle'
        self.fixture(bundle, bundle / 'bin')
        self.assertEqual(self.read()['files'], ['bin/tool'])

    def test_no_install_rules_keeps_null(self):
        self.assertIsNone(self.read())
        (self.build / 'install_manifest.txt').write_text('')
        self.assertIsNone(self.read())

    def test_external_cache_prefix_is_rejected(self):
        self.fixture(self.work / 'external')
        with self.assertRaisesRegex(ValueError, 'outside its owned directory'):
            self.read()

    def test_mixed_prefixes_are_rejected(self):
        self.fixture(self.build / 'bundle')
        self.prefix.mkdir()
        other = self.prefix / 'other'
        other.write_text('other')
        self.manifest.write_text(str(self.file) + '\n' + str(other) + '\n')
        with self.assertRaisesRegex(ValueError, 'escapes the captured prefix'):
            self.read()

    def test_manifest_traversal_is_rejected_even_if_it_resolves_inside(self):
        self.fixture()
        self.manifest.write_text(str(self.prefix / 'bin/../bin/tool') + '\n')
        with self.assertRaisesRegex(ValueError, 'without traversal'):
            self.read()

    def test_missing_file_is_rejected(self):
        self.fixture()
        self.file.unlink()
        with self.assertRaisesRegex(ValueError, 'missing, dangling'):
            self.read()

    def test_dangling_link_is_rejected(self):
        self.fixture()
        self.file.unlink()
        self.file.symlink_to('missing')
        with self.assertRaisesRegex(ValueError, 'missing, dangling'):
            self.read()

    def test_escaping_leaf_link_is_rejected(self):
        self.fixture()
        outside = self.work / 'outside'
        outside.write_text('outside')
        self.file.unlink()
        self.file.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'escapes the captured prefix'):
            self.read()

    def test_escaping_ancestor_link_is_rejected(self):
        self.fixture()
        self.file.unlink()
        self.file.parent.rmdir()
        outside = self.work / 'outside'
        outside.mkdir()
        (outside / 'tool').write_text('outside')
        (self.prefix / 'bin').symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'escapes the captured prefix'):
            self.read()

    def test_bundle_root_link_cannot_escape_owned_build(self):
        outside = self.work / 'outside'
        outside.mkdir()
        bundle = self.build / 'bundle'
        bundle.symlink_to(outside)
        self.fixture(bundle, bundle / 'bin')
        with self.assertRaisesRegex(ValueError, 'outside its owned directory'):
            self.read()

    def test_internal_existing_links_are_preserved(self):
        self.fixture()
        alias = self.file.parent / 'alias'
        alias.symlink_to('tool')
        self.manifest.write_text(str(self.file) + '\n' + str(alias) + '\n')
        self.assertEqual(self.read()['files'], ['bin/alias', 'bin/tool'])

    def test_file_api_destination_traversal_is_rejected(self):
        self.fixture(destination='../outside')
        with self.assertRaisesRegex(ValueError, 'File API.*traversal'):
            self.read()

    def test_uninstalled_external_file_api_hint_is_omitted(self):
        self.fixture(destination=self.work / 'outside')
        self.assertEqual(self.read(), {'files': ['bin/tool'], 'targets': {}})

    def test_uninstalled_file_api_hint_with_escaping_ancestor_is_omitted(self):
        optional = self.prefix / 'optional'
        self.fixture(destination=optional)
        outside = self.work / 'outside'
        outside.mkdir()
        (outside / 'tool').write_text('not installed')
        optional.symlink_to(outside)
        self.assertEqual(self.read(), {'files': ['bin/tool'], 'targets': {}})

    def test_uninstalled_file_api_hint_needs_no_existing_destination(self):
        self.fixture(destination=self.prefix / 'optional')
        self.assertFalse((self.prefix / 'optional').exists())
        self.assertEqual(self.read(), {'files': ['bin/tool'], 'targets': {}})


if __name__ == '__main__':
    unittest.main()
