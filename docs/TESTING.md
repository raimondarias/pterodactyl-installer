# Verification scope and clean-VPS procedure

Local tests use Python's standard-library unittest, temporary filesystem roots and recorded/failing doubles of APT, Docker, PHP and systemd. They do not install services on the test host.

Covered behavior includes:

- English-first online startup question, followed by downloads from only the selected `languages/en`, `languages/es` or `languages/pt-BR` directory.
- Real Bash bootstrap execution with recorded GitHub transport fixtures, immutable commit selection, archive verification/safe extraction and all-language preview.
- Reproducible single-language packages, committed-package freshness, menu language fetch/cache and unchanged active language on failed verification.
- Actual ncurses sessions in PTYs: menu groups, unavailable-action explanations, fresh-machine diagnostics, arrow-driven bootstrap, hidden fields, animation, resize and terminal echo/canonical restoration after exit/Ctrl+C.
- Read-only inventory and corrupt-state handling; direct commands and numeric fallback refuse missing prerequisites before loading nonexistent state.
- Explicit `--plain` and `TERM=dumb` fallback; generated credentials and installation reviews require acknowledgement before proceeding.
- Three startup languages, English default, complete catalogue field parity and translated confirmations.
- Simple setup matrix: Docker/standalone × MariaDB/MySQL × domain/public IPv4 × three languages.
- Advanced PHP, bind-address and timezone settings; passwords passed through stdin and omitted from state/argv.
- Package/repository selection for Ubuntu 22.04/24.04/26.04 and Debian 12/13; refusal to replace a different installed DB engine.
- One database-engine choice reused by game SQL; custom credentials, private report, retry and ownership checks.
- Independent local game SQL Compose configuration, firewall-before-start and rejection of an unsupported firewall backend.
- Real disposable MariaDB game database/account/privilege lifecycle, including quotes, backslashes and dollars in provisioning passwords. This instance has no TCP listener and changes no system service.
- Consistent physical game SQL backups, restart on backup failure, and game SQL/report retention after Panel purge.
- Docker MySQL environment/healthcheck/backup commands and MariaDB compatibility.
- Native environment key preservation, dedicated Redis/FPM/worker/timer generation, SQL collision checks and migration ordering.
- SQL, original keys, storage, extensions, Redis, file modes, owners and certificate links in backup/restore tests.
- Corrupt downloads, empty dumps, failed migrations/imports, failed certificate issuance and recovery paths.
- Separate Wings container project with host networking, required host paths, distroless-compatible healthcheck and image/config rollback.
- Removal confined to managed resources, preserving game files and avoiding global prune/volume deletion.
- Menu navigation, invalid/closed input, pseudoterminal animation, all-language no-root preview and the single-file launcher.
- Real `docker compose config` validation where the Docker CLI is available.
- Real `nginx -t` validation for HTTP, HTTPS and maintenance configs, with a temporary self-signed test certificate where NGINX/OpenSSL are available.

`tests/live_check.py` also checks GitHub releases, downloads and hashes the real Wings binary, executes its version/configure commands against a local mock API, downloads/hashes/extracts the real Panel archive and verifies official Panel/Wings OCI manifests for amd64/arm64. It does not run Panel/Wings services or execute an ARM64 binary on an amd64 host.

Run:

```bash
bash tests/run.sh
bash tests/run.sh --live
```

The online distribution test doubles only GitHub transport; it executes the actual Bash bootstrap, safe extraction and selected Python runtime. Missing packages, checksum mismatch, wrong-language archives, traversal, links/devices and duplicate paths are rejected before runtime execution. After publishing, run the online `--preview` path in all three languages as described in [UPLOAD.md](UPLOAD.md).

Optional checks are explicitly skipped if the corresponding client binary is absent. ShellCheck is used if installed; Bash syntax is always checked. The current verification also ran a separately downloaded official ShellCheck binary in a temporary directory, with the GitHub asset hash verified.

## Preview isolation

