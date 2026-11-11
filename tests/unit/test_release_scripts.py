"""scripts/prepare_release.py and scripts/release.py, against a tmp bare remote and clones.

`gh` and `pipx` are fakes on PATH: the first prints the CI runs a test sets, the second logs its
arguments. Nothing touches the real live folder, the real remote or the real pipx.
"""

import datetime
import os
import subprocess

import pytest

from tests.scripts_loader import load_script

release = load_script("release.py")
prepare = load_script("prepare_release.py")

PYPROJECT = '[project]\nname = "expense-world-tui"\nversion = "{}"\n'
CHANGELOG = "# Changelog\n\n## Unreleased\n{}\n"
GREEN = '[{"status": "completed", "conclusion": "success"}]'


def sh(cwd, *cmd):
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture(autouse=True)
def fakes(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(f"#!/bin/sh\ncat {tmp_path}/ci.json\n")
    pipx = bin_dir / "pipx"
    pipx.write_text(
        f'#!/bin/sh\nprintf "%s\\n" "$@" >> {tmp_path}/pipx.log\n'
        f"[ -f {tmp_path}/pipx.fail ] && exit 1\nexit 0\n"
    )
    for fake in (gh, pipx):
        fake.chmod(0o755)
    (tmp_path / "ci.json").write_text(GREEN)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    for who in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{who}_NAME", "t")
        monkeypatch.setenv(f"GIT_{who}_EMAIL", "t@example.com")


def commit(repo, version, unreleased="", entries=""):
    """A develop commit holding that version, its Unreleased lines and released entries."""
    (repo / "pyproject.toml").write_text(PYPROJECT.format(version))
    (repo / "CHANGELOG.md").write_text(CHANGELOG.format(unreleased) + entries)
    (repo / "constraints.txt").write_text("")
    sh(repo, "git", "add", "-A")
    sh(repo, "git", "commit", "-qm", version)
    return sh(repo, "git", "rev-parse", "HEAD")


class World:
    """A bare remote; `dev` is the agents' clone; `live` the owner's, on main."""

    def __init__(self, tmp_path):
        self.remote = tmp_path / "remote.git"
        self.dev = tmp_path / "dev"
        self.live = tmp_path / "Application Support" / "tui"
        sh(tmp_path, "git", "init", "-q", "--bare", "-b", "main", str(self.remote))
        sh(tmp_path, "git", "clone", "-q", str(self.remote), str(self.dev))
        sh(self.dev, "git", "checkout", "-q", "-b", "main")
        commit(self.dev, "0.0.1")
        sh(self.dev, "git", "push", "-q", "origin", "main")
        sh(self.dev, "git", "checkout", "-q", "-b", "develop")
        sh(self.dev, "git", "push", "-q", "origin", "develop")
        self.live.parent.mkdir()
        sh(tmp_path, "git", "clone", "-q", str(self.remote), str(self.live))
        self.log = tmp_path / "pipx.log"

    def prepare_on_develop(self, version, entries=""):
        entry = f"## v{version} — 2026-11-12\n\n- a change\n\n"
        sha = commit(self.dev, version, entries=entry + entries)
        sh(self.dev, "git", "push", "-q", "origin", "develop")
        return sha

    def run(self, command=release.release):
        return command(self.live, self.live)

    def remote_ref(self, ref):
        return sh(self.remote, "git", "rev-parse", ref)


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


def test_release_moves_main_tags_pushes_and_installs(world):
    sha = world.prepare_on_develop("1.0.0")
    world.run()
    assert sh(world.live, "git", "rev-parse", "main") == sha
    assert world.remote_ref("main") == sha
    assert world.remote_ref("v1.0.0^{commit}") == sha
    call = world.log.read_text().splitlines()
    assert call[:4] == ["install", "--force", "--python", "python3.12"]
    assert f"--pip-args=-c '{world.live}/constraints.txt'" in call
    assert call[-1] == str(world.live)
    assert "--editable" not in call and "-e" not in call


def test_releases_the_prepared_commit_not_later_develop_work(world):
    prepared_sha = world.prepare_on_develop("1.0.0")
    (world.dev / "later.txt").write_text("x")
    sh(world.dev, "git", "add", "-A")
    sh(world.dev, "git", "commit", "-qm", "later work")
    sh(world.dev, "git", "push", "-q", "origin", "develop")
    world.run()
    assert world.remote_ref("main") == prepared_sha
    assert world.remote_ref("v1.0.0^{commit}") == prepared_sha


def test_another_version_line_in_pyproject_is_not_a_release(world):
    prepared_sha = world.prepare_on_develop("1.0.0")
    with (world.dev / "pyproject.toml").open("a") as pyproject:
        pyproject.write('\n[tool.other]\nversion = "9"\n')
    sh(world.dev, "git", "commit", "-qam", "another table")
    sh(world.dev, "git", "push", "-q", "origin", "develop")
    world.run()
    assert world.remote_ref("main") == prepared_sha


def test_a_failed_pipx_names_latest_and_the_release_is_already_pushed(world, tmp_path):
    sha = world.prepare_on_develop("1.0.0")
    (tmp_path / "pipx.fail").write_text("")
    with pytest.raises(release.Refusal, match="latest"):
        world.run()
    assert world.remote_ref("main") == sha
    assert world.remote_ref("v1.0.0^{commit}") == sha


def test_a_rejected_push_rolls_back_so_a_rerun_works(world):
    world.prepare_on_develop("1.0.0")
    main_before = sh(world.live, "git", "rev-parse", "main")
    hook = world.remote / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    refused(world, "Nothing changed")
    assert sh(world.live, "git", "rev-parse", "main") == main_before
    assert sh(world.live, "git", "tag") == ""
    hook.unlink()
    world.run()
    assert world.remote_ref("v1.0.0^{commit}") == world.remote_ref("main")


def refused(world, match, command=release.release):
    with pytest.raises(release.Refusal, match=match):
        world.run(command)
    assert not world.log.exists()


def test_refuses_outside_the_live_folder(world, tmp_path):
    world.prepare_on_develop("1.0.0")
    with pytest.raises(release.Refusal, match="only in the live folder"):
        release.release(world.live, tmp_path / "elsewhere")


def test_refuses_a_dirty_tree(world):
    world.prepare_on_develop("1.0.0")
    (world.live / "stray.txt").write_text("x")
    refused(world, "has changes")


def test_refuses_another_branch(world):
    world.prepare_on_develop("1.0.0")
    sh(world.live, "git", "checkout", "-q", "-b", "side")
    refused(world, "not `main`")


def test_refuses_a_version_already_tagged(world):
    world.prepare_on_develop("1.0.0")
    world.run()
    world.log.unlink()
    refused(world, "already released")


def test_refuses_a_version_without_a_changelog_entry(world):
    commit(world.dev, "1.0.0", unreleased="- a change\n")
    sh(world.dev, "git", "push", "-q", "origin", "develop")
    refused(world, "no entry for v1.0.0")


@pytest.mark.parametrize(
    "runs", ["[]", '[{"status": "completed", "conclusion": "failure"}]', '[{"status": "queued"}]']
)
def test_refuses_unless_ci_passed(world, tmp_path, runs):
    world.prepare_on_develop("1.0.0")
    (tmp_path / "ci.json").write_text(runs)
    refused(world, "CI has not passed")
    assert world.remote_ref("main") != world.remote_ref("develop")


def test_refuses_when_main_cannot_fast_forward(world):
    world.prepare_on_develop("1.0.0")
    (world.live / "other.txt").write_text("x")
    sh(world.live, "git", "add", "-A")
    sh(world.live, "git", "commit", "-qm", "diverged")
    refused(world, "cannot fast-forward")
    assert "v1.0.0" not in sh(world.live, "git", "tag")


def test_back_installs_the_previous_tag_and_a_release_returns_from_it(world):
    world.prepare_on_develop("1.0.0")
    world.run()
    first = sh(world.live, "git", "rev-parse", "v1.0.0")
    world.prepare_on_develop("1.1.0")
    world.run()
    world.log.unlink()

    message = world.run(release.back)
    assert sh(world.live, "git", "rev-parse", "HEAD") == first
    assert sh(world.live, "git", "rev-parse", "--abbrev-ref", "HEAD") == "HEAD"
    assert world.remote_ref("main") == sh(world.live, "git", "rev-parse", "v1.1.0")
    assert "latest" in message and world.log.exists()

    world.prepare_on_develop("1.2.0")
    world.run()
    assert sh(world.live, "git", "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert world.remote_ref("v1.2.0^{commit}") == world.remote_ref("main")


def test_back_refuses_with_no_earlier_release_and_latest_returns_to_main(world):
    world.prepare_on_develop("1.0.0")
    world.run()
    world.log.unlink()
    refused(world, "no release before v1.0.0", release.back)
    world.prepare_on_develop("1.1.0")
    world.run()
    world.run(release.back)
    world.run(release.latest)
    assert sh(world.live, "git", "rev-parse", "--abbrev-ref", "HEAD") == "main"


# --- prepare_release.py ---


def prepared(tmp_path, unreleased, tags=()):
    repo = tmp_path / "work"
    remote = tmp_path / "origin.git"
    sh(tmp_path, "git", "init", "-q", "--bare", str(remote))
    sh(tmp_path, "git", "clone", "-q", str(remote), str(repo))
    commit(repo, "0.0.1", unreleased=unreleased)
    for tag in tags:
        sh(repo, "git", "tag", tag)
    return repo


def test_prepare_moves_unreleased_under_the_version_with_upgrading_first(tmp_path):
    repo = prepared(tmp_path, "\n- Screen\nUpgrading: engine 2.0.0 first\n")
    prepare.prepare(repo, "1.0.0", datetime.date(2026, 11, 12))
    assert (repo / "CHANGELOG.md").read_text() == (
        "# Changelog\n\n## Unreleased\n\n## v1.0.0 — 2026-11-12\n\n"
        "Upgrading: engine 2.0.0 first\n- Screen\n\n"
    )
    assert 'version = "1.0.0"' in (repo / "pyproject.toml").read_text()


@pytest.mark.parametrize(
    ("unreleased", "version", "tags", "match"),
    [
        ("", "1.0.0", (), "nothing under"),
        ("- x", "1.0.0", ("v1.0.0",), "not above"),
        ("- x", "1.0", (), "not X.Y.Z"),
    ],
)
def test_prepare_refuses(tmp_path, unreleased, version, tags, match):
    repo = prepared(tmp_path, unreleased, tags)
    with pytest.raises(prepare.release.Refusal, match=match):
        prepare.prepare(repo, version, datetime.date(2026, 11, 12))
    assert 'version = "0.0.1"' in (repo / "pyproject.toml").read_text()


def test_prepare_refuses_a_pyproject_without_a_version(tmp_path):
    repo = prepared(tmp_path, "- x")
    (repo / "pyproject.toml").write_text("[project]\n")
    sh(repo, "git", "commit", "-qam", "no version")
    with pytest.raises(prepare.release.Refusal, match="no `version"):
        prepare.prepare(repo, "1.0.0", datetime.date(2026, 11, 12))


def test_prepare_refuses_a_dirty_tree(tmp_path):
    repo = prepared(tmp_path, "- x")
    (repo / "stray.txt").write_text("x")
    with pytest.raises(prepare.release.Refusal, match="has changes"):
        prepare.prepare(repo, "1.0.0", datetime.date(2026, 11, 12))
