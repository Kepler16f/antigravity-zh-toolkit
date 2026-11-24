#!/usr/bin/env python3
"""Teach the localization engine to translate a whitelist of aria-label values.

Why this exists: the engine deliberately skips `aria-label` because some host
code compares the raw attribute (e.g. `getAttribute("aria-label")==="Cancel"`)
to decide behaviour - translating it would break that logic. But Antigravity's
own icon buttons use aria-label as their only tooltip text, so those stay
English.

The fix is a whitelist: the dictionary carries `ariaLabelSafe` (literal values)
and `ariaLabelSafePatterns` (regular expressions for labels that embed a
dynamic part, e.g. "Select model, current: <model>"). The engine only rewrites
an aria-label when the current value matches that whitelist, so the host's
logic-comparison values are never touched.

Idempotent. Usage:
    python patch_engine.py [tool_dir]
"""
import re
import sys
from pathlib import Path

MARKER = "ARIA_LABEL_SAFE_V1"


def patch_engine(root: Path) -> str:
    path = root / "engine.js"
    if not path.is_file():
        return "engine.js not found"
    src = path.read_text(encoding="utf-8")
    if MARKER in src:
        return "already patched"

    # 1) declare the whitelist next to the other rule tables
    anchor = "    var rawCats = DATA.mentionCategories || [];"
    if anchor not in src:
        return "anchor (rawCats) not found"
    decl = (
        f"    // {MARKER}: only these aria-label values may be rewritten. The\n"
        "    // engine never touches aria-label by default because host code compares\n"
        "    // the raw attribute; the whitelist keeps that guarantee for every other\n"
        "    // value while still translating Antigravity's own button tooltips.\n"
        "    var ARIA_SAFE = DATA.ariaLabelSafe || [];\n"
        "    var ARIA_SAFE_PATTERNS = [];\n"
        "    var ARIA_SAFE_RE = [];\n"
        "    for (i = 0; i < (DATA.ariaLabelSafePatterns || []).length; i++) {\n"
        "        try { ARIA_SAFE_RE.push(new RegExp(DATA.ariaLabelSafePatterns[i])); } catch (e) { }\n"
        "    }\n"
    )
    src = src.replace(anchor, decl + anchor, 1)

    # 2) translate whitelisted aria-label values in translateAttrs
    fn_anchor = """            var attrOut = translateString(attrVal);
                    if (attrVal !== attrOut) node.setAttribute(attr, attrOut);
                }
            }
        }
    }"""
    if fn_anchor not in src:
        return "anchor (translateAttrs) not found"
    fn_new = """            var attrOut = translateString(attrVal);
                    if (attrVal !== attrOut) node.setAttribute(attr, attrOut);
                }
            }
            // aria-label: whitelisted values only (see ARIA_SAFE above)
            var ariaVal = node.getAttribute('aria-label');
            if (ariaVal && LETTER_RE.test(ariaVal)) {
                var ariaSafe = false;
                for (var ai = 0; ai < ARIA_SAFE.length; ai++) {
                    if (ARIA_SAFE[ai] === ariaVal) { ariaSafe = true; break; }
                }
                if (!ariaSafe) {
                    for (var aj = 0; aj < ARIA_SAFE_RE.length; aj++) {
                        if (ARIA_SAFE_RE[aj].test(ariaVal)) { ariaSafe = true; break; }
                    }
                }
                if (ariaSafe) {
                    var ariaOut = translateString(ariaVal);
                    if (ariaVal !== ariaOut) node.setAttribute('aria-label', ariaOut);
                }
            }
        }
    }"""
    src = src.replace(fn_anchor, fn_new, 1)
    path.write_text(src, encoding="utf-8")
    return "patched"


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r"C:/agh/Antigravity一键汉化")
    print("engine:", patch_engine(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
