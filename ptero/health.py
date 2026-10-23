"""Read-only checks with per-component findings; one failure never hides the rest."""
import json
import shutil
import socket
import ssl
import time
import urllib.parse
import urllib.request
from .core import InstallerError


def inspect(i):
    rows = []
    def check(label, operation, remedy):
        try:
            result = operation()
            if result is False:
                raise InstallerError(remedy)
            rows.append(i.ui.tr('Healthy: {value}').format(value=i.ui.tr(label)))
        except (InstallerError, OSError, ValueError, KeyError, ssl.SSLError):
            rows.append(i.ui.tr('Needs attention: {value}').format(value=i.ui.tr(label)) + ' · ' + i.ui.tr(remedy))
    check('Disk space', lambda: shutil.disk_usage(i.p.root).free >= 4 * 1024**3, 'Free at least 4 GiB and move backups off this disk.')
    meminfo = i.p.root / 'proc/meminfo'
    if meminfo.exists():
        values = {line.split(':')[0]: int(line.split()[1]) for line in meminfo.read_text().splitlines() if ':' in line and len(line.split()) > 1 and line.split()[1].isdigit()}
        check('Available memory', lambda: values.get('MemAvailable', 0) >= 256 * 1024, 'Free memory before starting more game servers.')
    if i.p.state.exists():
        state = i.panel_state()
        if state.get('method') == 'standalone':
            backend = i.native(state)
            for unit in (backend.db_unit, backend.redis_unit, backend.queue, backend.scheduler, 'php' + state.get('php', '8.3') + '-fpm', 'nginx'):
                check(unit, lambda unit=unit: i.run.run(['systemctl', 'is-active', '--quiet', unit])[0] == 0, 'Inspect this service with systemctl status and journalctl.')
            check('Panel SQL and migrations', lambda: backend.artisan('migrate:status', '--no-interaction'), 'Check SQL credentials and finish pending migrations.')
            check('Queue failures', lambda: 'No failed jobs' in backend.artisan('queue:failed', '--no-interaction')[1], 'Inspect failed queue jobs before retrying them.')
        else:
            def containers():
                _, text = i.dc('ps', '--format', 'json')
                values = json.loads(text) if text.strip().startswith('[') else [json.loads(line) for line in text.splitlines() if line.strip()]
                return {'panel', 'database', 'cache'}.issubset({v.get('Service') for v in values}) and all(v.get('State') == 'running' and v.get('Health') == 'healthy' for v in values)
            check('Panel containers', containers, 'Inspect Docker Compose logs and container healthchecks.')
        def http():
            request = urllib.request.Request(state['url'], headers={'User-Agent': 'ptero-health'})
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status in (200, 301, 302, 303)
        check('Panel HTTP endpoint', http, 'Check the web server, DNS and application logs.')
        if state['url'].startswith('https://'):
            parsed = urllib.parse.urlsplit(state['url'])
            def expiry():
                with socket.create_connection((parsed.hostname, parsed.port or 443), timeout=10) as connection:
                    with ssl.create_default_context().wrap_socket(connection, server_hostname=parsed.hostname) as tls:
                        cert = tls.getpeercert()
                return ssl.cert_time_to_seconds(cert['notAfter']) - time.time() > 14 * 86400
            check('TLS certificate lifetime', expiry, 'Renew the certificate; fewer than 14 days remain or verification failed.')
    if i.p.wings_state.exists():
        state = i.load(i.p.wings_state)
        if state.get('status') != 'ready':
            rows.append(i.ui.tr('Wings is installed but still needs node configuration.'))
        elif state.get('method') == 'docker':
            from .wings import DockerWings
            check('Wings', lambda: DockerWings(i, state).health(), 'Inspect Wings logs and verify the Panel connection.')
        else:
            check('Wings', lambda: i.run.run(['systemctl', 'is-active', '--quiet', 'wings'])[0] == 0, 'Inspect Wings logs and verify the Panel connection.')
    for path in (i.p.state, i.p.wings_state):
        if path.exists():
            state = i.load(path)
            for name, phase in state.get('phases', {}).items():
                if phase.get('status') in ('running', 'failed'):
                    rows.append(i.ui.tr('Interrupted phase: {value}').format(value=i.ui.tr(name)))
    if (i.p.base / 'backup-profile.json').exists():
        check('Backup timer', lambda: i.run.run(['systemctl', 'is-active', '--quiet', 'ptero-backup.timer'])[0] == 0, 'Enable ptero-backup.timer and inspect the last backup service result.')
        check('Last scheduled backup', lambda: i.run.run(['systemctl', 'show', 'ptero-backup.service', '--property=Result', '--value'])[1].strip() == 'success', 'Inspect journalctl -u ptero-backup.service before trusting scheduled copies.')
    i.ui.card('Health report', rows)
    return rows
