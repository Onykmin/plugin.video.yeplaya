# -*- coding: utf-8 -*-
"""After-update changelog dialog: extract_section (D2, exact-version match)
and maybe_show_changelog orchestration (D1 fresh install, D3 opt-out,
record-before-show failure safety).
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from tests.conftest import get_mock_addon

import pytest
from unittest.mock import patch

from lib import changelog


@pytest.fixture(autouse=True)
def _isolate_mock_addon_settings():
    """Snapshot/restore the session-wide mock addon's settings dict so
    _addon_with()'s addon._settings.clear() never leaks into other test
    modules. Restores in place (.clear() + .update()) rather than
    reassigning, since the root conftest autouse guard and lib.* modules
    hold references to this same dict object."""
    addon = get_mock_addon()
    saved = dict(addon._settings)
    yield
    addon._settings.clear()
    addon._settings.update(saved)


NEWS = """
[B]1.2.2[/B]
- fix: subtitle auto-select now reads real track flags (forced / default / SDH) instead of bare language codes
[B]1.2.1[/B]
- fix: subtitle auto-select no longer picks a "Forced" track when a normal track of the same language exists
[B]1.2.0[/B]
- new: version-picker dialog now lists sources largest-file-first
- fix: resume / watched tracking now actually records
[B]1.0.0[/B]
- rebrand to Ye-Playa
"""


class _StubDialog:
    """Records textviewer() calls."""

    def __init__(self):
        self.calls = []

    def textviewer(self, heading, text):
        self.calls.append((heading, text))


def _install_dialog_stub():
    xbmcgui_mod = sys.modules['xbmcgui']
    stub = _StubDialog()
    return patch.object(xbmcgui_mod, 'Dialog', lambda: stub), stub


# ---------------------------------------------------------------------------
# extract_section (D2 + exact-version matching)
# ---------------------------------------------------------------------------

def test_extract_section_returns_only_current_version_body():
    body = changelog.extract_section(NEWS, '1.2.2')
    assert 'reads real track flags' in body
    # D2: never bleed into older sections
    assert 'largest-file-first' not in body
    assert 'rebrand to Ye-Playa' not in body


def test_extract_section_middle_version():
    body = changelog.extract_section(NEWS, '1.2.1')
    assert 'no longer picks a "Forced" track' in body
    assert 'reads real track flags' not in body
    assert 'largest-file-first' not in body


def test_extract_section_oldest_version():
    body = changelog.extract_section(NEWS, '1.0.0')
    assert 'rebrand to Ye-Playa' in body


def test_extract_section_exact_version_match_not_prefix():
    news = "[B]1.2.10[/B]\n- some future fix\n[B]1.2.1[/B]\n- older fix\n"
    body = changelog.extract_section(news, '1.2.1')
    assert 'older fix' in body
    assert 'future fix' not in body


def test_extract_section_exact_match_1_2_10_still_found():
    """The exact-match guard must not also block legitimately matching the
    longer version string itself."""
    news = "[B]1.2.10[/B]\n- some future fix\n[B]1.2.1[/B]\n- older fix\n"
    body = changelog.extract_section(news, '1.2.10')
    assert 'some future fix' in body
    assert 'older fix' not in body


def test_extract_section_missing_version_returns_empty():
    assert changelog.extract_section(NEWS, '9.9.9') == ''


def test_extract_section_falsy_inputs_return_empty():
    assert changelog.extract_section('', '1.2.2') == ''
    assert changelog.extract_section(None, '1.2.2') == ''
    assert changelog.extract_section(NEWS, '') == ''
    assert changelog.extract_section(NEWS, None) == ''


def test_extract_section_inline_bold_does_not_truncate_body():
    """Inline [B]...[/B] markup inside a body line must not be mistaken for
    the next section header: the header regex only matches leading bold
    that is version-shaped (digits/dots, optional leading 'v'), which
    '[B]bold inline[/B]' is not."""
    news = (
        '[B]1.3.0[/B]\n'
        '- new: [B]bold inline[/B] matters\n'
        '- second line\n'
        '[B]1.2.2[/B]\n'
        '- old\n'
    )
    body = changelog.extract_section(news, '1.3.0')
    assert '- new: [B]bold inline[/B] matters' in body
    assert '- second line' in body
    assert '- old' not in body


def test_extract_section_header_with_trailing_text_is_recognized():
    """The narrowing being fixed: '[B]1.3.0[/B] hotfix' (trailing text after
    the bold) must still be recognized as a section header/boundary."""
    news = (
        '[B]1.3.0[/B] hotfix\n'
        '- fixed a thing\n'
        '[B]1.2.2[/B]\n'
        '- old\n'
    )
    body = changelog.extract_section(news, '1.3.0')
    assert 'fixed a thing' in body
    assert 'old' not in body


def test_extract_section_trailing_text_header_terminates_preceding_section():
    """A '[B]version[/B] trailing text' header must also terminate the
    PRECEDING section's body (used as the next-header boundary)."""
    news = (
        '[B]1.4.0[/B]\n'
        '- first change\n'
        '[B]1.3.0[/B] hotfix\n'
        '- fixed a thing\n'
    )
    body = changelog.extract_section(news, '1.4.0')
    assert 'first change' in body
    assert 'fixed a thing' not in body


