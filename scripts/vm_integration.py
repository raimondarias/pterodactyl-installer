#!/usr/bin/env python3
"""Boot an isolated cloud VM and run the real installer; intended for CI hosts."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tarfile
import tempfile
import time
import urllib.request

IMAGES = {
 'ubuntu-22.04': ('https://cloud-images.ubuntu.com/jammy/current/', 'jammy-server-cloudimg-amd64.img'),
 'ubuntu-24.04': ('https://cloud-images.ubuntu.com/noble/current/', 'noble-server-cloudimg-amd64.img'),
 'ubuntu-26.04': ('https://cloud-images.ubuntu.com/resolute/current/', 'resolute-server-cloudimg-amd64.img'),
 'debian-12': ('https://cloud.debian.org/images/cloud/bookworm/latest/', 'debian-12-genericcloud-amd64.qcow2'),
 'debian-13': ('https://cloud.debian.org/images/cloud/trixie/latest/', 'debian-13-genericcloud-amd64.qcow2'),
}


def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--os', choices=IMAGES, required=True)
 p.add_argument('--method', choices=('standalone','docker'), default='standalone')
 p.add_argument('--engine', choices=('mariadb','mysql'), default='mariadb')
 a=p.parse_args()
 root=Path(__file__).resolve().parents[1]
 with tempfile.TemporaryDirectory(prefix='ptero-ci-vm-') as temporary:
  work=Path(temporary);base,name=IMAGES[a.os]
  sums=urllib.request.urlopen(base+('SHA512SUMS' if a.os.startswith('debian') else 'SHA256SUMS'),timeout=60).read().decode()
  expected=next(line.split()[0] for line in sums.splitlines() if line.split()[-1].lstrip('*')==name)
  h=hashlib.sha512() if a.os.startswith('debian') else hashlib.sha256()
  with urllib.request.urlopen(base+name,timeout=120) as source,(work/'base.img').open('wb') as target:
   while chunk:=source.read(1024*1024):h.update(chunk);target.write(chunk)
  if h.hexdigest()!=expected:raise RuntimeError('Official cloud-image checksum mismatch')
  subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(work/'key')],check=True)
  key=(work/'key.pub').read_text().strip()
  (work/'user-data').write_text('#cloud-config\ndisable_root: false\nssh_pwauth: false\nusers:\n  - name: root\n    ssh_authorized_keys:\n      - '+key+'\n')
  (work/'meta-data').write_text('instance-id: ptero-integration\nlocal-hostname: ptero-integration\n')
  subprocess.run(['genisoimage','-quiet','-output',str(work/'seed.iso'),'-volid','cidata','-joliet','-rock',str(work/'user-data'),str(work/'meta-data')],check=True)
  subprocess.run(['qemu-img','create','-f','qcow2','-F','qcow2','-b',str(work/'base.img'),str(work/'disk.qcow2'),'24G'],check=True)
  with socket.socket() as probe:
   probe.bind(('127.0.0.1',22022))
  machine=subprocess.Popen(['qemu-system-x86_64','-enable-kvm','-cpu','host','-m','2560','-smp','2','-vga','none',
   '-drive',f'file={work}/disk.qcow2,if=virtio','-drive',f'file={work}/seed.iso,media=cdrom',
   '-netdev','user,id=net0,hostfwd=tcp:127.0.0.1:22022-:22','-device','virtio-net-pci,netdev=net0,romfile=',
   '-display','none','-serial',f'file:{work}/console.log'])
  ssh=['ssh','-i',str(work/'key'),'-p','22022','-o','StrictHostKeyChecking=accept-new','-o','UserKnownHostsFile='+str(work/'known_hosts'),'-o','ConnectTimeout=5','root@127.0.0.1']
  try:
   for attempt in range(90):
    if subprocess.run([*ssh,'true'],capture_output=True).returncode==0:break
    if machine.poll() is not None:raise RuntimeError('VM exited before SSH became ready')
    time.sleep(2)
   else:raise RuntimeError('VM SSH readiness timed out')
   # The host key is trusted only on this loopback port belonging to our own VM.
   ssh[ssh.index('StrictHostKeyChecking=accept-new')]='StrictHostKeyChecking=yes'
   with tarfile.open(work/'runtime.tar.gz','w:gz') as tar:
    for path in ('ptero','installer.py','tests/integration'):
     tar.add(root/path,arcname=path,filter=lambda m:None if '__pycache__' in m.name else m)
   with (work/'runtime.tar.gz').open('rb') as stream:
    subprocess.run([*ssh,'mkdir -p /root/ptero-ci && tar -xz -C /root/ptero-ci'],stdin=stream,check=True)
   if os.environ.get('PTERO_GITHUB_TOKEN'):
    subprocess.run([*ssh,'umask 077; cat > /root/.ptero-github-token'], input=os.environ['PTERO_GITHUB_TOKEN'].encode(), check=True)
   result=subprocess.run([*ssh,f'cd /root/ptero-ci && python3 tests/integration/deploy.py --disposable --method {a.method} --engine {a.engine} --cycle --full'],timeout=3000)
   (root/'test-results').mkdir(exist_ok=True)
   subprocess.run([*ssh,'cat /root/ptero-ci/test-results/integration-result.json'],stdout=(root/'test-results'/('integration-'+a.os+'-'+a.method+'-'+a.engine+'.json')).open('wb'),check=False)
   if result.returncode:
    subprocess.run([*ssh,'tail -160 /var/log/pterodactyl-installer/installer.log'],check=False)
    subprocess.run([*ssh,'journalctl -u wings -u ptero-game-sql-native --no-pager -n 60'],check=False)
    raise RuntimeError('Real VM deployment failed')
  finally:
   machine.terminate()
   try:machine.wait(timeout=20)
   except subprocess.TimeoutExpired:machine.kill();machine.wait()


if __name__=='__main__':main()
