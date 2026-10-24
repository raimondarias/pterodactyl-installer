# Verification report — 1.2.1

24 October 2026. This version limits installer backups to **Panel and Wings configuration**. Hosted-server files, worlds and game SQL are outside the installer backup/restore scope. The Panel application database remains part of a Panel backup.

| Coverage | Result |
| --- | --- |
| Regression suite | **227 passing tests**, including real pseudoterminals, PHP/NGINX validation, SQL provisioning and an encrypted Restic roundtrip |
| Static checks | Bash syntax, Python compilation and ShellCheck passed |
| Languages | **777 messages**, English / Spanish / Brazilian Portuguese; field parity and reproducible language packages checked |
| Navigation | Implemented actions remain selectable with keyboard/mouse; missing requirements are explained and eligible actions offer explicit setup before retry |
| Removal | A missing component never triggers an installation offer when removal is selected |
| Fresh/broken state | Read-only host diagnosis works before installation; corrupt, foreign and unmanaged components are reported individually |
| Backup scope | Removed game-file and game-SQL backup/restore APIs, menu entries and preview workflows; Panel archive paths are allowlisted |
| Scheduled copies | Panel and/or installed Wings configuration, including Wings-only hosts; game containers and game SQL are never paused/stopped for a backup |
| Legacy profiles | Old game flags discarded with notice; private scheduled runtime replaced; mixed legacy snapshots rejected before download |
| Fresh systems | **4/4 passed**, Ubuntu 24.04 standalone/Docker × MariaDB/MySQL; [exact commit, official image checksum and case records](1.2.1-ci-matrix.json) |
| Public distribution | Actual GitHub downloads in all three languages, mouse navigation, language switching and terminal restoration passed; [exact tested commit](published-checks.txt) |
| Retention | Only scheduler-owned Panel/Wings copies are pruned; manual copies and legacy game archives remain untouched |
| Preview | All current actions simulated in memory; filesystem mutations, subprocess and network APIs denied; real keyboard/mouse/animation/cancellation checked |

## Real isolated-domain check

The temporary Ubuntu 24.04 KVM lab previously served at `installer.xerosrv.com` executed the new runtime. An old profile with game-inclusion flags was migrated, then the persistent systemd backup service uploaded an encrypted Panel/Wings-only bundle to Restic. Download and Panel archive inspection passed. A temporary real Minetest container kept the same running/paused/PID values, the native game SQL service kept its PID, and Wings configuration bytes stayed unchanged. The temporary test container was removed afterward.

[Structured scope result](1.2.1-domain-scope.json). The lab was retired on 24 October 2026 at the owner's request: its VM disk, credentials, certificates, dedicated services and domain proxy were deleted. The deployment results above are historical; no live demo remains.

## Fresh-system deployment checks

Current 1.2.1 integration scenarios install Panel/Wings, provision a game SQL host, start a real game and verify Panel/Wings configuration backups without changing the game or its SQL data. They also exercise Panel restart, same-release redeployment, purge and restore with the original application keys. All four Ubuntu 24.04 standalone/Docker × MariaDB/MySQL cases **passed** in [run 40100271996](https://github.com/raimondarias/pterodactyl-installer/actions/runs/40100271996). Each used the current Panel/Wings-only backup scope. [Structured records](1.2.1-ci-matrix.json) identify the exact runtime commit and official guest image checksum. The regression job in the same run also passed.

The [1.2.0 verification report](https://github.com/raimondarias/pterodactyl-installer/blob/v1.2.0/test-results/REPORT.md) and its 18 native-game-SQL / 10 Docker-game-SQL case records are historical coverage. That release included game-data backup/restore functions removed in 1.2.1; those records do not describe the current backup scope.

Ubuntu 26.04 native installation requires a preconfigured PHP 8.3/8.4 source; fresh-system CI uses Docker there. ARM64 execution, independent external S3/SFTP providers, independent VPS routing and external SMTP delivery remain untested. Actual encrypted repository and SSH tests use isolated local infrastructure.

[Local test output](local-tests.txt) · [Test procedure](../docs/TESTING.md) · [Operations and backup scope](../docs/ADVANCED.md).
