import json
from uuid import uuid4

import pytest

from expense import config
from expense.errors import ConfigInvalidError, ConfigMissingError


@pytest.fixture
def tmp_config(tmp_path, monkeypatch):
    config_path = tmp_path / ".expense-config"
    monkeypatch.setenv("EXPENSE_CONFIG", str(config_path))
    yield config_path


def test_load_missing_file_returns_none(tmp_config):
    assert config.load() is None


@pytest.mark.parametrize("url", ["https://example.com", "http://localhost:8000"])
def test_validate_engine_url_accepts_http_https_with_host(url):
    config.validate_engine_url(url)  # no raise


@pytest.mark.parametrize(
    "url", ["example.com", "ftp://example.com", "https://", "", "expense-world.onrender.com/v1"]
)
def test_validate_engine_url_rejects_scheme_or_host_less(url):
    """Shared save-time guard for the TUI SetupScreen and ConfigScreen
    — httpx would only fail at request time."""
    with pytest.raises(ConfigInvalidError, match="scheme and host"):
        config.validate_engine_url(url)


def test_save_and_load_round_trip(tmp_config):
    cfg = config.Config(
        engine_url="https://example.com",
        token="ewe_pat_abc123",
        main_currency="USD",
    )
    config.save(cfg)

    loaded = config.load()
    assert loaded is not None
    assert loaded.engine_url == cfg.engine_url
    assert loaded.token == cfg.token
    assert loaded.main_currency == cfg.main_currency


def test_save_chmod_600(tmp_config):
    cfg = config.Config(engine_url="https://example.com")
    config.save(cfg)

    mode = tmp_config.stat().st_mode & 0o777
    assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"


def test_load_corrupt_json_raises_config_invalid(tmp_config):
    tmp_config.write_text("{not valid json")
    with pytest.raises(ConfigInvalidError, match="not valid JSON") as exc:
        config.load()
    assert "setup screen" in str(exc.value)


def test_load_schema_invalid_raises_config_invalid(tmp_config):
    # Valid JSON, but missing the one required field (engine_url).
    tmp_config.write_text(json.dumps({"token": "ewe_pat_abc"}))
    with pytest.raises(ConfigInvalidError, match="invalid") as exc:
        config.load()
    assert "setup screen" in str(exc.value)


def test_ensure_loaded_raises_if_missing(tmp_config):
    with pytest.raises(ConfigMissingError) as exc:
        config.ensure_loaded()
    assert "setup screen" in str(exc.value)


@pytest.mark.parametrize("key", ["client_id", "bank_files", "future_field"])
def test_a_key_the_app_does_not_know_loads_and_is_dropped_on_save(tmp_config, key):
    """Older configs carry `client_id` or `bank_files`: neither is a validation
    error, none is read, and the next save leaves it out."""
    tmp_config.write_text(
        json.dumps(
            {
                "engine_url": "https://a.com",
                "token": "ewe_pat_old",
                key: {"Sueldo Soles": "BCP"} if key == "bank_files" else str(uuid4()),
            }
        )
    )

    loaded = config.load()
    assert loaded is not None
    assert (loaded.engine_url, loaded.token) == ("https://a.com", "ewe_pat_old")
    assert not hasattr(loaded, key)

    config.save(loaded)
    saved = json.loads(tmp_config.read_text())
    assert key not in saved and saved["token"] == "ewe_pat_old"


def test_the_hermetic_fixture_points_the_config_away_from_the_real_file():
    """The autouse fixture in conftest.py: no test reads or writes `~/.expense-config`."""
    assert config.config_path().name == "hermetic-config"


def test_expense_config_env_var_honored(tmp_path, monkeypatch):
    custom = tmp_path / "custom-config-name.json"
    monkeypatch.setenv("EXPENSE_CONFIG", str(custom))

    cfg = config.Config(engine_url="https://x.com")
    config.save(cfg)

    assert custom.exists()
    assert not (tmp_path / ".expense-config").exists()


def test_corrupt_config_renders_clean_cli_error(tmp_config):
    """A corrupt config exits 3 with the recovery hint — no traceback. The
    settings are read before the file, so no file is needed."""
    from typer.testing import CliRunner

    from tests.unit.helpers import real_cli_app

    cli_app = real_cli_app()

    tmp_config.write_text("{not valid json")
    runner = CliRunner()
    result = runner.invoke(cli_app, ["import", "sheet", "s.xlsx"])
    assert result.exit_code == 3
    assert "not valid JSON" in result.output
    assert "setup screen" in result.output
    assert "Traceback" not in result.output


def _settings(**over):
    return config.Config(engine_url="https://example.com", token="ewe_pat_a", **over)


def test_held_settings_are_used_without_reading_the_file_again(tmp_config):
    config.save(_settings())
    config.hold(config.load())
    tmp_config.unlink()

    assert config.ensure_loaded().token == "ewe_pat_a"
    assert config.ensure_loaded().engine_url == "https://example.com"


def test_save_replaces_the_held_settings(tmp_config):
    config.hold(None)
    with pytest.raises(ConfigMissingError):
        config.ensure_loaded()

    config.save(_settings(main_currency="PEN"))
    tmp_config.unlink()

    assert config.ensure_loaded().main_currency == "PEN"


def test_save_without_holding_leaves_reads_on_the_file(tmp_config):
    config.save(_settings())
    config.save(_settings(main_currency="USD"))
    assert config.ensure_loaded().main_currency == "USD"


def test_launch_reads_the_settings_once_so_a_pipe_works(tmp_config, monkeypatch):
    """`launch` is the only read of the file: a named pipe gives its contents once."""
    import os
    import threading

    from expense.tui import app as app_module

    os.mkfifo(tmp_config)
    payload = json.dumps({"engine_url": "http://127.0.0.1:8002", "token": "k"})

    def feed():
        with open(tmp_config, "w") as pipe:
            pipe.write(payload)

    writer = threading.Thread(target=feed, daemon=True)
    writer.start()
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True, raising=False)
    seen = {}
    real, calls = config.load, []

    def counted():
        calls.append(1)
        assert len(calls) == 1, "second read of the settings file"
        return real()

    monkeypatch.setattr(config, "load", counted)

    def run(self, **kw):
        seen["setup"] = self._setup
        seen["cfg"] = config.ensure_loaded()

    monkeypatch.setattr(app_module.ExpenseApp, "run", run)
    monkeypatch.setattr(app_module, "get_verbose", lambda ctx: False)
    app_module.launch(None)
    writer.join(timeout=5)

    assert len(calls) == 1
    assert seen["setup"] is False
    assert seen["cfg"].token == "k"
