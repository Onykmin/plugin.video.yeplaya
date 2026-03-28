# -*- coding: utf-8 -*-
"""Tests for safe_extract_zip — path traversal security."""
import sys
import os
import zipfile
import tempfile
import shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from lib.database import safe_extract_zip


class TestSafeExtractZip:
    def _make_zip(self, members, tmpdir):
        """Create a ZIP with given member names and return path."""
        zip_path = os.path.join(tmpdir, 'test.zip')
        with zipfile.ZipFile(zip_path, 'w') as zf:
            for name in members:
                zf.writestr(name, 'content')
        return zip_path

    def test_valid_extraction(self):
        tmpdir = tempfile.mkdtemp()
        try:
            zip_path = self._make_zip(['file.txt', 'subdir/file2.txt'], tmpdir)
            extract_to = os.path.join(tmpdir, 'out')
            os.makedirs(extract_to)
            assert safe_extract_zip(zip_path, extract_to) is True
            assert os.path.exists(os.path.join(extract_to, 'file.txt'))
            assert os.path.exists(os.path.join(extract_to, 'subdir', 'file2.txt'))
        finally:
            shutil.rmtree(tmpdir)

    def test_path_traversal_blocked(self):
        tmpdir = tempfile.mkdtemp()
        try:
            zip_path = self._make_zip(['../../../etc/passwd'], tmpdir)
            extract_to = os.path.join(tmpdir, 'out')
            os.makedirs(extract_to)
            assert safe_extract_zip(zip_path, extract_to) is False
            # File should NOT have been extracted
            assert not os.path.exists(os.path.join(tmpdir, 'etc', 'passwd'))
        finally:
            shutil.rmtree(tmpdir)

    def test_absolute_path_blocked(self):
        tmpdir = tempfile.mkdtemp()
        try:
            zip_path = self._make_zip(['/tmp/evil.txt'], tmpdir)
            extract_to = os.path.join(tmpdir, 'out')
            os.makedirs(extract_to)
            assert safe_extract_zip(zip_path, extract_to) is False
        finally:
            shutil.rmtree(tmpdir)

    def test_bad_zip_file(self):
        tmpdir = tempfile.mkdtemp()
        try:
            bad_path = os.path.join(tmpdir, 'bad.zip')
            with open(bad_path, 'w') as f:
                f.write('not a zip')
            assert safe_extract_zip(bad_path, tmpdir) is False
        finally:
            shutil.rmtree(tmpdir)

    def test_deep_traversal_blocked(self):
        tmpdir = tempfile.mkdtemp()
        try:
            # ../../../ goes well outside extract_to
            zip_path = self._make_zip(['a/../../../outside.txt'], tmpdir)
            extract_to = os.path.join(tmpdir, 'out')
            os.makedirs(extract_to)
            assert safe_extract_zip(zip_path, extract_to) is False
        finally:
            shutil.rmtree(tmpdir)
