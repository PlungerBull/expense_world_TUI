import json
import os
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, ValidationError

from expense.errors import ConfigInvalidError, ConfigMissingError

#: Where the engine runs on the owner's Mac. The setup screen offers it in its
#: address box, and the "not an address" message gives it as the example.
LOCAL_ENGINE_URL = "http://127.0.0.1:8000"

#: What a message says to do when the settings file is missing or cannot be read.
#: The app's setup screen asks for the engine address and key whenever it opens
#: without a usable settings file, so that is where every such message points.
SETUP_REMEDY = "Open the app: its setup screen asks for the engine address and key."


def config_path() -> Path:
    return Path(os.environ.get("EXPENSE_CONFIG", "~/.expense-config")).expanduser()


def validate_engine_url(url: str) -> None:
    """Reject a URL without an http(s) scheme + host. Raises ConfigInvalidError.

    httpx raises UnsupportedProtocol only at request time; both config entry
    points (`config set --engine-url`, the TUI ConfigScreen and SetupScreen) call this so
    the mistake surfaces at save time, not on the next command.
    Deliberately not inside save(): saves that don't touch engine_url (e.g.
    mirroring main_currency) must not brick on a legacy-invalid URL.
    """
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ConfigInvalidError(
            f"engine URL must be a full URL with scheme and host,\ne.g. {LOCAL_ENGINE_URL}"
        )


class Config(BaseModel):
    # extra="ignore": an older config file may carry keys nothing reads; they
    # load without error and are dropped on the next save.
    model_config = ConfigDict(extra="ignore")

    engine_url: str
    token: str | None = None
    main_currency: str | None = None
    # `expense import sheet`: a sheet account leg ("BCP:PEN" — sheet name,
    # colon, currency) → the ledger name it is written under ("Sueldo Soles").
    # Written by --account-name, read on every run after; a flag for a key
    # already here replaces it.
    sheet_account_names: dict[str, str] = {}


def load() -> Config | None:
    path = config_path()
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ConfigInvalidError(
            f"Config file at {path} is not valid JSON: {exc}. {SETUP_REMEDY}"
        ) from exc
    try:
        return Config.model_validate(raw)
    except ValidationError as exc:
        raise ConfigInvalidError(
            f"Config file at {path} is invalid: {exc}. {SETUP_REMEDY}"
        ) from exc


def save(cfg: Config) -> None:
    # The temp file lands beside the config as `.expense-config.*.tmp` and is then
    # `os.replace`d, so a crash mid-write can leave a copy holding the live token. The
    # engine operator's "Erasing everything" procedure has a step that deletes
    # `~/.expense-config*` to catch it. If the temp file's location or name ever
    # changes, tell the engine side so that step still matches.
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = cfg.model_dump(mode="json")

    with tempfile.NamedTemporaryFile(
        mode="w",
        dir=path.parent,
        prefix=".expense-config.",
        suffix=".tmp",
        delete=False,
    ) as tmp:
        json.dump(payload, tmp, indent=2, sort_keys=True)
        tmp_path = Path(tmp.name)

    if os.name != "nt":
        os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, path)


def clear() -> None:
    path = config_path()
    if path.exists():
        path.unlink()


def ensure_loaded() -> Config:
    cfg = load()
    if cfg is None:
        raise ConfigMissingError(f"No config found. {SETUP_REMEDY}")
    return cfg


def load_usable() -> Config | None:
    """The saved config, or None when there is none the app can use.

    None for a missing file and for one that cannot be read: damaged or
    half-written JSON, a body that is not a config, bytes that are not text, or
    a path the app may not read. The app opens its setup screen on None
    (`expense/tui/app.py`), so a broken file is met the same way as no file.
    """
    try:
        return load()
    except (ConfigInvalidError, OSError, ValueError):
        return None
