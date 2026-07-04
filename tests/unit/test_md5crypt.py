# -*- coding: utf-8 -*-
"""Known-answer tests for md5crypt ($1$) against the reference algorithm.

Reference vectors produced by `openssl passwd -1 -salt abcdefgh`. The addon
feeds md5crypt UTF-8-encoded bytes (api.py: password.encode('utf-8')), so the
non-ASCII cases below guard the byte-handling in the 'weird xform' loop — a
regression there silently breaks Webshare login for accented passwords.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from md5crypt import md5crypt

_SALT = b'abcdefgh'

# (utf-8 password, expected $1$ hash) — all verified with `openssl passwd -1`.
_VECTORS = [
    ('aheslo', '$1$abcdefgh$xXvcE.GsrFc6AQ2U9RRCU1'),
    ('test123', '$1$abcdefgh$FuRpVTqE/Onxax.jDI2aR/'),
    # Non-ASCII: byte-lengths 2 and 4 exercise the else-branch that appends the
    # first byte of pw; the old chr(pw[0]).encode() emitted 2 bytes and failed.
    ('á', '$1$abcdefgh$5ukipRdoBcJu8PYArV8Y0.'),
    ('áá', '$1$abcdefgh$XI3.uP32quxoh0UkorBbz1'),
    ('ěš', '$1$abcdefgh$e.oikuJu.v3zX1UFkraWr.'),
    ('áheslo', '$1$abcdefgh$Jc.F9PATTGX3rGDrRrrAb/'),
]


def test_md5crypt_known_vectors():
    for pw, expected in _VECTORS:
        got = md5crypt(pw.encode('utf-8'), _SALT)
        assert got == expected, "md5crypt({!r}) = {} != {}".format(pw, got, expected)
