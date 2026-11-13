#!/usr/bin/env python3
"""Add the user-content guard to the upstream engine.js.

Why: the engine translates every text node it is allowed to see. Conversation
names and project names are USER content, so a session named "debug" gets turned
into "调试" (the dictionary has `Debug -> 调试`, and matching is case-insensitive).
That is wrong: the user typed that name, and it should stay exactly as typed.

Fix: make judgeElement() skip the containers that render user-named content:
  - data-testid="breadcrumb-segment"     top breadcrumb (project / conversation)
  - data-testid="conversation-row-sidebar"  conversation list rows
  - data-testid="project-header"         project names in the sidebar

The change is idempotent (marked with USER-CONTENT-GUARD) and is re-applied by
install.ps1 whenever the upstream tool is upgraded (an upgrade replaces engine.js).

Usage:  python patch_engine.py "<upstream tool dir>"
"""
import os
import sys

MARKER = 'USER-CONTENT-GUARD'
TESTID_LIST = "'breadcrumb-segment' || ut === 'conversation-row-sidebar' || ut === 'project-header'"

ANCHOR_0 = "        if (element.hasAttribute && element.hasAttribute('data-ag-localization-skip')) return true;"
ANCHOR_ANC = "                if (cur.getAttribute('data-ag-localization-skip')) return true;"

BLOCK_0 = """
        // %s: 用户自己命名的内容绝不翻译。
        // 会话名 / 项目名是用户输入，翻了会让人以为名字被改掉了
        //（实测 2026-11-13：名为 "debug" 的会话被翻成"调试"，顶部面包屑和侧边栏都变）。
        if (element.getAttribute) {
            var ut = element.getAttribute('data-testid');
            if (ut === %s) return true;
        }""" % (MARKER, TESTID_LIST)

BLOCK_ANC = """
                // %s: 祖先链上的用户内容容器（会话行 / 项目标题 / 面包屑段）
                var ut2 = cur.getAttribute('data-testid');
                if (ut2 === %s) return true;""" % (MARKER, TESTID_LIST)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    tool_dir = sys.argv[1]
    path = os.path.join(tool_dir, 'engine.js')
    if not os.path.isfile(path):
        print('engine.js not found: %s' % path)
        return 1

    with open(path, 'r', encoding='utf-8') as f:
        src = f.read()

    if MARKER in src:
        print('already patched (USER-CONTENT-GUARD present)')
        return 0

    for anchor in (ANCHOR_0, ANCHOR_ANC):
        if anchor not in src:
            print('anchor not found, upstream engine.js layout changed:')
            print('  ' + anchor.strip()[:90])
            return 1

    src = src.replace(ANCHOR_0, ANCHOR_0 + BLOCK_0, 1)
    src = src.replace(ANCHOR_ANC, ANCHOR_ANC + BLOCK_ANC, 1)

    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(src)

    print('patched: %s' % path)
    print('  skipped containers: breadcrumb-segment / conversation-row-sidebar / project-header')
    return 0


if __name__ == '__main__':
    sys.exit(main())
