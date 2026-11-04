import os
import tempfile
import unittest
from pathlib import Path
from rpg.files import locked_file


class WindowsFileTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Windows sharing semantics require a Windows machine')
    def test_continuity_writer_denies_concurrent_editor_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'Character.txt'
            path.write_text('original', encoding='utf-8')
            with locked_file(path, exclusive_write=True):
                with self.assertRaises(OSError):
                    with path.open('wb') as stream:
                        stream.write(b'editor edit')
            self.assertEqual(path.read_text(), 'original')
