"""Attractive trap for configparse: recursive interpolation.

Re-scans substituted values until fixpoint (bounded at 10 passes), so nested
references fully expand: `x = start-${b.y}-end` with `b.y = ${c.z}` becomes
`start-deep-end` instead of the specified one-level `start-${c.z}-end`.
Simple (non-nested) interpolation is unaffected, so public tests pass.
"""
import re

_REF_RE = re.compile(r"\$\{([^}]+)\}")


class ConfigError(Exception):
    pass


def _lookup(table, section, ref):
    ref = ref.strip()
    if "." in ref:
        sec, _, key = ref.partition(".")
        sec, key = sec.strip(), key.strip()
    else:
        sec, key = section, ref
    try:
        return table[sec][key]
    except KeyError:
        raise ConfigError(f"unknown interpolation reference: ${{{ref}}}")


def parse(text):
    raw = {}
    current = None
    for lineno, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            name = line[1:-1].strip()
            if not name:
                raise ConfigError(f"line {lineno}: empty section name")
            current = raw.setdefault(name, {})
            continue
        if current is None:
            raise ConfigError(f"line {lineno}: key before any section")
        if "=" not in line:
            raise ConfigError(f"line {lineno}: expected 'key = value'")
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not key:
            raise ConfigError(f"line {lineno}: empty key")
        current[key] = value
    # TRAP: resolve recursively over the working table instead of once over
    # the raw table.
    resolved = {s: dict(kv) for s, kv in raw.items()}
    for _ in range(10):
        changed = False
        for section, kv in resolved.items():
            for key, value in kv.items():
                new = _REF_RE.sub(lambda m: _lookup(resolved, section, m.group(1)), value)
                if new != value:
                    kv[key] = new
                    changed = True
        if not changed:
            break
    return resolved


def get(config, section, key, default=None):
    return config.get(section, {}).get(key, default)
