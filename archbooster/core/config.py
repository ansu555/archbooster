"""
Loads ~/.config/archbooster/config.toml.
Creates a default config if none exists.
"""
import tomllib
from pathlib import Path
from dataclasses import dataclass, field

CONFIG_FILE = Path.home() / ".config" / "archbooster" / "config.toml"

DEFAULT_TOML = """\
[general]
aur_helper      = "yay"   # "yay" or "paru"
check_interval  = 4       # hours between background daemon scans

[categories]
# Add package name prefixes to override auto-classification
extra_critical = []
extra_optional = []

[ignore]
# Packages listed here are hidden from the update list entirely
packages = []
"""


@dataclass
class Config:
    aur_helper:     str       = "yay"
    check_interval: int       = 4
    extra_critical: list[str] = field(default_factory=list)
    extra_optional: list[str] = field(default_factory=list)
    ignored:        list[str] = field(default_factory=list)


def load_config() -> Config:
    if not CONFIG_FILE.exists():
        _write_default()
    raw = tomllib.loads(CONFIG_FILE.read_text())
    g   = raw.get("general",    {})
    cat = raw.get("categories", {})
    ign = raw.get("ignore",     {})
    return Config(
        aur_helper     = g.get("aur_helper",     "yay"),
        check_interval = g.get("check_interval", 4),
        extra_critical = cat.get("extra_critical", []),
        extra_optional = cat.get("extra_optional", []),
        ignored        = ign.get("packages",      []),
    )


def _write_default() -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(DEFAULT_TOML)
