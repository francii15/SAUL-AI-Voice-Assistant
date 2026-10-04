"""Install into an existing Orynth folder, with hashes and a recoverable backup.
Never copies .env, wake models or user output folders from the release package.
"""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
INSTALL_FILES = ('assistant.py', 'run_saul.py', 'verify_saul.py', 'test_regression.py',
                 'aura_float.png', 'aura_hero.png', 'saul.ico', 'Launch_Saul.vbs', 'Create_Saul_Shortcut.ps1', 'Start_Saul.cmd', 'saul_desktop.py', 'Start_Saul_Floating.cmd', 'Verify_Saul.cmd', 'LIVE_TEST.md', 'RELEASE_NOTES.md')

def checked_files(root):
    manifest = json.loads((root/'SHA256.json').read_text(encoding='utf-8'))
    for name, expected in manifest.items():
        if Path(name).name != name:
            raise ValueError('Invalid package path')
        actual = hashlib.sha256((root/name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError('Package checksum mismatch: '+name)
    if not set(INSTALL_FILES) <= set(manifest):
        raise ValueError('Incomplete package manifest')

def install(root, target):
    root, target = root.resolve(), target.resolve()
    if root == target:
        raise ValueError('Extract the release to a separate folder, not directly over Orynth.')
    checked_files(root)
    if not (target/'hey_saul.onnx').is_file():
        raise ValueError('The target needs your existing hey_saul.onnx. No replacement model is bundled.')
    target.mkdir(parents=True, exist_ok=True)
    backup = target/'backups'/datetime.now().strftime('pre-1.0.0-rc8_%Y%m%d_%H%M%S_%f')
    backup.mkdir(parents=True)
    names = list(INSTALL_FILES)+['python-path.txt']
    metadata = {'target':str(target), 'existing':[], 'created':[], 'installed_hashes':{}}
    for name in names:
        destination = target/name
        if destination.exists():
            shutil.copy2(destination, backup/name)
            metadata['existing'].append(name)
        else:
            metadata['created'].append(name)
    (backup/'backup.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    try:
        for name in INSTALL_FILES:
            shutil.copy2(root/name, target/name)
        (target/'python-path.txt').write_text(sys.executable+'\n', encoding='utf-8')
        metadata['installed_hashes'] = {name:hashlib.sha256((target/name).read_bytes()).hexdigest() for name in names}
        (backup/'backup.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    except Exception:
        for name in metadata['existing']:
            shutil.copy2(backup/name, target/name)
        for name in metadata['created']:
            (target/name).unlink(missing_ok=True)
        raise
    return backup

def rollback(backup):
    backup = backup.resolve()
    metadata = json.loads((backup/'backup.json').read_text(encoding='utf-8'))
    target = Path(metadata['target'])
    for name in metadata['existing']+metadata['created']:
        if Path(name).name != name:
            raise ValueError('Invalid backup path')
        path = target/name
        expected = metadata['installed_hashes'].get(name)
        if path.exists() and expected and hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('File changed since deployment; keep your edits before rolling back: '+name)
    for name in metadata['existing']:
        if not (backup/name).is_file(): raise ValueError('Backup is incomplete')
    for name in metadata['existing']:
        shutil.copy2(backup/name, target/name)
    for name in metadata['created']:
        (target/name).unlink(missing_ok=True)
    return target

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=Path, default=Path(r'C:\Orynth'))
    parser.add_argument('--rollback', type=Path)
    args = parser.parse_args()
    if os.name != 'nt' or sys.version_info[:2] != (3,11):
        print('Run from the Windows orynth environment with Python 3.11.')
        return 1
    try:
        if args.rollback:
            print('Restored:', rollback(args.rollback)); return 0
        checked_files(ROOT)
        subprocess.run([sys.executable, str(ROOT/'test_regression.py')], cwd=ROOT, check=True)
        backup = install(ROOT, args.target)
        print('Installed into:', args.target)
        print('Previous release backed up in:', backup)
        try:
            shortcut = subprocess.run(
                ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                 str(args.target/'Create_Saul_Shortcut.ps1'), '-InstallDirectory', str(args.target)],
                cwd=args.target, capture_output=True, text=True, timeout=25)
            if shortcut.returncode:
                raise RuntimeError(shortcut.stderr.strip() or shortcut.stdout.strip())
            print(shortcut.stdout.strip())
        except (OSError, subprocess.TimeoutExpired, RuntimeError) as shortcut_error:
            print('Desktop shortcut could not be created:', shortcut_error)
            print('Saul is installed; Start_Saul_Floating.cmd still launches it.')
        print('Next: launch Saul from its desktop shortcut, then check LIVE_TEST.md.')
        return 0
    except Exception as error:
        print('Deployment stopped:', error)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
