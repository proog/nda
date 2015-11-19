import subprocess
import os
import sys


def run(args):
    process = subprocess.run(args, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = process.stdout.decode('utf-8').splitlines()

    if len(output) == 0:
        output = ['return code %i, no output' % process.returncode] + output

    return output


def git_pull():
    process = subprocess.run(['git', 'pull'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return process.returncode == 0


def restart(file):
    os.execv(file, sys.argv)
