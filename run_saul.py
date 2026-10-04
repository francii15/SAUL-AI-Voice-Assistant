"""Windows launcher: keep one launched Saul instance per installation."""
import os
from pathlib import Path
import subprocess
import sys


def main():
    if os.name != 'nt':
        print('This desktop release requires Windows.')
        return 1
    import msvcrt
    root = Path(__file__).resolve().parent
    with (root / '.saul-running.lock').open('a+b') as handle:
        if handle.tell() == 0:
            handle.write(b'0'); handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            print('Saul is already running. Use its existing terminal window.')
            return 2
        try:
            child = subprocess.Popen([sys.executable, str(root / 'assistant.py'), *sys.argv[1:]], cwd=root)
            try:
                return child.wait()
            except KeyboardInterrupt:
                # The child receives Ctrl+C from the same Windows console.
                try:
                    return child.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    child.terminate()
                    return child.wait()
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


if __name__ == '__main__':
    raise SystemExit(main())
