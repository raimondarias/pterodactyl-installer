# Verification report — 1.2.0

23 October 2026. Test results distinguish simulations, real deployment and external infrastructure.

| Coverage | Result |
| --- | --- |
| Regression suite | **205 passing tests**, including real PTYs, MariaDB socket lifecycle, PHP/NGINX parsers and encrypted Restic roundtrip |
| Static checks | Bash syntax, Python compilation and ShellCheck 0.11.0 passed |
| Languages | **740 messages** in English, Spanish and Brazilian Portuguese; placeholders and reproducible language packages verified |
| Download bootstrap | English first question; only selected language fetched from an immutable commit; checksum and safe extraction enforced |
| Public distribution | Real GitHub downloads and ncurses previews in all three languages; mouse selection, language switching and terminal restoration passed. [Exact snapshot and output](published-checks.txt) |
| Terminal interface | Keyboard, mouse, categories, search, masked inputs, invalid-input correction, resize, animated progress and cancellation tested in actual pseudoterminals |
| Preview isolation | All 33 actions and 96 Panel form combinations; en/es/pt-BR tours with subprocess, network and filesystem mutation APIs denied |
| Managed state | Missing/corrupt state, action prerequisites, persisted phase failure/resume, interrupted SQL setup and secret-free checkpoint records covered |
| SQL configuration | Single engine choice; both Panel backends; local/remote/deferred game SQL; credentials supplied through stdin and private files |
| Recovery | Checksums, safe extraction, empty destinations, original SQL version/image and network identity enforced; failed backups resume paused games |
| SSH | Strict host keys and batch key authentication; runtime checksum; credentials through encrypted stdin |
| Upstream artifacts | Panel v2.0.0-beta.2 and Wings v1.13.4 release artifacts verified; official amd64/arm64 image manifests checked |
| Fresh native-game-SQL matrix | **18/18 passed**, Ubuntu/Debian with both Panel methods and SQL engines; [immutable run and case records](ci-native-matrix.json) |
| Additional Docker-game-SQL matrix | **10/10 passed**, Ubuntu/Debian with Docker Panel and both SQL engines; [immutable run and case records](ci-docker-matrix.json) |

## Real deployment on installer.xerosrv.com

A dedicated Ubuntu 24.04 KVM guest runs behind a separate host NGINX virtual host. Existing host sites and databases are outside the guest. These checks executed real services:

- Standalone Panel with MariaDB, migrations, first administrator, PHP-FPM, Redis, queue and scheduler.
- Valid Let's Encrypt HTTPS, secure cookies and public application assets.
- Automatic location, node and eleven allocations through actual Panel v2 contracts.
- Wings deployment and configuration over verified SSH; HTTPS API rejects unauthenticated requests.
- Isolated native game SQL with a separate operating-system account, Panel host registration, physical backup and restoration of original table data.
- Private SQL provisioning over verified SSH with an explicit source allowlist, followed by Panel registration.
- Docker Panel with MySQL, its authentication client, schema loading, administrator and container health.
- Docker Wings with healthy API authentication and preservation of the running game, followed by restoration of the standalone daemon.
- Docker game SQL with both MariaDB and MySQL: private account provisioning, original table data after physical restore and supervision held stopped until data copying completes.
- A real Minetest server created through Panel contracts, started by Wings and listening on its game allocation; game-file restore preserves content and ownership, and the game starts again.
- Encrypted scheduled systemd backup into a local Restic repository, snapshot download and archive checksum verification.
- A separate encrypted SFTP repository roundtrip over verified SSH to the isolated guest.
- Panel service restart, same-release update redeployment, purge and restore preserving APP_KEY and HASHIDS_SALT.
- Guest reboot with a changed boot ID, managed services returning and public HTTPS responding again.

[Structured deployment record](integration-domain.json). Test credentials remain in a private file on the server and are excluded from this repository.

## Fresh-system matrix and limits

The manually triggered [deployment workflow](https://github.com/raimondarias/pterodactyl-installer/actions/workflows/tests.yml) boots disposable official cloud images and performs install, restart, update redeployment, purge, restore, node linking, game SQL restoration and a real game smoke test. It covers 18 Ubuntu/Debian × deployment × SQL combinations. All **18 cases passed** in [run 40054262242](https://github.com/raimondarias/pterodactyl-installer/actions/runs/40054262242), using native game SQL and standalone Wings. [Exact source commit, image checksums and results](ci-native-matrix.json).

An additional **10 Docker Panel + Docker game-SQL cases passed** in [run 40057444433](https://github.com/raimondarias/pterodactyl-installer/actions/runs/40057444433) after the Docker provisioning/readiness/restore fixes. [Exact source commit, image checksums and results](ci-docker-matrix.json). These cases cover both engines on all five distributions. Docker Wings was exercised separately in the domain lab. The final regression run on this runtime commit also [passed](https://github.com/raimondarias/pterodactyl-installer/actions/runs/40057444721).

Ubuntu 26.04 native installation needs a preconfigured PHP 8.3/8.4 source; the tested PHP repository does not currently publish that distribution. The installer detects this before package changes. Fresh Ubuntu 26.04 matrix jobs therefore use Docker.

External S3 and independent SFTP providers, remote VPS routing and external SMTP delivery were not exercised: the user selected isolated local environments. ARM64 image availability was verified; execution uses amd64. Same-release redeployment checks the update mechanism; it does not prove compatibility with an unreleased future Panel schema.

[Local test output](local-tests.txt) · [Test procedure](../docs/TESTING.md) · [Advanced operations](../docs/ADVANCED.md).
