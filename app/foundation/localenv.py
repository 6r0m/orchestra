"""Read deployment-private values without exporting them into a process's environment."""
import os

from app.foundation import paths


def read(path=None):
    """NAME=value entries; an absent file is empty, while an unreadable file raises."""
    path = os.path.join(paths.REPO, ".env") if path is None else path
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except FileNotFoundError:
        return {}
    entries = {}
    for line in lines:
        name, sep, value = line.partition("=")
        name = name.strip()
        if sep and name and not name.startswith("#"):
            entries[name] = value.strip().strip("'\"")
    return entries
