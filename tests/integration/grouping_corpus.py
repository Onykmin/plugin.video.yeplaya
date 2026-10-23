# -*- coding: utf-8 -*-
"""Maintenance tool (not collected by pytest): snapshot/diff grouping over the corpus.

    python3 tests/integration/grouping_corpus.py snapshot OUT_DIR [--order ORDER]
    python3 tests/integration/grouping_corpus.py diff OLD.json NEW.json

snapshot: runs the production path (fetch_and_group_series, network mocked, same
replay as the baseline test) for every query in baseline_results.json and writes
OUT_DIR/snapshot_<order>.json (OUT_DIR must be outside the repo; ':' becomes '_'), deterministic: per group key, display name, scalar metadata, seasons/episodes
and the ORDERED versions (ident, name, size, quality score).
ORDER = forward (default, recorded API order) | reversed | shuffle:SEED. The file list is
permuted before grouping; diffing a forward snapshot against a permuted one shows what
depends on input order.
diff: per query, prints groups added/removed, key/name/metadata changes, files moved
between groups, version-order changes; ends with a summary line. Run from repo root.
"""

import json
import random
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import tests.conftest  # noqa: E402,F401  (installs the Kodi mocks lib/ needs)
from lib.grouping import fetch_and_group_series  # noqa: E402
from lib.parsing import parse_quality_metadata  # noqa: E402
from tests.integration.test_baseline_regression import BASELINE, fixture_path  # noqa: E402

_STRUCT = {'seasons', 'versions', 'display_name_candidates'}


def run_pipeline(query, order='forward'):
    """Same replay as the baseline test, with the recorded file list reordered."""
    content = fixture_path(query).read_bytes()
    if order != 'forward':
        root = ET.fromstring(content)
        files = root.findall('file')
        for f in files:
            root.remove(f)
        if order == 'reversed':
            files.reverse()
        elif order.startswith('shuffle:'):
            random.Random(order.split(':', 1)[1]).shuffle(files)
        else:
            raise SystemExit(f'unknown order {order!r}')
        root.extend(files)
        content = ET.tostring(root)
    with patch('lib.grouping.api', side_effect=[MagicMock(content=content), None]):
        return fetch_and_group_series('token', query, 'video', '')


def _version(v):
    return {'ident': v.get('ident'), 'name': v.get('name'),
            'size': v.get('size'),
            'score': parse_quality_metadata(v.get('name') or '').get('quality_score')}


def _meta(data):
    return {k: v for k, v in sorted(data.items())
            if k not in _STRUCT and isinstance(v, (str, int, float, bool, type(None), list))}


def snapshot_one(query, order='forward'):
    grouped = run_pipeline(query, order)
    if grouped is None:
        return {'series': {}, 'movies': {}, 'non_series': []}
    series = {}
    for key, data in grouped['series'].items():
        series[key] = {
            'meta': _meta(data),
            'seasons': {str(s): {str(e): [_version(v) for v in vs] for e, vs in sorted(eps.items())}
                        for s, eps in sorted(data['seasons'].items())},
        }
    movies = {key: {'meta': _meta(data), 'versions': [_version(v) for v in data['versions']]}
              for key, data in grouped.get('movies', {}).items()}
    non_series = sorted(f.get('ident') or '' for f in grouped['non_series'])
    return {'series': series, 'movies': movies, 'non_series': non_series}


def cmd_snapshot(out_dir, order='forward'):
    out_dir = Path(out_dir).resolve()
    if out_dir == ROOT or ROOT in out_dir.parents:
        raise SystemExit(f'refusing to write snapshots inside the repo: {out_dir}')
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / ('snapshot_%s.json' % order.replace(':', '_'))
    snap = {q: snapshot_one(q, order) for q in sorted(BASELINE)}
    out.write_text(json.dumps(snap, indent=1, ensure_ascii=False, sort_keys=True),
                   encoding='utf-8')
    print(f'wrote {out} ({len(snap)} queries, order={order})')


def _file_map(qsnap):
    """ident -> (kind, key) for every grouped file; non-series under ('loose', '')."""
    m = {}
    for key, g in qsnap['series'].items():
        for eps in g['seasons'].values():
            for vs in eps.values():
                for v in vs:
                    m[v['ident']] = ('series', key)
    for key, g in qsnap['movies'].items():
        for v in g['versions']:
            m[v['ident']] = ('movie', key)
    for ident in qsnap['non_series']:
        m[ident] = ('loose', '')
    return m


def _names(qsnap):
    names = {}
    for g in qsnap['series'].values():
        for eps in g['seasons'].values():
            for vs in eps.values():
                for v in vs:
                    names[v['ident']] = v['name']
    for g in qsnap['movies'].values():
        for v in g['versions']:
            names[v['ident']] = v['name']
    return names


def _orders(qsnap):
    o = {}
    for key, g in qsnap['series'].items():
        for s, eps in g['seasons'].items():
            for e, vs in eps.items():
                o[('series', key, s, e)] = [(v['ident'], v['score'], v['size']) for v in vs]
    for key, g in qsnap['movies'].items():
        o[('movie', key)] = [(v['ident'], v['score'], v['size']) for v in g['versions']]
    return o


