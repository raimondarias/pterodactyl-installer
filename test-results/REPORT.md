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
| Retention | Only scheduler-owned Panel/Wings copies are pruned; manual copies and legacy game archives remain untouched |
| Preview | All current actions simulated in memory; filesystem mutations, subprocess and network APIs denied; real keyboard/mouse/animation/cancellation checked |

## Real isolated-domain check

The existing Ubuntu 24.04 KVM lab at [installer.xerosrv.com](https://installer.xerosrv.com) executed the new runtime. An old profile with game-inclusion flags was migrated, then the persistent systemd backup service uploaded an encrypted Panel/Wings-only bundle to Restic. Download and Panel archive inspection passed. A temporary real Minetest container kept the same running/paused/PID values, the native game SQL service kept its PID, and Wings configuration bytes stayed unchanged. The temporary test container was removed afterward.

[Structured scope result](1.2.1-domain-scope.json). Credentials remain private on the test server.

## Fresh-system deployment checks

Current 1.2.1 integration scenarios install Panel/Wings, provision a game SQL host, start a real game and verify Panel/Wings configuration backups without changing the game or its SQL data. They also exercise Panel restart, same-release redeployment, purge and restore with the original application keys. Completed current-version run records are added separately from the regression suite.

The [1.2.0 verification report](https://github.com/raimondarias/pterodactyl-installer/blob/v1.2.0/test-results/REPORT.md) and its 18 native-game-SQL / 10 Docker-game-SQL case records are historical coverage. That release included game-data backup/restore functions removed in 1.2.1; those records do not describe the current backup scope.

Ubuntu 26.04 native installation requires a preconfigured PHP 8.3/8.4 source; fresh-system CI uses Docker there. ARM64 execution, independent external S3/SFTP providers, independent VPS routing and external SMTP delivery remain untested. Actual encrypted repository and SSH tests use isolated local infrastructure.

[Local test output](local-tests.txt) · [Test procedure](../docs/TESTING.md) · [Operations and backup scope](../docs/ADVANCED.md).
