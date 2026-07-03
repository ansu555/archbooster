## What does this change?

<!-- One or two sentences. If it's a new backend, name it. If it's a bug fix,
     describe the wrong behavior and the fix. -->

## Why

<!-- What prompted this — a bug you hit, a distro you use, a gap you found.
     See CONTRIBUTING.md for what's actually in scope right now. -->

## Testing

<!-- How did you verify this? For backend changes, mocked CLI output is
     expected (see tests/test_apt.py or tests/test_dnf.py for the pattern) —
     note if you also tested against a real install. -->

- [ ] `pytest -q` passes locally
- [ ] Added/updated tests for the behavior change
- [ ] Live-tested against a real install (if applicable) — describe:

## Checklist

- [ ] PR is scoped to one change (not bundled with unrelated fixes)
- [ ] Docstrings/comments explain non-obvious *why*, not just *what*
