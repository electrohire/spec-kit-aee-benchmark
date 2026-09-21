"""INI-ish config parser with one-level interpolation (reference)."""
import re

_REF_RE = re.compile(r"\$\{([^}]+)\}")


class ConfigError(Exception):
    pass


def _lookup(raw, section, ref):
    ref = ref.strip()
    if "." in ref:
        sec, _, key = ref.partition(".")
        sec, key = sec.strip(), key.strip()
    else:
        sec, key = section, ref
    try:
        return raw[sec][key]
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
    resolved = {}
    for section, kv in raw.items():
        out = {}
        for key, value in kv.items():
            out[key] = _REF_RE.sub(lambda m: _lookup(raw, section, m.group(1)), value)
        resolved[section] = out
    return resolved


def get(config, section, key, default=None):
    return config.get(section, {}).get(key, default)