def test_extract_section_header_with_v_prefix_is_recognized():
    news = (
        '[B]v1.3.0[/B]\n'
        '- new stuff\n'
        '[B]1.2.2[/B]\n'
        '- old\n'
    )
    body = changelog.extract_section(news, '1.3.0')
    assert 'new stuff' in body
    assert 'old' not in body


def test_extract_section_header_with_leading_whitespace_is_recognized():
    news = (
        '   [B]1.3.0[/B]\n'
        '- new stuff\n'
        '\t[B]1.2.2[/B]\n'
        '- old\n'
    )
    body = changelog.extract_section(news, '1.3.0')
    assert 'new stuff' in body
    assert 'old' not in body


def test_extract_section_non_version_leading_bold_is_not_a_boundary():
    """'[B]Breaking:[/B]' and '[B]Note[/B]' are leading bold but not
    version-shaped, so they must not be mistaken for section headers."""
    news = (
        '[B]1.3.0[/B]\n'
        '[B]Breaking:[/B] do not do X\n'
        '[B]Note[/B] something\n'
        '- more body\n'
        '[B]1.2.2[/B]\n'
        '- old\n'
    )
    body = changelog.extract_section(news, '1.3.0')
    assert '[B]Breaking:[/B] do not do X' in body
    assert '[B]Note[/B] something' in body
    assert '- more body' in body
    assert 'old' not in body


def test_extract_section_real_addon_xml_shape_only_target_section():
    """Regression guard: anchoring must not break real-world multi-section
    parsing shaped like the actual addon.xml <news> block."""
    news = (
        '[B]1.2.2[/B]\n'
        '- fix: subtitle auto-select now reads real track flags\n'
        '[B]1.2.1[/B]\n'
        '- fix: subtitle auto-select no longer picks a "Forced" track\n'
        '[B]1.2.0[/B]\n'
        '- new: version-picker dialog now lists sources largest-file-first\n'
        '- fix: resume / watched tracking now actually records\n'
        '[B]1.0.0[/B]\n'
        '- rebrand to Ye-Playa\n'
    )
    body = changelog.extract_section(news, '1.2.0')
    assert 'largest-file-first' in body
    assert 'resume / watched tracking' in body
    assert 'Forced' not in body
    assert 'rebrand to Ye-Playa' not in body


# ---------------------------------------------------------------------------
# maybe_show_changelog orchestration
# ---------------------------------------------------------------------------

def _addon_with(version, path='/addon/path'):
    """Return (addon, fake_getAddonInfo) with a fresh settings dict.

    fake_getAddonInfo is patched onto the CLASS via patch.object(type(addon), ...),
    so it must accept `self` like a real unbound method.
    """
    addon = get_mock_addon()
    addon._settings.clear()

    def fake_get_info(self, key):
        if key == 'version':
            return version
        if key == 'path':
            return path
        return 'TestAddon'
    return addon, fake_get_info


def test_fires_on_version_change():
    addon, fake_get_info = _addon_with('1.2.2')
    addon.setSetting('changelog_seen_version', '1.2.1')
    patch_dialog, stub = _install_dialog_stub()
    with patch.object(type(addon), 'getAddonInfo', fake_get_info), \
         patch.object(changelog, 'read_news', return_value=NEWS), \
         patch_dialog:
        changelog.maybe_show_changelog()
    assert len(stub.calls) == 1
    heading, text = stub.calls[0]
    assert 'reads real track flags' in text
    assert addon._settings['changelog_seen_version'] == '1.2.2'


def test_silent_on_same_version():
    addon, fake_get_info = _addon_with('1.2.2')
    addon.setSetting('changelog_seen_version', '1.2.2')
    patch_dialog, stub = _install_dialog_stub()
    with patch.object(type(addon), 'getAddonInfo', fake_get_info), \
         patch.object(changelog, 'read_news', return_value=NEWS), \
         patch_dialog:
        changelog.maybe_show_changelog()
    assert stub.calls == []
    assert addon._settings['changelog_seen_version'] == '1.2.2'  # unchanged


def test_fresh_install_silent_d1():
    addon, fake_get_info = _addon_with('1.2.2')
    # no changelog_seen_version recorded at all -> seen == ''
    patch_dialog, stub = _install_dialog_stub()
    with patch.object(type(addon), 'getAddonInfo', fake_get_info), \
         patch.object(changelog, 'read_news', return_value=NEWS), \
         patch_dialog:
        changelog.maybe_show_changelog()
    assert stub.calls == []
    assert addon._settings['changelog_seen_version'] == '1.2.2'


