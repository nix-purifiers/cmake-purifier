# SPDX-License-Identifier: MIT
#
# Checks handlers.py with stand-in handlers, scripts that claim what a
# handler of a package index would. The flake check `lock-handlers` runs
# it: test_handlers.py <lock dir> <scratch dir>.
import os
import sys

sys.path.insert(0, sys.argv[1])
import handlers

scratch = sys.argv[2]
failures = []


def check(name, got, want):
    if got != want:
        failures.append(f"{name}: got {got!r}, want {want!r}")


def handler(name, body):
    """A stand-in handler: a Python script with `records` read from stdin."""
    path = os.path.join(scratch, name)
    with open(path, "w") as f:
        f.write(f"#!{sys.executable}\nimport json, sys\nrecords = [json.loads(l) for l in sys.stdin if l.strip()]\n{body}\n")
    os.chmod(path, 0o755)
    return path


page = {"method": "GET", "url": "https://index.test/simple/demo/", "status": 200, "hash": "sha256-page"}
wheel = {"method": "GET", "url": "https://files.test/demo-1.0-py3-none-any.whl", "status": 200, "hash": "sha256-wheel"}
other = {"method": "GET", "url": "https://other.test/a.tar.gz", "status": 200, "hash": "sha256-other"}

index = handler(
    "index",
    """
claimed = [r["url"] for r in records if "index.test" in r["url"] or "files.test" in r["url"]]
entries = [{"path": "https/index.test/simple/demo/index.html", "contents": "<html/>"}]
entries += [{"path": "https/files.test/" + r["url"].rsplit("/", 1)[1], "url": r["url"], "mirrors": [], "hash": r["hash"]}
            for r in records if "files.test" in r["url"]]
json.dump({"claimed": claimed, "entries": entries}, sys.stdout)
""",
)
seen = handler(
    "seen",
    """
json.dump({"claimed": [], "entries": [{"path": "seen", "contents": json.dumps([r["url"] for r in records])}]}, sys.stdout)
""",
)

left, entries = handlers.apply_handlers([page, wheel, other], [index, seen])
check("unclaimed responses", left, [other])
check("entry paths", sorted(e["path"] for e in entries), ["https/files.test/demo-1.0-py3-none-any.whl", "https/index.test/simple/demo/index.html", "seen"])
check("a later handler sees only what is unclaimed", [e["contents"] for e in entries if e["path"] == "seen"], ['["https://other.test/a.tar.gz"]'])
check("no handlers", handlers.apply_handlers([page], []), ([page], []))


def raises(name, programs):
    try:
        handlers.apply_handlers([page], programs)
    except handlers.HandlerError:
        return
    failures.append(f"{name}: no HandlerError")


raises("a failing handler", [handler("fails", "sys.exit('no index')")])
raises("a handler that prints no JSON", [handler("garbage", "print('hello')")])
raises("an entry that is both a file and inline", [handler("both", """
json.dump({"claimed": [], "entries": [{"path": "p", "url": "u", "contents": "c"}]}, sys.stdout)
""")])

if failures:
    print("\n".join(failures))
    sys.exit(1)
