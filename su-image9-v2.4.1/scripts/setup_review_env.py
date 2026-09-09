#!/usr/bin/env python3
"""Explicit, opt-in virtual environment for the optional media/PDF backend."""
from __future__ import annotations
import argparse
from pathlib import Path
import subprocess
import sys
import venv


def main() -> int:
    ap=argparse.ArgumentParser(description='可选审阅/PDF虚拟环境；需显式--install，不修改系统Python。')
    ap.add_argument('--install',action='store_true')
    ap.add_argument('--venv',type=Path,default=Path(__file__).resolve().parents[1]/'.venv-review')
    args=ap.parse_args()
    if not args.install:
        print('尚未安装。获得安装授权后使用 --install；文字/Prompt工具不需要此依赖。')
        return 0
    folder=args.venv.resolve()
    try:
        if folder.exists() and not (folder/'pyvenv.cfg').is_file():
            raise ValueError('目标已存在且不是虚拟环境，不覆盖。')
        if not folder.exists():
            venv.EnvBuilder(with_pip=True).create(folder)
        python=folder/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
        requirements=Path(__file__).resolve().parents[1]/'requirements-review.txt'
        subprocess.run([str(python),'-m','pip','install','-r',str(requirements)],check=True)
        subprocess.run([str(python),str(Path(__file__).with_name('export_review.py')),'--doctor'],check=True)
        print('审阅/PDF使用此Python：',python)
        return 0
    except (OSError,ValueError,subprocess.CalledProcessError) as exc:
        print('审阅环境尚未完成：'+str(exc),file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
