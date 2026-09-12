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
    the mistake surfaces at save time, not on the next command (backlog 6.3b).
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
    # extra="ignore" also tolerates the retired client_id key still present in
    # config files written before the sync deletion (2026-08-06).
    model_config = ConfigDict(extra="ignore")

    engine_url: str
    token: str | None = None
    main_currency: str | None = None
    # `expense import bank`: the file's stem ("VISA Infinite Sapphire") → the
    # account base name it was last imported into ("BCP Signature"). Written
    # the first time a file is imported, read on every run after, overridden
    # by --account (2026-09-12, mockup expense-world-bank-import.html pick B).
    bank_files: dict[str, str] = {}


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
