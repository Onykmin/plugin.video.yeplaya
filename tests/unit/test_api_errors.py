# -*- coding: utf-8 -*-
"""lib.api: input validation, XML handling, token revalidation, error paths.

The Webshare HTTP layer is replaced by a scripted fake session; everything
above it (api, revalidate, login, getlink, getinfo) is real code.
"""
import importlib

import pytest
import requests

from tests.conftest import MockAddon


class FakeResponse:
    def __init__(self, body, status=200):
        self.content = body.encode() if isinstance(body, str) else body
        self.status = status

    def raise_for_status(self):
        if self.status >= 400:
            raise requests.exceptions.HTTPError('%d' % self.status)


class FakeSession:
    """Answers POST /api/<fn>/ from a dict of fn -> response | [responses] | exception."""

    def __init__(self, script):
        self.script = {k: (list(v) if isinstance(v, list) else [v]) for k, v in script.items()}
        self.calls = []

    def post(self, url, data=None, timeout=None):
        fn = url.rstrip('/').rsplit('/', 1)[-1]
        self.calls.append((fn, data))
        queue = self.script[fn]
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        return item


def ok(**fields):
    inner = ''.join('<%s>%s</%s>' % (k, v, k) for k, v in fields.items())
    return FakeResponse('<response><status>OK</status>%s</response>' % inner)


ERR = FakeResponse('<response><status>ERROR</status></response>')


@pytest.fixture
def env(monkeypatch):
    api = importlib.import_module('lib.api')
    utils = importlib.import_module('lib.utils')
    addon = MockAddon()
    notices = []
    monkeypatch.setattr(api, '_addon', addon)
    monkeypatch.setattr(utils, 'popinfo', lambda msg, **kw: notices.append(msg))

    def use(script):
        session = FakeSession(script)
        monkeypatch.setattr(api, '_session', session)
        return session

    class Env:
        pass

    e = Env()
    e.api, e.addon, e.notices, e.use = api, addon, notices, use
    return e


@pytest.mark.parametrize('ident', ['valid_ident-123', 'a' * 100, 'AbC'])
def test_validate_ident_accepts_safe_values(env, ident):
    assert env.api.validate_ident(ident) is True


@pytest.mark.parametrize('ident', [
    None, '', 0, 123, b'abc', 'abc!@#', '../etc/passwd', 'id;DROP TABLE',
    '<script>alert(1)</script>', 'with space', 'a' * 101,
])
def test_validate_ident_rejects_unsafe_values(env, ident):
    assert env.api.validate_ident(ident) is False


@pytest.mark.parametrize('content', [b'<not>valid<xml', b'', None, b'x' * (10 * 1024 * 1024 + 1)])
def test_parse_xml_returns_none_for_bad_or_oversized_input(env, content):
    assert env.api.parse_xml(content) is None


@pytest.mark.parametrize('body, expected', [
    ('<response><status>OK</status></response>', True),
    ('<response><status>ERROR</status></response>', False),
    ('<response><data>x</data></response>', False),
])
def test_is_ok(env, body, expected):
    assert env.api.is_ok(env.api.parse_xml(body)) is expected


def test_is_ok_none(env):
    assert env.api.is_ok(None) is False


@pytest.mark.parametrize('exc', [
    requests.exceptions.Timeout(), requests.exceptions.ConnectionError('down')])
def test_api_returns_none_on_network_failure(env, exc):
    env.use({'ping': exc})
    assert env.api.api('ping', {}) is None


def test_api_returns_none_on_http_error(env):
    env.use({'ping': FakeResponse('', status=503)})
    assert env.api.api('ping', {}) is None


def test_revalidate_returns_existing_valid_token(env):
    env.addon.setSetting('token', 'good')
    session = env.use({'user_data': ok(vip='1')})
    assert env.api.revalidate() == 'good'
    assert [fn for fn, _ in session.calls] == ['user_data']
    assert env.notices == []


