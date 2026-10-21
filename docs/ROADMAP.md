# Recommended next work

These are proposals, not features already delivered. Prioritize recoverability
and a working first node before adding more cosmetic effects.

| Priority | Addition | Impact and acceptance criteria |
| --- | --- | --- |
| 1 | Automated game SQL restore and scheduled off-server backups | A guided restore verifies checksum, pinned engine/image, ownership and private networking. Back up Panel, game SQL and game files separately; restore all three on a second disposable host and prove existing game credentials still work. Report failure and retention clearly. |
| 2 | First-node setup | Collect location, node address, TLS, API/SFTP ports, memory, disk and allocation ranges. Create the node/allocations, link Wings and optionally create a test server through supported Panel contracts/APIs, with duplicate detection and an explicit resource review. |
| 3 | Clean-machine integration CI | Boot disposable Ubuntu/Debian VMs, exercise standalone/Docker and MariaDB/MySQL, reboot, renew test certificates, run a game and connect to its SQL database. Test blocked external SQL access, interrupted installs, restore, update failures and removal. Include ARM64 where supported. Command doubles alone cannot establish deployment reliability. |
| 4 | Native isolated game SQL backend | Offer a second native SQL instance with its own datadir/socket/service and restricted private routing, so a standalone Panel can also use native game SQL. Do not put the globally privileged game provisioning user in the Panel SQL instance. Test package/version differences and boot/firewall ordering first. |
| 5 | Health monitoring and resumable phases | Detect disk/memory pressure, queue/SQL/Redis failures, disconnected nodes and certificate expiry; give actionable diagnostics. Save completed installation phases and validate them before resume. Alerts require explicit destination configuration. |
| 6 | Remote-node database bootstrap over a private network | Prepare SQL on a node only after collecting and verifying remote access, private addresses and allowed sources. Register it in the Panel and test from a real game container. Keep management credentials separate from per-game accounts. |

Current limitations and the actual test evidence are in
[the verification report](../test-results/REPORT.md) and
[the clean-VPS procedure](TESTING.md).
