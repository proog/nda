import subprocess
import os
import sys


def run(args):
    output = subprocess.check_output(args, shell=True, stderr=subprocess.STDOUT).decode('utf-8').splitlines()

    if len(output) == 0:
        output = ['no output']

    return output


def git_pull():
    try:
        subprocess.check_call(['git', 'pull'])
        return True
    except subprocess.CalledProcessError:
        return False


def restart(file):
    os.execv(file, sys.argv)
