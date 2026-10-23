# Verification report — Ptero Installer 1.1.0

Date: 23 October 2026.

| Check | Result |
| --- | --- |
| Local unittest suite | **170 tests passed**, no failures or skips in this environment |
| Guided simple setup matrix | Both Panel methods × both database engines × IP/domain × all three languages |
| Language catalogue | 568 messages with complete en/es/pt-BR entries and matching placeholders |
| Bash syntax / Python compilation | Passed |
| Online language bootstrap | Real Bash + Python runtime with GitHub transport fixtures: English first question, only selected folder, one language question, immutable commit and clean temporary-directory removal |
| Download rejection | Missing packages, wrong language, bad checksum, traversal, absolute paths, links, devices and duplicate archive entries rejected |
| Language distributions | Three reproducible packages with one locale each; committed bytes match the shared runtime and translation tables |
| Menu language change | Only the requested locale fetched; checksum/snapshot enforced; existing locale retained on failure |
| Published GitHub distribution | **Passed** against `173926847ac9a13022e5eea87647c989373dede1`: actual downloads, full-screen picker and ncurses preview in en/es/pt-BR, clean terminal restoration and verified language changes |
| Full-screen TUI | Passed with actual ncurses PTYs: arrows, categories, numeric shortcuts, search, masked forms, resize, busy animation and terminal restoration |
| Prerequisites and fresh machine | Option 20 is blocked with an installation hint; option 14 gives machine information and next steps; corrupt state is reported without overwriting it |
| Plan/password review | Review and generated credentials require acknowledgement before continuing |
| Interactive animation | Multiple actual ncurses activity frames captured in a real pseudoterminal; reduced-motion/plain fallbacks checked |
| TUI screenshots | Captured from actual ncurses buffers; SVG render visually reviewed |
| Full preview | All 22 simulated actions; 96 Panel form combinations; en/es/pt-BR tours with subprocess, HTTP/socket and filesystem mutation APIs denied |
| Preview bootstrap | Both launchers refuse to install missing Python in preview mode, including root; APT tripwire remains untouched |
| Interactive preview | Real PTY: invalid-domain correction, masked administrator password, typed confirmation, animated deployment, dashboard return and terminal restoration |
| Corrupt state shape | Lists, scalars and malformed nested credentials reported as invalid without overwriting them |
| Single-file launcher | Built, payload checksum verified, extracted and executed `--version` successfully |
| Real Compose parser | Passed for MariaDB Panel, MySQL Panel, both game SQL engines and Docker Wings |
| Game SQL setup | One engine selection, both Panel backends, local/remote/skip, custom credentials, private report, ownership checks and retry |
| Real game SQL lifecycle | Disposable MariaDB socket server: provisioning user, per-game database/user, grants, queries and deletion; special password characters preserved |
| Game SQL startup/removal | Generated firewall ordered before SQL, systemd-only supervision, unsupported backend refusal, unhealthy startup stops, Panel purge preserves SQL and report |
| Game SQL backup | Physical data/credentials archive + checksum, restart after success/failure |
| PHP syntax / credential rendering | Real PHP parser accepted registration code; passwords remain exact in translated UI |
| Real NGINX syntax | Passed HTTP, HTTPS and maintenance configurations with temporary test files |
| OS/package selection | Simulated Ubuntu 22.04/24.04/26.04 and Debian 12/13, both engines |
| Official Panel release | v2.0.0-beta.2 verified through GitHub API |
| Official Wings release | v1.13.4 verified through GitHub API |
| Real Wings amd64 binary | Downloaded, official SHA-256 verified, version command executed |
| Real Wings configuration | Accepted installer JSON/YAML against a temporary local mock API |
| Real Panel archive | Downloaded, official SHA-256 verified, safely extracted, expected files checked |
| Official OCI images | Panel and Wings manifests checked for amd64 and arm64 |
| Repository endpoints | MariaDB 11.4 Ubuntu jammy and MySQL 8.4 Debian trixie amd64 indexes reachable on 21 October 2026 |
| ShellCheck | **Passed**, v0.11.0 official binary downloaded into a temporary directory and verified using GitHub asset SHA-256; not installed system-wide |
| Complete deployment | **Not performed:** no available Docker daemon; no clean native package deployment |
| Public DNS/TLS, SMTP and game server | **Not performed:** requires disposable VPSes and real domains/accounts |

Package and system-service operations are simulated in the local suite. The game SQL integration test starts only a disposable MariaDB process with a private temporary Unix socket, no TCP listener, and terminates it before cleanup. MySQL service execution and full Laravel host registration are not validated end to end. The real NGINX test only validates configuration; it does not start or reload the host service. Remote checks execute Wings only for version/configure, use temporary files, and never start its daemon or the Panel. ARM64 availability was checked in OCI manifests; its binaries were not executed on this amd64 host.

Game SQL firewall forwarding, boot/Docker restart ordering and full cross-host physical restore still require the clean-VPS procedure. The host registration tests record commands and validate PHP syntax; they do not substitute for an actual Panel installation.

Local distribution tests use GitHub transport fixtures, including an actual PTY bootstrap that chooses Spanish with an arrow and opens the selected ncurses runtime. `python3 tests/published_check.py` additionally checks actual public downloads, ncurses previews in all three languages, terminal restoration and verified language changes after publication. The recorded [published output](published-checks.txt) identifies the exact snapshot checked. Complete service deployment on a clean VPS remains untested.

See [ShellCheck output](shellcheck.txt), [local output](local-tests.txt), [test procedure](../docs/TESTING.md), and [UI previews](../docs/preview-en.txt).

Upstream releases, binaries, archive and OCI manifests were rechecked on 23 October 2026 for this release. The repository endpoint checks in the table were last performed on 21 October 2026. The published-distribution log identifies the exact public snapshot tested; it is updated after pushing the release code.
