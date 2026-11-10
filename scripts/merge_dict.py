#!/usr/bin/env python3
"""Merge the extra dictionary entries into the upstream localization tool's zh_data.json.

Case-sensitive (like the JS engine), idempotent (running it twice adds nothing).

Usage:  python merge_dict.py <tool_dir> <patch_json>
"""
import json
import os
import shutil
import sys


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    tool_dir, patch_file = sys.argv[1], sys.argv[2]
    data_file = os.path.join(tool_dir, 'zh_data.json')
    if not os.path.isfile(data_file):
        print('zh_data.json not found: %s' % data_file)
        return 1
    if not os.path.isfile(patch_file):
        print('patch file not found: %s' % patch_file)
        return 1

    with open(data_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    with open(patch_file, 'r', encoding='utf-8') as f:
        patch = json.load(f)

    backup = data_file + '.bak-install'
    if not os.path.exists(backup):
        shutil.copyfile(data_file, backup)
        print('backup   : %s' % backup)

    added = 0
    for field in ('exact', 'prefix'):
        src = patch.get(field) or {}
        dst = data.setdefault(field, {})
        for k, v in src.items():
            if k not in dst:
                dst[k] = v
                added += 1

    have = {r.get('pattern') for r in (data.get('regex') or [])}
    for r in patch.get('regex') or []:
        if r.get('pattern') not in have:
            data.setdefault('regex', []).append(r)
            have.add(r.get('pattern'))
            added += 1

    data['version'] = str(data.get('version', '')).split('+local')[0] + '+local'
    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    print('added    : %d entries' % added)
    print('total    : exact=%d prefix=%d regex=%d' % (
        len(data.get('exact') or {}), len(data.get('prefix') or {}), len(data.get('regex') or [])))
    return 0


if __name__ == '__main__':
    sys.exit(main())
