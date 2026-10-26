#!/usr/bin/env python3
"""
check_translation.py - check (or start) a language file for the game.

  python check_translation.py                 check every language in lang/
  python check_translation.py es              check lang/es.json only
  python check_translation.py --init es Español
                                              create lang/es.json from the English
                                              file, ready to translate

What a check reports (exit code 1 if anything is wrong, 0 if all is well):
  missing        keys the English file has but yours doesn't (they would show
                 up in English in the game - harmless, but incomplete)
  extra          keys yours has that English doesn't (typos, or outdated keys)
  placeholders   a text whose {placeholders} differ from English's: for
                 example English has "Round {n} / {total}" and yours lost {total}
  empty          texts that are empty
  untranslated   texts identical to English (only informational: many are
                 fine - "Start", "Score", "Memory" - but a long run of them
                 usually means "not translated yet")

See docs/TRANSLATING.md for the full guide.
"""
import json
import os
import sys

import i18n


def check(code):
    """Print the report for one language; return True when it has no problems."""
    problems = i18n.validate(code)
    table = i18n.table(code)
    reference = i18n.table(i18n.FALLBACK_LANGUAGE)
    untranslated = sorted(k for k in reference
                          if not k.startswith("_") and k in table and table[k] == reference[k])
    bad = any(problems.values())
    name = table.get("_language_name", code)
    print(f"{code} ({name}): {'PROBLEMS' if bad else 'ok'}")
    labels = {"missing": "missing keys", "extra": "unknown keys",
              "placeholders": "{placeholders} differ from English", "empty": "empty texts"}
    for kind, label in labels.items():
        for key in problems[kind]:
            detail = ""
            if kind == "placeholders":
                detail = f"   English: {reference[key]!r}   yours: {table[key]!r}"
            print(f"   {label}: {key}{detail}")
    if code != i18n.FALLBACK_LANGUAGE:
        total = len([k for k in reference if not k.startswith("_")])
        same = len(untranslated)
        print(f"   (info: {same} of {total} texts are identical to English"
              f"{' - not translated yet?' if same > total * 0.5 else ''})")
    return not bad


def init_language(code, name):
    """Create lang/<code>.json as a copy of the English file, ready to translate."""
    path = os.path.join(i18n.LANG_DIR, f"{code}.json")
    if os.path.exists(path):
        print(f"lang/{code}.json already exists - not overwriting it.")
        return False
    reference = i18n.table(i18n.FALLBACK_LANGUAGE)
    data = dict(reference)
    data["_language_name"] = name
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"Created lang/{code}.json - now translate the values (not the keys!), then run:")
    print(f"    python check_translation.py {code}")
    return True


def main(argv):
    if argv and argv[0] == "--init":
        if len(argv) != 3:
            print("usage: python check_translation.py --init <code> <language name>")
            return 2
        i18n.reload()
        return 0 if init_language(argv[1], argv[2]) else 1
    i18n.reload()
    codes = argv or [code for code, _name in i18n.available_languages()]
    ok = True
    for code in codes:
        if code not in dict(i18n.available_languages()):
            print(f"{code}: no file lang/{code}.json")
            ok = False
            continue
        ok = check(code) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
