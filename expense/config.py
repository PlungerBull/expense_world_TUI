import json
import os
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, ValidationError

from expense.errors import ConfigInvalidError, ConfigMissingError


def config_path() -> Path:
    return Path(os.environ.get("EXPENSE_CONFIG", "~/.expense-config")).expanduser()


def validate_engine_url(url: str) -> None:
    """Reject a URL without an http(s) scheme + host. Raises ConfigInvalidError.

    httpx raises UnsupportedProtocol only at request time; both config entry
    points (`config set --engine-url` and the TUI ConfigScreen) call this so
    the mistake surfaces at save time, not on the next command.
    Deliberately not inside save(): saves that don't touch engine_url (e.g.
    mirroring main_currency) must not brick on a legacy-invalid URL.
    """
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ConfigInvalidError(
            "engine URL must be a full URL with scheme and host, "
            "e.g. https://expense-world-engine.onrender.com"
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
            f"Config file at {path} is not valid JSON: {exc}. "
            "Run: expense config set --engine-url <url> --token <pat>"
        ) from exc
    try:
        return Config.model_validate(raw)
    except ValidationError as exc:
        raise ConfigInvalidError(
            f"Config file at {path} is invalid: {exc}. "
            "Run: expense config set --engine-url <url> --token <pat>"
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
        raise ConfigMissingError(
            "No config found. Run: expense config set --engine-url <url> --token <pat>"
        )
    return cfg