The simulator reuses the real Panel and Wings connection forms, but has no service runner or deployment paths. Tests deny subprocess execution, network sockets, HTTP requests and filesystem writes while completing the tour in every language. A 96-combination form matrix exercises simple/advanced, standalone/Docker, MariaDB/MySQL, IP/domain and local/existing/deferred game SQL. Both Bash launchers are tested with Python absent and a tripwire APT executable, including root execution.

An additional real PTY walkthrough enters an invalid domain, corrects it, completes the administrator form, types the install confirmation, observes multiple animated frames, returns to the preview overview and checks terminal restoration. The full simulated lifecycle covers all 22 menu actions, separate SQL retention and restore prerequisites.

## Full deployment: still required

Use disposable VPSes with systemd and working Docker, plus real DNS names and an SMTP test account. Automated command simulations and upstream artifact validation do not establish that every package/service/network combination works end to end.

1. Test each supported Ubuntu/Debian version, first with the recommended standalone + MariaDB path, then Docker MariaDB, native MySQL on supported architecture and Docker MySQL.
2. Test both public IPv4/HTTP and domain/HTTPS paths in English, Spanish and Brazilian Portuguese. Verify the correct URL, administrator login and hidden input.
3. Confirm migrations complete before the Panel serves traffic. Check FPM, private Redis, queue and scheduler in standalone; check official healthchecks in Docker.
4. Create a location/node/allocations, issue the node certificate and link Wings. Test both the systemd daemon and the optional container.
5. Start a real game using a CPU-compatible egg, connect to its allocation, inspect the console and exercise SFTP.
6. Send a password recovery email and run a scheduled task.
7. Make a backup, restore to a second empty host with the same deployment/DB method and original application keys, and verify login/node access.
8. Exercise an actual compatible release update and a forced migration failure with recovery from backup.
9. Test certificate renewal dry-runs. Standalone Panel uses its dedicated Certbot configuration directory; Wings uses host Certbot. Verify reload/restart hooks for its selected backend.
10. Uninstall while retaining data, reactivate it, then test purge after a successful backup. Confirm unrelated services and all game data remain.
11. Exercise local game SQL with both engines and both Panel methods. Confirm automatic registration, per-server limits, game-container access via the private gateway and rejection of SQL from an external interface, including routed private addresses. Reboot and restart Docker; verify firewall persistence before accepting deployment. Check a remote prepared host and a node with a custom bridge.
12. Back up game SQL independently, verify checksum and restore manually on an isolated second host with the original image/network and Panel backup. Confirm existing game credentials still work. Exercise read-only/full disk, backup restart failure and an interrupted initialization.
13. Repeat on ARM64 with supported database packages and game images.

The creation environment has a Docker CLI but no available Docker daemon. Only the temporary MariaDB socket instance is executed locally. No full native package deployment, public DNS/TLS issuance, SMTP delivery or game-server run has been performed there. The verification report identifies those limits explicitly.

## Disposable cloud-image matrix

`python3 scripts/vm_integration.py --os ubuntu-24.04 --method standalone --engine mariadb` downloads an official image, verifies its checksum, boots a private QEMU/KVM guest, waits for root SSH, uploads the runtime and runs the real deployment/restart/update/purge/restore scenario. The script terminates its VM afterward. It supports Ubuntu 22.04/24.04/26.04 and Debian 12/13 with both engines and deployment methods. Run this coordinator on an otherwise unused CI machine with QEMU, genisoimage and KVM; loopback port 22022 must be free.

The workflow in `.github/workflows/tests.yml` runs regressions on push/PR and provides the full deployment matrix through manual dispatch. A configured matrix is not a claim that every combination has passed; actual completed runs and the local domain test are recorded separately.

Ubuntu 26.04 is covered by Docker integration. Fresh standalone setup needs a separately configured PHP 8.3/8.4 package source: the tested Ondřej PPA currently has no resolute Release index. The installer stops before package changes when that prerequisite is missing. The automated fresh-VM matrix excludes those two unavailable native cases.
