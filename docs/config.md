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

## `[update]`

| Key | Default | Meaning |
|---|---|---|
| `default_scope` | `"safe"` | Scope of the one-command app update (`archbooster --update`, overridable per-run with `--scope`). `"safe"`: everything except the system layer — libraries ride along with the apps that need them, which is what keeps native packages from breaking. `"apps"`: user-facing apps only (packages shipping a `.desktop` launcher, plus every Flatpak/Snap app); stricter, but a native app whose update requires a newer library makes pacman stop with a dependency error rather than partially upgrade. Unrecognized values fall back to `"safe"`. |

Either way, the system layer (kernel, drivers, firmware, bootloader, core
libs) is **always** held back via `--ignore` — updating it takes an explicit
full upgrade (`[F]` in the TUI).

## `[snapshot]`

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `true` | Create a filesystem snapshot before a full system upgrade (`[F]` in the dashboard) **and** before the native pass of an app update (which is a real `-Syu --ignore=…` sync, so libraries do move), so a broken run has a rollback point. No-ops quietly if no snapshot tool is installed — this is a safety bonus, not a hard requirement. |
| `backend` | `"auto"` | Which tool to use: `"auto"` (snapper first, then timeshift), `"snapper"`, `"timeshift"`, or `"none"` to disable regardless of `enabled`. |

Rolling back to a snapshot is done from the dashboard: press `[B]` (app-level)
to open the Snapshots screen, `[R]` to arm a rollback for the highlighted
snapshot, then `[Y]` to confirm — any other key cancels the arm instead of
doing whatever it would normally do, so a rollback is never one accidental
keystroke away.

## `[profiles]`

Named groups of package-name patterns, used by the dashboard's `[P]` filter
and by `[automation]` auto-update below. A plain name is an exact match; `*`
makes it a wildcard (prefix/suffix/substring).

```toml
[profiles]
browsers = ["firefox", "chromium", "*chrome*"]
editors  = ["code", "cursor-bin", "*vim*"]
```

Pressing `[P]` in the dashboard cycles through these, each time
auto-selecting only the rows the active profile matches (never a locked
system row) so `[ENTER]` updates just that group. Cycling past the last
profile clears the filter back to "everything selected".

## `[automation]`

| Key | Default | Meaning |
|---|---|---|
| `auto_update` | `false` | If true, the background daemon non-interactively updates packages matching `auto_update_profile` on every scan — opt-in, off by default. |
| `auto_update_profile` | `""` | Name of a `[profiles]` entry to auto-update. Ignored if empty or `auto_update` is false. |

System/critical packages are **never** auto-updated, even if a profile's
patterns would technically match one (e.g. a `"*"` catch-all profile) — the
daemon enforces the app/system guardrail a second time on this path since it
runs unattended. Every auto-update run is logged to history, and mentioned by
name in the desktop notification, so it's never silent.

## Notes

- `extra_critical` entries are the only user-facing way to widen the
  app-vs-system guardrail (`categorizer.is_system`) — add a prefix there if a
  package you consider system-critical isn't caught by the built-in list.
- apt and dnf get their own built-in critical-package lists
  (`categorizer.APT_CRITICAL_PATTERNS` / `DNF_CRITICAL_PATTERNS`), since
  Debian/Fedora package names don't match Arch's (`linux-image-*` vs
  `linux`, `libc6` vs `glibc`, ...). `extra_critical` extends whichever list
  applies to a given package's backend.
- Flatpak, Snap, and Homebrew have no system layer at all, so packages from
  those backends never classify as "critical" regardless of name — this
  matters in practice for Homebrew, whose flat formula names (e.g.
  `openssl`) can otherwise collide with an Arch-shaped critical pattern.
- Backend-specific settings (e.g. per-Flatpak-remote config) don't exist yet;
  Flatpak updates are driven entirely by whatever remotes `flatpak` itself
  already has configured.
