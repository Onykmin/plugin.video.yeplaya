# -*- coding: utf-8 -*-
"""safe_extract_zip: archive members must never land outside the target dir."""
import zipfile

import pytest

from lib.database import safe_extract_zip


def make_zip(tmp_path, members):
    path = tmp_path / 'test.zip'
    with zipfile.ZipFile(path, 'w') as zf:
        for name in members:
            zf.writestr(name, 'content')
    return str(path)


@pytest.fixture
def dest(tmp_path):
    d = tmp_path / 'out'
    d.mkdir()
    return d


def test_valid_archive_is_extracted(tmp_path, dest):
    assert safe_extract_zip(make_zip(tmp_path, ['file.txt', 'sub/file2.txt']), str(dest)) is True
    assert (dest / 'file.txt').is_file()
    assert (dest / 'sub' / 'file2.txt').is_file()


@pytest.mark.parametrize('member', [
    '../../../etc/passwd',
    'a/../../../outside.txt',
    '/tmp/evil.txt',
    '../out_evil/x.txt',  # sibling sharing the destination's name as prefix
])
def test_escaping_member_rejects_whole_archive(tmp_path, dest, member):
    assert safe_extract_zip(make_zip(tmp_path, ['ok.txt', member]), str(dest)) is False
    # validation happens before extraction: nothing is written, even the harmless member
    assert list(dest.iterdir()) == []
    assert not (tmp_path / 'out_evil').exists()


def test_corrupt_archive_returns_false(tmp_path, dest):
    bad = tmp_path / 'bad.zip'
    bad.write_text('not a zip')
    assert safe_extract_zip(str(bad), str(dest)) is False
