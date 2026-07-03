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
confirm         = false   # false: run pacman/yay non-interactively (your
                          #        selection in ArchBooster is the confirmation).
                          # true:  also show the package manager's own prompts
                          #        (best when running from a plain terminal).
notify          = true    # desktop notification (via notify-send) when the
                          # background daemon finds updates. No-ops quietly
                          # if notify-send isn't installed.

[categories]
# Add package name prefixes to override auto-classification
extra_critical = []
extra_optional = []

[ignore]
# Packages listed here are hidden from the update list entirely
packages = []

[snapshot]
enabled = true    # create a filesystem snapshot (snapper or timeshift, whichever
                  # is installed) before a full system upgrade. No-ops quietly if
                  # neither tool is installed.
backend = "auto"  # "auto" | "snapper" | "timeshift" | "none"

[profiles]
# Named groups of package-name patterns for the dashboard's [P] profile filter
# and for [automation] auto-update below. Patterns support * wildcards (fnmatch);
# a plain name is an exact match. Example:
#   browsers = ["firefox", "chromium", "*chrome*"]

[automation]
auto_update         = false  # if true, the background daemon non-interactively
                              # updates packages matching auto_update_profile on
                              # every scan. System/critical packages are never
                              # auto-updated, regardless of profile contents.
auto_update_profile = ""     # name of a [profiles] entry; ignored if empty or
                              # auto_update is false.
"""


@dataclass
class Config:
    aur_helper:          str            = "yay"
    check_interval:      int            = 4
    confirm:             bool           = False
    notify:              bool           = True
    extra_critical:      list[str]      = field(default_factory=list)
    extra_optional:      list[str]      = field(default_factory=list)
    ignored:             list[str]      = field(default_factory=list)
    snapshot_enabled:    bool           = True
    snapshot_backend:    str            = "auto"
    profiles:            dict[str, list[str]] = field(default_factory=dict)
    auto_update:         bool           = False
    auto_update_profile: str            = ""


def load_config() -> Config:
    if not CONFIG_FILE.exists():
        _write_default()
    raw  = tomllib.loads(CONFIG_FILE.read_text())
    g    = raw.get("general",    {})
    cat  = raw.get("categories", {})
    ign  = raw.get("ignore",     {})
    snap = raw.get("snapshot",   {})
    prof = raw.get("profiles",   {})
    auto = raw.get("automation", {})
    return Config(
        aur_helper          = g.get("aur_helper",     "yay"),
        check_interval      = g.get("check_interval", 4),
        confirm             = g.get("confirm",        False),
        notify              = g.get("notify",         True),
        extra_critical      = cat.get("extra_critical", []),
        extra_optional      = cat.get("extra_optional", []),
        ignored             = ign.get("packages",      []),
        snapshot_enabled    = snap.get("enabled", True),
        snapshot_backend    = snap.get("backend", "auto"),
        profiles            = {k: v for k, v in prof.items() if isinstance(v, list)},
        auto_update         = auto.get("auto_update", False),
        auto_update_profile = auto.get("auto_update_profile", ""),
    )


def _write_default() -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(DEFAULT_TOML)
