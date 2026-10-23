"""Minimal S-expression reader/writer for KiCad files.

Atoms are kept as Python str; quoted strings are wrapped in QStr so they
round-trip with quotes. Lists are Python lists.
"""


class QStr(str):
    """A string atom that was (or must be) quoted."""


def parse(text):
    pos = 0
    n = len(text)
    stack = [[]]
    while pos < n:
        c = text[pos]
        if c in " \t\r\n":
            pos += 1
        elif c == "(":
            stack.append([])
            pos += 1
        elif c == ")":
            done = stack.pop()
            stack[-1].append(done)
            pos += 1
        elif c == '"':
            pos += 1
            buf = []
            while text[pos] != '"':
                if text[pos] == "\\":
                    pos += 1
                    buf.append({"n": "\n", "t": "\t"}.get(text[pos], text[pos]))
                else:
                    buf.append(text[pos])
                pos += 1
            pos += 1
            stack[-1].append(QStr("".join(buf)))
        else:
            start = pos
            while pos < n and text[pos] not in " \t\r\n()":
                pos += 1
            stack[-1].append(text[start:pos])
    return stack[0][0]


def _atom(a):
    if isinstance(a, QStr):
        return '"' + a.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
    if isinstance(a, float):
        s = f"{a:.4f}".rstrip("0").rstrip(".")
        return "0" if s == "-0" else s
    return str(a)


def dumps(node, indent=0):
    """Serialize in KiCad's style: short lists inline, nested lists indented."""
    if not isinstance(node, list):
        return _atom(node)
    if not any(isinstance(x, list) for x in node):
        return "(" + " ".join(_atom(x) for x in node) + ")"
    tab = "\t" * (indent + 1)
    out = "(" + " ".join(_atom(x) for x in node if not isinstance(x, list))
    # keep atoms that follow sub-lists in order (rare in KiCad files)
    for x in node:
        if isinstance(x, list):
            if x and x[0] == "xy":
                out += " " + dumps(x, indent + 1)
            else:
                out += "\n" + tab + dumps(x, indent + 1)
    return out + "\n" + "\t" * indent + ")"


def find(node, key):
    """First child list whose head is key."""
    for x in node:
        if isinstance(x, list) and x and x[0] == key:
            return x
    return None


def find_all(node, key):
    return [x for x in node if isinstance(x, list) and x and x[0] == key]