def _align_idents(a, b):
    """Rename idents in b that exist only there to the ident a holds for the same
    (name, size): inline dedup keeps whichever same-name copy came first, so a permuted
    input legitimately swaps idents. Returns the number of swaps (not a grouping change)."""
    fa, fb = _file_map(a), _file_map(b)
    only_a = {}
    for ident in set(fa) - set(fb):
        only_a.setdefault(_ident_sig(a, ident), []).append(ident)
    sigs_b = {i: _ident_sig(b, i) for i in set(fb) - set(fa)}
    rename = {}
    for ident in sorted(sigs_b):
        if only_a.get(sigs_b[ident]):
            rename[ident] = only_a[sigs_b[ident]].pop()
    for g in b['series'].values():
        for eps in g['seasons'].values():
            for vs in eps.values():
                for v in vs:
                    v['ident'] = rename.get(v['ident'], v['ident'])
    for g in b['movies'].values():
        for v in g['versions']:
            v['ident'] = rename.get(v['ident'], v['ident'])
    b['non_series'] = sorted(rename.get(i, i) for i in b['non_series'])
    return len(rename)


def _ident_sig(qsnap, ident):
    for g in qsnap['series'].values():
        for eps in g['seasons'].values():
            for vs in eps.values():
                for v in vs:
                    if v['ident'] == ident:
                        return (v['name'], v['size'])
    for g in qsnap['movies'].values():
        for v in g['versions']:
            if v['ident'] == ident:
                return (v['name'], v['size'])
    return (ident, None)


def diff_query(q, a, b, counts):
    counts['ident_swapped'] += _align_idents(a, b)
    lines = []
    for kind, bucket in (('series', 'series'), ('movie', 'movies')):
        for key in sorted(set(a[bucket]) - set(b[bucket])):
            lines.append(f'  - {kind} removed: {key!r} ({_size(a, kind, key)} files)')
            counts['removed'] += 1
        for key in sorted(set(b[bucket]) - set(a[bucket])):
            lines.append(f'  + {kind} added: {key!r} ({_size(b, kind, key)} files)')
            counts['added'] += 1
        for key in sorted(set(a[bucket]) & set(b[bucket])):
            ma, mb = a[bucket][key]['meta'], b[bucket][key]['meta']
            for f in sorted(set(ma) | set(mb)):
                if ma.get(f) != mb.get(f):
                    lines.append(f'  ~ {kind} {key!r} {f}: {ma.get(f)!r} -> {mb.get(f)!r}')
                    counts['meta'] += 1
    fa, fb, names = _file_map(a), _file_map(b), {**_names(a), **_names(b)}
    moves = {}
    for ident in sorted(set(fa) & set(fb)):
        if fa[ident] != fb[ident]:
            moves.setdefault((fa[ident], fb[ident]), []).append(ident)
    for (src, dst), idents in sorted(moves.items()):
        lines.append(f'  > moved {len(idents)} file(s) {src[0]}:{src[1]!r} -> {dst[0]}:{dst[1]!r}')
        for ident in idents[:5]:
            lines.append(f'      {names.get(ident, ident)}')
        if len(idents) > 5:
            lines.append(f'      ... +{len(idents) - 5} more')
        counts['moved_files'] += len(idents)
    for ident in sorted(set(fa) ^ set(fb)):
        lines.append(f'  ! file {"dropped" if ident in fa else "appeared"}: {names.get(ident, ident)}')
        counts['dropped_appeared'] += 1
    oa, ob = _orders(a), _orders(b)
    for k in sorted(set(oa) & set(ob), key=str):
        da, db = {t[0]: t for t in oa[k]}, {t[0]: t for t in ob[k]}
        if set(da) != set(db):
            continue  # membership change: reported as moved/dropped above
        for ident in sorted(da):
            if da[ident][1] != db[ident][1]:
                lines.append(f'  ~ rescored {k} {names.get(ident, ident)}: {da[ident][1]} -> {db[ident][1]}')
                counts['rescored'] += 1
        if [t[0] for t in oa[k]] != [t[0] for t in ob[k]]:
            # same (score, size) sequence = a tie between equal-ranked versions
            tie = [t[1:] for t in oa[k]] == [t[1:] for t in ob[k]]
            lines.append(f'  # version order {"tie" if tie else "changed"} {k}')
            counts['order_ties' if tie else 'order'] += 1
    if lines:
        counts['queries'] += 1
        print(f'[{q}]')
        print('\n'.join(lines))


def _size(snap, kind, key):
    if kind == 'movie':
        return len(snap['movies'][key]['versions'])
    return sum(len(vs) for eps in snap['series'][key]['seasons'].values() for vs in eps.values())


def cmd_diff(old, new):
    a = json.loads(Path(old).read_text(encoding='utf-8'))
    b = json.loads(Path(new).read_text(encoding='utf-8'))
    counts = dict.fromkeys(('queries', 'added', 'removed', 'meta', 'moved_files',
                            'dropped_appeared', 'rescored', 'order', 'order_ties', 'ident_swapped'), 0)
    for q in sorted(set(a) | set(b)):
        if q not in a or q not in b:
            print(f'[{q}] only in {"new" if q in b else "old"}')
            counts['queries'] += 1
            continue
        diff_query(q, a[q], b[q], counts)
    print('SUMMARY: ' + ' '.join(f'{k}={v}' for k, v in counts.items()) + f' of {len(b)} queries')


def main(argv):
    if len(argv) == 2 and argv[0] == 'snapshot':
        cmd_snapshot(argv[1])
    elif len(argv) == 4 and argv[0] == 'snapshot' and argv[2] == '--order':
        cmd_snapshot(argv[1], argv[3])
    elif len(argv) == 3 and argv[0] == 'diff':
        cmd_diff(argv[1], argv[2])
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