def test_opt_out_silent_but_recorded_d3():
    addon, fake_get_info = _addon_with('1.2.2')
    addon.setSetting('changelog_seen_version', '1.2.1')
    addon.setSetting('show_changelog', 'false')
    patch_dialog, stub = _install_dialog_stub()
    with patch.object(type(addon), 'getAddonInfo', fake_get_info), \
         patch.object(changelog, 'read_news', return_value=NEWS), \
         patch_dialog:
        changelog.maybe_show_changelog()
    assert stub.calls == []
    assert addon._settings['changelog_seen_version'] == '1.2.2'


def test_read_news_failure_does_not_raise():
    addon, fake_get_info = _addon_with('1.2.2')
    addon.setSetting('changelog_seen_version', '1.2.1')
    patch_dialog, stub = _install_dialog_stub()

    def _boom():
        raise RuntimeError('boom')

    with patch.object(type(addon), 'getAddonInfo', fake_get_info), \
         patch.object(changelog, 'read_news', side_effect=_boom), \
         patch_dialog:
        changelog.maybe_show_changelog()  # must not raise
    assert stub.calls == []
    # record-before-show: version still recorded despite downstream failure
    assert addon._settings['changelog_seen_version'] == '1.2.2'


def test_missing_section_in_news_no_dialog():
    addon, fake_get_info = _addon_with('1.2.2')
    addon.setSetting('changelog_seen_version', '1.2.1')
    patch_dialog, stub = _install_dialog_stub()
    with patch.object(type(addon), 'getAddonInfo', fake_get_info), \
         patch.object(changelog, 'read_news', return_value=''), \
         patch_dialog:
        changelog.maybe_show_changelog()
    assert stub.calls == []
    assert addon._settings['changelog_seen_version'] == '1.2.2'


def test_record_before_show_survives_textviewer_raising():
    """Failure-safety guarantee: version is recorded even if the dialog
    itself raises, so a crash never causes a repeat prompt."""
    addon, fake_get_info = _addon_with('1.2.2')
    addon.setSetting('changelog_seen_version', '1.2.1')

    class _RaisingDialog:
        def textviewer(self, heading, text):
            raise RuntimeError('dialog exploded')

    xbmcgui_mod = sys.modules['xbmcgui']
    with patch.object(type(addon), 'getAddonInfo', fake_get_info), \
         patch.object(changelog, 'read_news', return_value=NEWS), \
         patch.object(xbmcgui_mod, 'Dialog', lambda: _RaisingDialog()):
        changelog.maybe_show_changelog()  # must not raise (outer try/except)
    assert addon._settings['changelog_seen_version'] == '1.2.2'


def test_no_version_returns_early():
    addon, fake_get_info = _addon_with('')
    patch_dialog, stub = _install_dialog_stub()
    with patch.object(type(addon), 'getAddonInfo', fake_get_info), \
         patch_dialog:
        changelog.maybe_show_changelog()
    assert stub.calls == []
    assert 'changelog_seen_version' not in addon._settings


def test_heading_never_blank_when_localized_string_empty():
    """resources/language/.../strings.po ships getLocalizedString(30445) as
    an empty msgstr in practice. ''.format(current) is still '' (no raise),
    so the except-based fallback alone can never catch it; the heading must
    still fall back to the addon name."""
    addon, fake_get_info = _addon_with('1.2.2')
    addon.setSetting('changelog_seen_version', '1.2.1')
    patch_dialog, stub = _install_dialog_stub()
    with patch.object(type(addon), 'getAddonInfo', fake_get_info), \
         patch.object(changelog, 'read_news', return_value=NEWS), \
         patch.object(type(addon), 'getLocalizedString', lambda self, sid: ''), \
         patch_dialog:
        changelog.maybe_show_changelog()
    assert len(stub.calls) == 1
    heading, _text = stub.calls[0]
    assert heading  # never blank
    assert heading == 'TestAddon'  # falls back to addon name


def test_heading_falls_back_on_unformattable_placeholder():
    """A translator's stray '{bogus}' placeholder raises KeyError on
    .format(current); the existing except-fallback must still produce a
    non-empty heading without propagating the exception."""
    addon, fake_get_info = _addon_with('1.2.2')
    addon.setSetting('changelog_seen_version', '1.2.1')
    patch_dialog, stub = _install_dialog_stub()
    with patch.object(type(addon), 'getAddonInfo', fake_get_info), \
         patch.object(changelog, 'read_news', return_value=NEWS), \
         patch.object(type(addon), 'getLocalizedString',
                      lambda self, sid: 'What is new in {bogus}'), \
         patch_dialog:
        changelog.maybe_show_changelog()  # must not raise
    assert len(stub.calls) == 1
    heading, _text = stub.calls[0]
    assert heading  # never blank
    assert heading == 'TestAddon'
