"""Build a versioned, self-contained desktop download using PyInstaller."""

import argparse
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from netmonitor_core import APP_VERSION


def checked_version(expected=None):
    if not re.fullmatch(r"\d+\.\d+\.\d+", APP_VERSION):
        raise ValueError("APP_VERSION must be major.minor.patch")
    if expected and expected.removeprefix("v") != APP_VERSION:
        raise ValueError(f"Tag {expected} does not match APP_VERSION {APP_VERSION}")
    return APP_VERSION


def windows_version_file(path):
    parts = tuple(map(int, checked_version().split('.'))) + (0,)
    fields = {
        'CompanyName': 'Yananai Chiwuta', 'FileDescription': 'LiteNetMonitor',
        'FileVersion': APP_VERSION, 'InternalName': 'LiteNetMonitor',
        'LegalCopyright': 'Copyright 2026 Yananai Chiwuta',
        'OriginalFilename': 'LiteNetMonitor.exe', 'ProductName': 'LiteNetMonitor',
        'ProductVersion': APP_VERSION,
    }
    strings = ',\n'.join(f'StringStruct({key!r}, {value!r})' for key, value in fields.items())
    path.write_text(
        f'VSVersionInfo(ffi=FixedFileInfo(filevers={parts!r}, prodvers={parts!r}, '
        'mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0)), '
        f"kids=[StringFileInfo([StringTable('040904B0', [{strings}])]), "
        "VarFileInfo([VarStruct('Translation', [1033, 1200])])])", encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-version', help='Refuse to build a mismatched release tag')
    args = parser.parse_args()
    checked_version(args.expected_version)
    machine = platform.machine().lower()
    architecture = {'amd64': 'x64', 'x86_64': 'x64', 'aarch64': 'arm64', 'arm64': 'arm64'}.get(machine)
    system = {'win32': 'windows', 'darwin': 'macos', 'linux': 'linux'}.get(sys.platform)
    if not system or not architecture:
        raise SystemExit(f'Unsupported build target: {sys.platform}/{machine}')
    os.chdir(ROOT)
    output = ROOT / 'dist' / 'releases'
    output.mkdir(parents=True, exist_ok=True)
    build_dir = ROOT / 'build'
    build_dir.mkdir(exist_ok=True)
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed',
               '--name', 'LiteNetMonitor', '--exclude-module', 'pystray', '--exclude-module', 'PIL']
    if system == 'windows':
        version_path = build_dir / 'windows-version.txt'
        windows_version_file(version_path)
        command += ['--onefile', '--version-file', str(version_path)]
    elif system == 'linux':
        command += ['--onefile']
    else:
        command += ['--osx-bundle-identifier', 'io.github.yananai-chiwuta.litenetmonitor']
    subprocess.run(command + ['LiteNetMonitor.pyw'], check=True)
    if system == 'macos':
        info_path = ROOT / 'dist' / 'LiteNetMonitor.app' / 'Contents' / 'Info.plist'
        with info_path.open('rb') as stream:
            info = plistlib.load(stream)
        info.update(CFBundleShortVersionString=APP_VERSION, CFBundleVersion=APP_VERSION)
        with info_path.open('wb') as stream:
            plistlib.dump(info, stream)
        # Updating Info.plist invalidates the local ad-hoc signature. Restore it;
        # this is not Developer ID signing or Apple notarization.
        subprocess.run(['codesign', '--force', '--deep', '--sign', '-', str(info_path.parents[1])], check=True)
    binary = (ROOT / 'dist' / 'LiteNetMonitor.app' / 'Contents' / 'MacOS' / 'LiteNetMonitor'
              if system == 'macos' else ROOT / 'dist' / ('LiteNetMonitor.exe' if system == 'windows' else 'LiteNetMonitor'))
    if system == 'windows':
        from PyInstaller.utils.win32.versioninfo import read_version_info_from_executable
        metadata = read_version_info_from_executable(str(binary))
        major, minor, patch = map(int, APP_VERSION.split('.'))
        if (metadata is None or metadata.ffi.fileVersionMS != (major << 16 | minor)
                or metadata.ffi.fileVersionLS != patch << 16):
            raise RuntimeError('Windows executable version metadata does not match APP_VERSION')
    subprocess.run([str(binary), '--smoke-test'], check=True, timeout=30)
    stem = f'LiteNetMonitor-{APP_VERSION}-{system}-{architecture}'
    with tempfile.TemporaryDirectory(prefix='litenetmonitor-release-') as temporary:
        folder = Path(temporary) / stem
        folder.mkdir()
        for name in ('README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.txt', 'CHANGELOG.md'):
            shutil.copy2(ROOT / name, folder / name)
        (folder / 'VERSION.txt').write_text(APP_VERSION + '\n', encoding='utf-8')
        python_license = Path(sys.base_prefix) / 'LICENSE.txt'
        if python_license.exists():
            shutil.copy2(python_license, folder / 'PYTHON_LICENSE.txt')
        if system == 'macos':
            shutil.copytree(ROOT / 'dist' / 'LiteNetMonitor.app', folder / 'LiteNetMonitor.app', symlinks=True)
            archive = output / (stem + '.zip')
            subprocess.run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', str(folder), str(archive)], check=True)
        elif system == 'linux':
            shutil.copy2(ROOT / 'dist' / 'LiteNetMonitor', folder / 'LiteNetMonitor')
            archive = output / (stem + '.tar.gz')
            with tarfile.open(archive, 'w:gz') as stream:
                stream.add(folder, arcname=stem)
        else:
            shutil.copy2(ROOT / 'dist' / 'LiteNetMonitor.exe', folder / 'LiteNetMonitor.exe')
            archive = output / (stem + '.zip')
            with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as stream:
                for file in folder.rglob('*'):
                    if file.is_file():
                        stream.write(file, file.relative_to(folder.parent))
    print(f'Created {archive}')


if __name__ == '__main__':
    main()
