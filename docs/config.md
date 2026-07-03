# Config reference

ArchBooster reads `~/.config/archbooster/config.toml`, creating it with the
defaults below on first run (`archbooster/core/config.py`).

## `[general]`

| Key | Default | Meaning |
|---|---|---|
| `aur_helper` | `"yay"` | Which AUR helper to shell out to: `"yay"` or `"paru"`. Ignored if neither is installed — the pacman backend just reports itself unavailable. |
| `check_interval` | `4` | Hours between background daemon scans, consumed by the systemd timer. |
| `confirm` | `false` | `false`: pacman/yay/flatpak run non-interactively (your checkbox selection in the TUI *is* the confirmation, so `--noconfirm`/`-y` is appended). `true`: the package manager's own prompt is shown too — useful when running from a plain terminal instead of the TUI. |
| `notify` | `true` | Whether the background daemon fires a desktop notification (via `notify-send`) when it finds updates. If `notify-send` isn't installed, this silently no-ops regardless of the setting. |

## `[categories]`

| Key | Default | Meaning |
|---|---|---|
| `extra_critical` | `[]` | Extra package name prefixes to force into the "critical" (system-layer, guardrail-locked) category, on top of the built-in list (kernel, mesa, nvidia, glibc, systemd, ...). |
| `extra_optional` | `[]` | Extra package name prefixes to force into "optional" (fonts, themes, ...), on top of the built-in list. |

Both are matched with the same rule as the built-ins: exact match or
`name.startswith(prefix)`. Anything not matched by either list is "normal".

## `[ignore]`

| Key | Default | Meaning |
|---|---|---|
| `packages` | `[]` | Package names hidden from the update list entirely — filtered out before categorization, so they never show up in the TUI, `--scan`, or the daemon's notification count. |

## Notes

- `extra_critical` entries are the only user-facing way to widen the
  app-vs-system guardrail (`categorizer.is_system`) — add a prefix there if a
  package you consider system-critical isn't caught by the built-in list.
- Backend-specific settings (e.g. per-Flatpak-remote config) don't exist yet;
  Flatpak updates are driven entirely by whatever remotes `flatpak` itself
  already has configured.
