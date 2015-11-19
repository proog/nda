import subprocess
import os
import sys


def run(args):
    output = subprocess.check_output(args, shell=True, stderr=subprocess.STDOUT).decode('utf-8').splitlines()

    if len(output) == 0:
        output = ['no output']

    return output


def git_pull():
    return subprocess.check_call(['git', 'pull']) == 0


def restart(file):
    os.execv(file, sys.argv)
