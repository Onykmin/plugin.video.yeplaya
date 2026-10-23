# -*- coding: utf-8 -*-
"""Offline database browsing: loading JSON dumps from the profile folder."""
import importlib
import json

import pytest


@pytest.fixture
def dbm(monkeypatch, tmp_path):
    mod = importlib.import_module('lib.database')
    (tmp_path / 'db').mkdir()
    added = []
    monkeypatch.setattr(mod, '_profile', str(tmp_path))
    monkeypatch.setattr(mod, 'revalidate', lambda: 'TOK')
    monkeypatch.setattr(mod.xbmcplugin, 'addDirectoryItem',
                        lambda handle, url, item, folder: added.append((url, item.label, folder)))
    mod.added, mod.root = added, tmp_path
    return mod


def write(dbm, name, data):
    (dbm.root / 'db' / name).write_text(json.dumps({'data': data}), encoding='utf8')


def test_loaddb_returns_data_section(dbm):
    write(dbm, 'films.json', [{'id': '1', 'title': 'A'}])
    assert dbm.loaddb(str(dbm.root / 'db'), 'films.json') == [{'id': '1', 'title': 'A'}]


@pytest.mark.parametrize('content', ['{not json', '{"other": 1}'])
def test_loaddb_returns_empty_on_corrupt_or_unexpected_file(dbm, content):
    (dbm.root / 'db' / 'bad.json').write_text(content)
    assert dbm.loaddb(str(dbm.root / 'db'), 'bad.json') == {}


def test_loaddb_returns_empty_when_file_missing(dbm):
    assert dbm.loaddb(str(dbm.root / 'db'), 'nope.json') == {}


def test_db_root_lists_available_dumps_as_folders(dbm):
    write(dbm, 'films.json', [])
    dbm.db({})
    assert [(label, folder) for _, label, folder in dbm.added] == [('films', True)]
    assert 'file=films.json' in dbm.added[0][0]


def test_db_file_lists_titles_as_folders(dbm):
    write(dbm, 'films.json', [{'id': '1', 'title': 'Alpha'}, {'id': '2', 'title': 'Beta'}])
    dbm.db({'file': 'films.json'})
    assert [(label, folder) for _, label, folder in dbm.added] == [('Alpha', True), ('Beta', True)]
    assert 'key=2' in dbm.added[1][0]


def test_db_file_param_cannot_read_outside_db_folder(dbm):
    (dbm.root / 'secret.json').write_text(json.dumps({'data': [{'id': '1', 'title': 'LEAK'}]}))
    dbm.db({'file': '../secret.json'})
    assert dbm.added == []


def test_db_stream_listing_for_one_title(dbm):
    write(dbm, 'films.json', [{'id': '1', 'title': 'Alpha', 'streams': [
        {'ident': 'abc', 'quality': '1080p', 'lang': 'CZ', 'ainfo': ' 5.1', 'size': '1 GB'}]}])
    dbm.db({'file': 'films.json', 'key': '1'})
    assert [(label, folder) for _, label, folder in dbm.added] == [('1080p - CZ 5.1', False)]
    assert 'ident=abc' in dbm.added[0][0]


def test_db_unknown_key_lists_nothing(dbm):
    write(dbm, 'films.json', [{'id': '1', 'title': 'Alpha', 'streams': []}])
    dbm.db({'file': 'films.json', 'key': 'zzz'})
    assert dbm.added == []


def test_db_missing_dir_and_failed_download_does_not_crash(dbm, monkeypatch):
    import shutil
    shutil.rmtree(dbm.root / 'db')
    monkeypatch.setattr(dbm, 'getlink', lambda ident, token: None)
    dbm.db({})
    assert dbm.added == []
    assert not (dbm.root / 'db').exists()


def test_db_corrupt_download_is_discarded_so_next_run_retries(dbm, monkeypatch):
    import shutil

    class Resp:
        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size):
            yield b'not a zip'

    shutil.rmtree(dbm.root / 'db')
    monkeypatch.setattr(dbm, 'getlink', lambda ident, token: 'http://x/db.zip')
    monkeypatch.setattr(dbm._session, 'get', lambda *a, **k: Resp(), raising=False)
    dbm.db({})
    assert not (dbm.root / 'db.zip').exists()
    assert not (dbm.root / 'db').exists()
