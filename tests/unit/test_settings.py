# -*- coding: utf-8 -*-
"""resources/settings.xml invariants the code relies on."""
import os
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
