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


# --- categories (B2) --------------------------------------------------------

EXPECTED_CATEGORIES = [
    ('30030', ['wsuser', 'wspass', 'token', 'duuid']),
    ('30461', ['scategory', 'ssort', 'slimit', 'default_view', 'group_movies',
               'filter_irrelevant', 'resultsize', 'customformat', 'labelformat', 'shistory']),
    ('30462', ['audio_lang', 'audio_lang2', 'sub_lang', 'sub_lang2', 'sub_auto',
               'track_resume', 'track_watched']),
    ('30463', ['random_episode', 'random_episode_next', 'random_movie']),
    ('30040', ['dfolder', 'dnormalize', 'dnotify']),
    ('30464', ['experimental', 'show_changelog', 'changelog_seen_version']),
]

# Every id in settings.xml before the split (30 ids incl. dnevery, minus the
# later-added random_episode_next), pinned so an accidental rename or drop shows.
BASE_IDS = {
    'wsuser', 'wspass', 'token', 'duuid', 'scategory', 'ssort', 'slimit', 'default_view',
    'group_movies', 'filter_irrelevant', 'resultsize', 'customformat', 'labelformat',
    'shistory', 'audio_lang', 'audio_lang2', 'sub_lang', 'sub_lang2', 'sub_auto',
    'track_resume', 'track_watched', 'random_episode', 'random_movie', 'dfolder',
    'dnormalize', 'dnotify', 'dnevery', 'experimental', 'show_changelog',
    'changelog_seen_version',
}

# sha256 of every setting's (id, type, label, values, lvalues, default, option,
# visible, enable), sorted by id, taken before the split with dnevery already gone.
SETTINGS_FINGERPRINT = '1c613eb048a2e448b8b5877dcaab5d9850381301cfb40b42c78354c3d7c571ef'


def _categories():
    return ET.parse(SETTINGS).getroot().findall('category')


def test_categories_are_six_in_the_planned_order():
    assert [c.get('label') for c in _categories()] == [label for label, _ in EXPECTED_CATEGORIES]


def test_categories_hold_exactly_the_planned_ids_in_order():
    got = [[s.get('id') for s in c.iter('setting') if s.get('id')] for c in _categories()]
    assert got == [ids for _, ids in EXPECTED_CATEGORIES]


def test_categories_have_no_duplicate_ids_and_no_separator_rows():
    settings_ = list(ET.parse(SETTINGS).getroot().iter('setting'))
    ids = [s.get('id') for s in settings_ if s.get('id')]
    assert len(ids) == len(set(ids))
    assert [s for s in settings_ if s.get('type') in ('lsep', 'sep')] == []


def test_categories_id_set_is_base_minus_dnevery_plus_random_episode_next():
    ids = {s.get('id') for s in ET.parse(SETTINGS).getroot().iter('setting') if s.get('id')}
    assert ids == (BASE_IDS - {'dnevery'}) | {'random_episode_next'}
    assert len(ids) == 30


def test_categories_keep_option_lists_defaults_and_dependencies_unchanged():
    import hashlib
    import json
    rows = sorted([s.get('id')] + [s.get(a) for a in (
        'type', 'label', 'values', 'lvalues', 'default', 'option', 'visible', 'enable')]
        for s in ET.parse(SETTINGS).getroot().iter('setting') if s.get('id'))
    assert hashlib.sha256(json.dumps(rows).encode()).hexdigest() == SETTINGS_FINGERPRINT


def test_categories_keep_dependent_pairs_adjacent_inside_one_category():
    for cat in _categories():
        ids = [s.get('id') for s in cat.iter('setting')]
        for first, second in (('customformat', 'labelformat'),
                              ('random_episode', 'random_episode_next')):
            if second in ids:
                assert ids[ids.index(second) - 1] == first


def _used_label_ids():
    root = ET.parse(SETTINGS).getroot()
    used = set()
    for el in root.iter():
        if el.tag not in ('category', 'setting'):
            continue
        for attr in ('label', 'lvalues'):
            used.update(re.findall(r'\d+', el.get(attr) or ''))
    return used


@pytest.mark.parametrize('lang', LANGUAGES)
def test_strings_every_settings_label_and_category_id_exists_in_every_language(lang):
    missing = sorted(_used_label_ids() - _po_ids(lang))
    assert missing == []
    assert {'30461', '30462', '30463', '30464'} <= _po_ids(lang)
