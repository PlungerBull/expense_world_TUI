"""`dropped_bank_files` — a line of dropped/pasted paths, read without a terminal.

The formats are what each emulator types on a drop: Terminal.app escapes with
backslashes, VS Code single-quotes for bash/zsh (double quotes for other
shells), and a hand-pasted path may be raw.
"""

from pathlib import Path

import pytest

from expense.tui.dropped import dropped_bank_files

NAMES = ("Sueldo Soles (1).xlsx", "Cuenta Digital Dólares.xlsx", "movimientos.xlsx")


@pytest.fixture
def files(tmp_path) -> list[Path]:
    made = []
    for name in NAMES:
        path = tmp_path / name
        path.write_bytes(b"")
        made.append(path)
    return made


def _escaped(path: Path) -> str:
    """Terminal.app: every shell-special character backslash-escaped."""
    return "".join("\\" + c if c in " ()'&$!;" else c for c in str(path))


def _single(path: Path) -> str:
    """VS Code with bash/zsh: single quotes, a quote inside as `'\\''`."""
    return "'" + str(path).replace("'", "'\\''") + "'"


def _double(path: Path) -> str:
    return '"' + str(path) + '"'


def test_a_plain_absolute_path(tmp_path):
    path = tmp_path / "movimientos.xlsx"
    path.write_bytes(b"")
    assert dropped_bank_files(str(path)) == [path]


def test_a_home_relative_path(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "Downloads").mkdir()
    path = tmp_path / "Downloads" / "movimientos.xlsx"
    path.write_bytes(b"")
    assert dropped_bank_files("~/Downloads/movimientos.xlsx") == [path]


def test_a_raw_pasted_path_with_spaces_and_parentheses(files):
    assert dropped_bank_files(str(files[0])) == [files[0]]


def test_terminal_app_escapes_spaces_and_parentheses(files):
    line = _escaped(files[0])
    assert "\\ " in line and "\\(" in line and "\\)" in line
    assert dropped_bank_files(line) == [files[0]]


def test_terminal_app_escapes_any_other_character(tmp_path):
    path = tmp_path / "it's & $now!; ok.xlsx"
    path.write_bytes(b"")
    assert dropped_bank_files(_escaped(path)) == [path]
    # an escaped ordinary letter is that letter, as in a shell
    assert dropped_bank_files(str(path.parent) + "/it\\'s\\ \\&\\ \\$now\\!\\;\\ o\\k.xlsx") == [
        path
    ]


def test_vs_code_single_quoted(files):
    assert dropped_bank_files(_single(files[0])) == [files[0]]


def test_vs_code_single_quoted_with_a_quote_inside(tmp_path):
    path = tmp_path / "it's.xlsx"
    path.write_bytes(b"")
    assert dropped_bank_files(_single(path)) == [path]


def test_double_quoted(files):
    assert dropped_bank_files(_double(files[0])) == [files[0]]


@pytest.mark.parametrize("quote", [_escaped, _single, _double])
@pytest.mark.parametrize("count", [2, 3])
def test_several_files_in_one_drop(files, quote, count):
    line = " ".join(quote(f) for f in files[:count])
    assert dropped_bank_files(line) == files[:count]


def test_formats_mix_in_one_line(files):
    line = f"{_escaped(files[0])} {_single(files[1])} {_double(files[2])}"
    assert dropped_bank_files(line) == files


@pytest.mark.parametrize("pad", [("  ", "  "), ("", " "), ("", "\n"), ("\t", " \r\n")])
def test_surrounding_whitespace_and_a_trailing_newline(files, pad):
    before, after = pad
    assert dropped_bank_files(before + _escaped(files[0]) + after) == [files[0]]
    assert dropped_bank_files(before + str(files[0]) + after) == [files[0]]


def test_upper_case_suffix_is_accepted(tmp_path):
    path = tmp_path / "MOVIMIENTOS.XLSX"
    path.write_bytes(b"")
    assert dropped_bank_files(str(path)) == [path]


def test_a_file_that_does_not_exist_is_not_a_path(tmp_path):
    assert dropped_bank_files(str(tmp_path / "gone.xlsx")) is None


def test_an_existing_file_that_is_not_xlsx_is_not_a_path(tmp_path):
    path = tmp_path / "movimientos.csv"
    path.write_bytes(b"")
    assert dropped_bank_files(str(path)) is None


def test_a_folder_named_like_a_workbook_is_not_a_path(tmp_path):
    folder = tmp_path / "carpeta.xlsx"
    folder.mkdir()
    assert dropped_bank_files(str(folder)) is None


def test_a_relative_path_is_not_a_path(files, monkeypatch):
    monkeypatch.chdir(files[2].parent)
    assert dropped_bank_files(files[2].name) is None


@pytest.mark.parametrize("quote", [_escaped, _single, _double])
def test_one_good_and_one_bad_path_leave_the_whole_line_quick_add(files, tmp_path, quote):
    missing = tmp_path / "gone.xlsx"
    assert dropped_bank_files(f"{quote(files[0])} {quote(missing)}") is None
    assert dropped_bank_files(f"{quote(files[0])} -28") is None


@pytest.mark.parametrize(
    "line",
    [
        "",
        "   ",
        "Cine -28 @BCP #ocio",
        "tottus porongoche -38.60 $BCP Signature PEN @KORAKUEN #CAJA CHICA",
        "McDonald's -20 $BCP PEN",  # an unclosed quote to shlex
        "-6.60 $BCP PEN //movimientos.xlsx",
        "~nobody_here_at_all/x.xlsx",
    ],
)
def test_ordinary_quick_add_lines_are_not_paths(line):
    assert dropped_bank_files(line) is None
