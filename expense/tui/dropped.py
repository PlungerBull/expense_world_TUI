"""Is this line a bank file dropped on the terminal? — text in, files out.

Dragging a file onto a terminal makes the emulator *type* its path, so the
LOG bar sees a dropped file as ordinary text. Each emulator writes it in its
own shell syntax:

* **Terminal.app** backslash-escapes every character a shell would read
  specially: `/Users/me/Downloads/Sueldo\\ Soles\\ \\(1\\).xlsx`. Several files
  dropped at once arrive space-separated.
* **VS Code's terminal** wraps the path in single quotes for bash and zsh
  (`'/Users/me/Downloads/Sueldo Soles (1).xlsx'`, a quote inside written as
  `'\\''`), and fish/Windows shells may use double quotes. It inserts only the
  first file of a multi-file drop; two drops in a row arrive with nothing
  between them.
* **A path pasted or typed by hand** may be raw, spaces and all.

All of that is POSIX shell word syntax, so `shlex` reads every form; a raw
path with spaces is tried as one literal path first. Typing, pasting and
dropping all reach the bar as the same text and go through this one function.

The line is files only if **every** word is an absolute path (`~/` counts) to
an existing `.xlsx` file, any letter case. One word that is not turns the
whole line back into quick-add — a half-recognised line would import some of
what you dropped and leave the rest as a transaction attempt.
"""

import shlex
from pathlib import Path

#: The bank's export format — the only file the import reads.
SUFFIX = ".xlsx"


def dropped_bank_files(text: str) -> list[Path] | None:
    """The files the line names, in order — or `None` when it is not files.

    Cheap on an ordinary quick-add line: a word is checked against the disk
    only after it already looks like an absolute `.xlsx` path.
    """
    line = text.strip()
    if not line:
        return None
    literal = _bank_file(line)
    if literal is not None:
        return [literal]
    try:
        words = shlex.split(line)
    except ValueError:  # an unclosed quote: `McDonald's -20 $BCP PEN`
        return None
    files = [_bank_file(word) for word in words]
    if not files or any(f is None for f in files):
        return None
    return [f for f in files if f is not None]


def _bank_file(word: str) -> Path | None:
    """`word` as an existing `.xlsx` file at an absolute path, or `None`."""
    try:
        path = Path(word).expanduser()
    except RuntimeError:  # `~name` for a user this machine does not have
        return None
    if not path.is_absolute() or path.suffix.lower() != SUFFIX:
        return None
    return path if path.is_file() else None
