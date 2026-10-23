# Changelog

## 1.2.0 — 2026-10-23

- Select languages, menu actions and wizard choices with a mouse click in compatible terminals; click sidebar groups and use the wheel to navigate. Keyboard controls remain available.
- Restore mouse tracking on exit and enforce the same action prerequisites for clicks and keyboard selection.

- Add automatic location/node/allocation creation through Panel v2 contracts, with duplicate checks and local Wings configuration.
- Add isolated native game SQL, verified physical SQL restoration and game-file backup/restore.
- Add encrypted Restic backups, systemd scheduling, per-instance retention and snapshot download.
- Add persisted installation phases, a resume action and a health report that collects multiple findings.
- Add remote Wings and private game SQL provisioning over SSH with strict host-key verification.
- Add disposable QEMU integration runners and a manual Ubuntu/Debian deployment matrix.
- Fix native Artisan working directories discovered during the real deployment, and enforce secure session cookies for HTTPS URLs.

## 1.1.0 — 2026-10-23

- Replace the short interface demo with a complete in-memory installation preview, sharing production Panel and Wings connection forms.
- Add simulated maintenance, game database credentials, backups, restore, removal and scenario reset with contextual prerequisites.
- Identify preview mode throughout the TUI and animate simulated task stages. Support an automatic full text tour for redirected input.
- Prevent both launchers from installing missing Python in preview mode, even as root.
- Handle malformed state objects and nested credentials as invalid managed state instead of crashing.
- Reset the progress display to Wings installation phases when installing Panel and Wings together.
- Shorten the README and move detailed operations and preview instructions into dedicated guides.
- Expand regression coverage for simulation isolation, installation choices, lifecycle and terminal interaction.

Upstream Panel v2 remains beta. Complete deployment and public TLS require disposable VPS integration testing.
