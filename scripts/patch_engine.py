#!/usr/bin/env python3
"""Apply local behaviour patches to the upstream engine.js.

Why this exists: the upstream translator skips whole containers to protect user
content (message bubbles, code, the input box). Two gaps needed fixing, and
both are behaviour patches rather than dictionary entries:

1. USER-CONTENT-GUARD - conversation titles / project names are user content
   and must never be translated. Upstream has no skip rule for them, and the
   guard containers are identified by data-testid:
       breadcrumb-segment        top breadcrumb (project / conversation)
       conversation-row-sidebar  conversation rows in the sidebar
       project-header            project names in the sidebar

2. USER-REL-TIME - the message bubble (data-testid="user-input-step") is
   skipped wholesale, which also skips the relative timestamp next to the
   user's own message ("2h ago"). The agent side of the screen shows a
   translated timestamp, so the same screen ends up half Chinese / half
   English. Only the timestamp is let through - the text the user typed is
   still skipped.

The patch is idempotent per rule: each rule is checked for its own marker, so
adding a rule later does not require undoing the earlier ones. Re-run this
after every upstream tool upgrade (install.ps1 does it automatically).

Usage:  python patch_engine.py "<upstream tool dir>"
"""
import os
import sys

MARKER_CONTENT = 'USER-CONTENT-GUARD'
MARKER_TIME = 'USER-REL-TIME'

# ---- rule 1: user-named content must not be translated -----------------------
R1_ANCHOR = "        if (element.hasAttribute && element.hasAttribute('data-ag-localization-skip')) return true;"
R1_ANCHOR_ANC = "                if (cur.getAttribute('data-ag-localization-skip')) return true;"
# NOTE: every comparison must be against the variable as well
# ('x' || 'y' is a non-empty string -> always true -> every element with a
#  data-testid would be skipped, i.e. most of the UI would stop translating).
R1_TESTIDS = "%(v)s === 'breadcrumb-segment' || %(v)s === 'conversation-row-sidebar' || %(v)s === 'project-header'"
R1_BLOCK_0 = """
        // %s: 用户自己命名的内容绝不翻译（会话名 / 项目名）。
        // 名为 "debug" 的会话被翻成"调试"、项目名被翻掉，都会让人以为名字被改了。
        if (element.getAttribute) {
            var ug = element.getAttribute('data-testid');
            if (%s) return true;
        }""" % (MARKER_CONTENT, R1_TESTIDS % {'v': 'ug'})
R1_BLOCK_ANC = """
                // %s: 祖先链上的用户命名容器（会话行 / 项目标题 / 面包屑段）
                var ug2 = cur.getAttribute('data-testid');
                if (%s) return true;""" % (MARKER_CONTENT, R1_TESTIDS % {'v': 'ug2'})

# ---- rule 2: relative timestamps inside the user's own bubble ---------------
R2_ANCHOR = "                if (cur.getAttribute('data-testid') === 'user-input-step') return true;"
R2_BLOCK = """
                // %s: 用户消息气泡里的「相对时间戳」不是用户输入，要照译。
                // 气泡整体仍然跳过（用户自己打的字绝不翻），只放行 "2h ago" 这类时间。
                // 否则 agent 那边的时间是中文、用户消息这边是英文，同屏不一致。
                if (cur.getAttribute('data-testid') === 'user-input-step' && !isRelTime(element)) return true;""" % MARKER_TIME
R2_HELPER_ANCHOR = "    function judgeElement(element) {"
R2_HELPER = """    // 相对时间戳（"2h ago" / "36m ago" / "3d ago"）——用户消息气泡旁也有，
    // 需要单独识别出来放行翻译，否则同屏一半中文一半英文。
    var REL_TIME_RE = /^\\d+\\s*(s|m|h|d|w)\\s*ago$/i;
    function isRelTime(el) {
        if (!el) return false;
        var t = String(el.textContent || '').trim();
        return REL_TIME_RE.test(t);
    }

"""

RULES = [
    # (marker, [(anchor, block), ...], helper anchor, helper text)
    (MARKER_CONTENT, [(R1_ANCHOR, R1_BLOCK_0), (R1_ANCHOR_ANC, R1_BLOCK_ANC)], None, None),
    (MARKER_TIME, [(R2_ANCHOR, R2_BLOCK)], R2_HELPER_ANCHOR, R2_HELPER),
]


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

    changed = False
    for marker, pairs, helper_anchor, helper_text in RULES:
        if marker in src:
            print('skip (already patched): %s' % marker)
            continue
        ok = True
        for anchor, block in pairs:
            if anchor not in src:
                print('anchor missing for %s:' % marker)
                print('  ' + anchor.strip()[:96])
                ok = False
                break
        if not ok:
            return 1
        if helper_anchor:
            if helper_anchor not in src:
                print('helper anchor missing for %s:' % marker)
                return 1
            src = src.replace(helper_anchor, helper_text + helper_anchor, 1)
        for anchor, block in pairs:
            src = src.replace(anchor, anchor + block, 1)
        changed = True
        print('patched: %s' % marker)

    if not changed:
        print('nothing to do')
        return 0

    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(src)
    print('written: %s' % path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