def test_revalidate_warns_when_account_is_not_vip(env):
    env.addon.setSetting('token', 'good')
    env.use({'user_data': ok(vip='0')})
    assert env.api.revalidate() == 'good'
    assert env.notices == ['String_30103']


def test_revalidate_rejected_token_is_cleared_then_relogin_is_attempted(env):
    env.addon.setSetting('token', 'stale')
    session = env.use({'user_data': ERR})
    assert env.api.revalidate() is None  # no stored credentials -> login prompt
    assert env.addon.getSetting('token') == ''
    assert [fn for fn, _ in session.calls] == ['user_data']
    assert env.notices == ['String_30101']


def test_revalidate_recovers_from_stale_token_by_logging_in_again(env):
    env.addon.setSetting('token', 'stale')
    env.addon.setSetting('wsuser', 'bob')
    env.addon.setSetting('wspass', 'secret')
    env.use({
        'user_data': [ERR, ok(vip='1')],
        'salt': ok(salt='abc123'),
        'login': ok(token='FRESH'),
    })
    assert env.api.revalidate() == 'FRESH'


def test_revalidate_network_failure_returns_none_without_clearing_token(env):
    env.addon.setSetting('token', 'good')
    env.use({'user_data': requests.exceptions.ConnectionError('down')})
    assert env.api.revalidate() is None
    assert env.addon.getSetting('token') == 'good'


def test_revalidate_logs_in_when_no_token(env):
    env.addon.setSetting('wsuser', 'bob')
    env.addon.setSetting('wspass', 'secret')
    session = env.use({
        'salt': ok(salt='abc123'),
        'login': ok(token='NEWTOKEN'),
        'user_data': ok(vip='1'),
    })
    assert env.api.revalidate() == 'NEWTOKEN'
    login_data = dict(session.calls)['login']
    assert login_data['username_or_email'] == 'bob'
    assert 'secret' not in login_data.values()  # only the hashed password goes out


def test_login_without_credentials_prompts_settings_and_makes_no_request(env):
    session = env.use({})
    assert env.api.login() is None
    assert session.calls == []
    assert env.notices == ['String_30101']


def test_login_wrong_password_notifies_and_stores_no_token(env):
    env.addon.setSetting('wsuser', 'bob')
    env.addon.setSetting('wspass', 'wrong')
    env.use({'salt': ok(salt='abc123'), 'login': ERR})
    assert env.api.login() is None
    assert env.addon.getSetting('token') == ''
    assert env.notices == ['String_30102']


def test_getlink_returns_link_and_persists_device_uuid(env):
    session = env.use({'file_link': ok(link='https://dl.example/f')})
    assert env.api.getlink('abc123', 'tok') == 'https://dl.example/f'
    uuid_sent = session.calls[0][1]['device_uuid']
    assert uuid_sent and env.addon.getSetting('duuid') == uuid_sent
    env.api.getlink('abc123', 'tok')
    assert session.calls[1][1]['device_uuid'] == uuid_sent


def test_getlink_rejects_bad_ident_without_network(env):
    session = env.use({})
    assert env.api.getlink('../x', 'tok') is None
    assert session.calls == []


@pytest.mark.parametrize('reply', [ERR, requests.exceptions.Timeout()])
def test_getlink_failure_notifies_user(env, reply):
    env.use({'file_link': reply})
    assert env.api.getlink('abc123', 'tok') is None
    assert env.notices == ['String_30107']


def test_getinfo_retries_as_maybe_removed_when_first_lookup_fails(env):
    session = env.use({'file_info': [ERR, ok(name='f.mkv')]})
    xml = env.api.getinfo('abc123', 'tok')
    assert xml.find('name').text == 'f.mkv'
    assert 'maybe_removed' not in session.calls[0][1]
    assert session.calls[1][1]['maybe_removed'] == 'true'


def test_getinfo_gives_up_when_both_lookups_fail(env):
    env.use({'file_info': ERR})
    assert env.api.getinfo('abc123', 'tok') is None
    assert env.notices == ['String_30107']
