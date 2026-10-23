# Implementation status and next validation

The 1.2.0 implementation adds all seven agreed areas: disposable integration tooling, automatic first-node creation, encrypted scheduled backups and guided restores, persisted resume phases, expanded health checks, isolated native game SQL and verified SSH provisioning of remote nodes/SQL. See [advanced operations](ADVANCED.md) for their contracts and limits.

Remaining validation and expansion:

1. Complete the full Ubuntu/Debian × standalone/Docker × MariaDB/MySQL integration matrix, including ARM64 runners. Keep failures visible and attach only redacted artifacts.
2. Test S3 and SFTP against independent off-server infrastructure; current encrypted repository roundtrips use isolated local storage.
3. Test remote routing and firewall behavior between independent VPSes. Local SSH/VM tests do not prove provider networking.
4. Add guided game-file restore for custom Wings daemon paths and more granular per-server backup selection.
5. Add configured notification destinations for failed backups and health checks.
6. Expand recovery from saved installation phases into explicit guided update rollback, with schema-compatible backup restoration.

[Verification report](../test-results/REPORT.md) · [Testing procedure](TESTING.md).
