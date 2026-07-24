import re
from pathlib import Path


def parse_usd_file(filepath):
    with open(filepath) as f:
        text = f.read()
    return _parse_usda(text)


PRIM_RE = re.compile(
    r'^\s*(?P<decl>def|over|class|variantSet)\s+'
    r'(?P<type>\w+)\s+'
    r'"(?P<name>[^"]+)"'
)

ATTR_RE = re.compile(
    r'^\s*(?:(uniform|varying)\s+)?'
    r'(?:[\w\[\]]+\s+)*'
    r'(?P<name>[\w:]+)\s*=\s*'
    r'(?P<value>.+)'
)


def _parse_usda(text):
    lines = text.split('\n')
    meta = _parse_top_metadata(text)

    prims = []
    stack = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue

        if stripped in ('{', '}') or stripped.startswith('(') or stripped == ')':
            continue

        indent = len(line) - len(line.lstrip())

        while stack and stack[-1][0] >= indent:
            stack.pop()

        m = PRIM_RE.match(line)
        if m:
            prim = _make_prim(m)
            if stack:
                stack[-1][1]['children'].append(prim)
            else:
                prims.append(prim)
            stack.append((indent, prim))
            continue

        am = ATTR_RE.match(line)
        if am and stack:
            parent = stack[-1][1]
            attr_name = am.group('name')
            attr_value = am.group('value').rstrip(',').strip()

            trailing = _collect_trailing_metadata(lines, i)
            entry = {'name': attr_name, 'value': attr_value}
            if trailing:
                entry['metadata'] = trailing

            if 'primvars:' in attr_name:
                parent['primvars'].append(entry)
            else:
                parent['attributes'].append(entry)

    return {'metadata': meta, 'prims': prims}


def _make_prim(m):
    return {
        'decl': m.group('decl'), 'type': m.group('type'), 'name': m.group('name'),
        'attributes': [], 'metadata': {}, 'primvars': [], 'children': [],
    }


def _collect_trailing_metadata(lines, idx):
    for j in range(1, 4):
        n = lines[idx + j] if idx + j < len(lines) else ''
        ns = n.strip()
        if ns.startswith('('):
            end = ns.find(')')
            if end >= 0:
                return _parse_kv_block(ns[1:end])
            break
        elif ns.startswith(')') or not ns:
            break
    return {}


def _parse_top_metadata(text):
    m = re.search(r'^\s*\((.*?)\)\s*$', text, re.DOTALL | re.MULTILINE)
    if m:
        return _parse_kv_block(m.group(1))
    return {}


def _parse_kv_block(text):
    kv = {}
    for line in text.split('\n'):
        line = line.strip().rstrip(',')
        if '=' in line:
            k, v = line.split('=', 1)
            kv[k.strip()] = v.strip()
    return kv
