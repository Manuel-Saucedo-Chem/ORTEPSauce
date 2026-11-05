"""Entry point for the stand-alone ORTEPSauce.exe (PyInstaller).

freeze_support() must run first: the GIF export renders frames in worker processes, and in a
frozen .exe every worker starts this same program again."""
import multiprocessing
import os
import sys


def main():
    multiprocessing.freeze_support()
    # a windowed .exe has no console: give print() somewhere harmless to write
    if sys.stdout is None:
        sys.stdout = open(os.devnull, 'w')
    if sys.stderr is None:
        sys.stderr = open(os.devnull, 'w')
    from ortepsauce.__main__ import cli
    return cli()


if __name__ == '__main__':
    sys.exit(main())
