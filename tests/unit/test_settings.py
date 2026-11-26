# -*- coding: utf-8 -*-
"""resources/settings.xml invariants the code relies on."""
import os
import re
import xml.etree.ElementTree as ET

import pytest

SETTINGS = os.path.join(os.path.dirname(__file__), '..', '..', 'resources', 'settings.xml')


@pytest.fixture(scope='module')
def settings():
    return {s.get('id'): s for s in ET.parse(SETTINGS).getroot().iter('setting') if s.get('id')}


def test_group_movies_is_standalone_and_on_by_default(settings):
    s = settings['group_movies']
    assert s.get('enable') is None
    assert s.get('default') == 'true'


def test_device_uuid_is_hidden_from_the_user(settings):
    assert settings['duuid'].get('visible') == 'false'


def test_label_format_only_enabled_when_custom_format_is_on(settings):
    # relative reference: the setting directly above must be `customformat`
    assert settings['labelformat'].get('enable') == 'eq(-1,true)'
    ids = [s.get('id') for s in ET.parse(SETTINGS).getroot().iter('setting')]
    assert ids[ids.index('labelformat') - 1] == 'customformat'


def test_removed_slast_setting_stays_removed(settings):
    assert 'slast' not in settings


LANG_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'resources', 'language')
LANGUAGES = ('resource.language.en_gb', 'resource.language.cs_cz', 'resource.language.sk_sk')


def _po_ids(lang):
    path = os.path.join(LANG_DIR, lang, 'strings.po')
    with open(path, encoding='utf8') as f:
        return set(re.findall(r'^msgctxt "#(\d+)"', f.read(), re.M))


def test_random_episode_next_is_a_three_way_select_defaulting_to_off(settings):
    s = settings['random_episode_next']
    assert s.get('type') == 'select'
    assert s.get('default') == '0'
    assert len(s.get('lvalues').split('|')) == 3


def test_random_episode_next_lvalues_are_the_new_labels(settings):
    s = settings['random_episode_next']
    assert s.get('label') == '30456'
    assert s.get('lvalues') == '30457|30458|30459'


def test_random_episode_next_sits_directly_after_random_episode_and_depends_on_it(settings):
    ids = [s.get('id') for s in ET.parse(SETTINGS).getroot().iter('setting')]
    assert ids[ids.index('random_episode_next') - 1] == 'random_episode'
    assert settings['random_episode_next'].get('enable') == 'eq(-1,true)'


@pytest.mark.parametrize('lang', LANGUAGES)
def test_random_episode_next_strings_exist_in_every_language(lang):
    present = _po_ids(lang)
    missing = [str(i) for i in range(30456, 30461) if str(i) not in present]
    assert missing == []


PLAYBACK_PY = os.path.join(os.path.dirname(__file__), '..', '..', 'lib', 'playback.py')


def test_dnevery_setting_is_removed(settings):
    assert 'dnevery' not in settings


def test_dnevery_dnotify_has_no_dependent_sibling():
    nodes = [s for s in ET.parse(SETTINGS).getroot().iter('setting')]
    ids = [s.get('id') for s in nodes]
    following = nodes[ids.index('dnotify') + 1]
    assert 'eq(-1' not in (following.get('visible') or '') + (following.get('enable') or '')


def test_dnevery_is_no_longer_read_and_downloads_notify_every_10():
    with open(PLAYBACK_PY, encoding='utf8') as f:
        src = f.read()
    assert 'dnevery' not in src
    assert re.search(r'^\s+every = 10$', src, re.M)
