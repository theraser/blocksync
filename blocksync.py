#!/usr/bin/env python2
"""
Synchronise block devices over the network

Copyright 2006-2008 Justin Azoff <justin@bouncybouncy.net>
Copyright 2011 Robert Coup <robert@coup.net.nz>
Copyright 2012 Holger Ernst <info@ernstdatenmedien.de>
Copyright 2014 Robert McQueen <robert.mcqueen@collabora.co.uk>
Copyright 2016 Theodor-Iulian Ciobanu
License: GPL

Getting started:

* Copy blocksync.py to the home directory on the remote host & make it executable
* Make sure your remote user is either root or can sudo (use -s for sudo)
* Make sure your local user can ssh to the remote host (use -i for a SSH key)
* Invoke:
    python blocksync.py /dev/source [user@]remotehost [/dev/dest]

* Specify localhost for local usage:
    python blocksync.py /dev/source localhost /dev/dest
"""

from __future__ import print_function
import os
import sys
import signal
import hashlib
from math import ceil
import subprocess
import time
from datetime import timedelta

SAME = b"0"
DIFF = b"1"
COMPLEN = len(SAME)  # SAME/DIFF length

LOCAL_FADVISE = 1
REMOTE_FADVISE = 2

if callable(getattr(os, "posix_fadvise", False)):
    from os import posix_fadvise, POSIX_FADV_NOREUSE, POSIX_FADV_DONTNEED
    fadvise = lambda fileobj, offset, length, advice: posix_fadvise(fileobj.fileno(), offset, length, advice)
else:
    try:
        from fadvise import set_advice, POSIX_FADV_NOREUSE, POSIX_FADV_DONTNEED
        fadvise = lambda fileobj, offset, length, advice: set_advice(fileobj, advice, offset, length)
    except:
        fadvise = None

if fadvise:
    USE_DONTNEED = sys.platform.startswith('linux')
    USE_NOREUSE = not(USE_DONTNEED)
else:
    USE_NOREUSE = USE_DONTNEED = False

def do_create(f, size):
    f = open(f, 'a', 0)
    f.truncate(size)
    f.close()


def do_open(f, mode):
    f = open(f, mode)
    if USE_NOREUSE:
        fadvise(f, 0, 0, POSIX_FADV_NOREUSE)
    f.seek(0, 2)
    size = f.tell()
    f.seek(0)
    return f, size


def getblocks(f, blocksize):
    while 1:
        block = f.read(blocksize)
        if not block:
            break
        if USE_DONTNEED:
            fadvise(f, f.tell() - blocksize, blocksize, POSIX_FADV_DONTNEED)
        yield block


def server(dev, deleteonexit, options):
    global USE_NOREUSE, USE_DONTNEED

    blocksize = options.blocksize

    hash1 = getattr(hashlib, options.hash.lower())
    hash2 = getattr(hashlib, options.addhash.lower()) if options.addhash else False

    print('init')
    sys.stdout.flush()

    if (options.fadvise & REMOTE_FADVISE == 0):
        print('Disabled')
        USE_NOREUSE = USE_DONTNEED = False
    elif USE_NOREUSE:
        print('NOREUSE')
    elif USE_DONTNEED:
        print('DONTNEED')
    else:
        print('None')
    sys.stdout.flush()

    size = int(sys.stdin.readline().strip())
    if size > 0:
        do_create(dev, size)

    print(dev, blocksize)
    f, size = do_open(dev, 'rb+')
    print(size)
    sys.stdout.flush()

    startpos = int(sys.stdin.readline().strip())
    maxblock = int(sys.stdin.readline().strip()) - 1

    f.seek(startpos)

    if getattr(sys.stdin, "buffer", False):
        stdin = sys.stdin.buffer
        stdout = sys.stdout.buffer
    else:
        stdin = sys.stdin
        stdout = sys.stdout

    for i, block in enumerate(getblocks(f, blocksize)):
        stdout.write(hash1(block).digest())
        if hash2:
            stdout.write(hash2(block).digest())
        stdout.flush()
        res = stdin.read(COMPLEN)
        if res == DIFF:
            newblock = stdin.read(blocksize)
            newblocklen = len(newblock)
            f.seek(-newblocklen, 1)
            f.write(newblock)
            if USE_DONTNEED:
                fadvise(f, f.tell() - newblocklen, newblocklen, POSIX_FADV_DONTNEED)
        if i == maxblock:
            break

    if deleteonexit:
        os.remove(__file__)


def copy_self(workerid, remotecmd):
    with open(__file__) as srcfile:
        cmd = remotecmd + ['/usr/bin/env', 'sh', '-c', '"SCRIPTNAME=\`mktemp -q\`; cat >\$SCRIPTNAME; echo \$SCRIPTNAME"', '<<EOT\n', srcfile.read(), '\nEOT']

    p = subprocess.Popen(cmd, bufsize=0, stdin=subprocess.PIPE, stdout=subprocess.PIPE, close_fds=True)
    p_in, p_out = p.stdin, p.stdout

    remotescript = p_out.readline().strip()
    p.poll()
    if p.returncode is not None:
        print("[worker %d] Error copying blocksync to the remote host!" % workerid, file = options.outfile)
        sys.exit(1)

    return remotescript.decode('UTF-8')


def sync(workerid, srcdev, dsthost, dstdev, options):
    global USE_NOREUSE, USE_DONTNEED

    blocksize = options.blocksize
    addhash = options.addhash
    dryrun = options.dryrun
    interval = options.interval

    if not dstdev:
        dstdev = srcdev

    print("Starting worker #%d (pid: %d)" % (workerid, os.getpid()), file = options.outfile)
    print("[worker %d] Block size is %0.1f MB" % (workerid, blocksize / (1024.0 * 1024)), file = options.outfile)

    if (options.fadvise & LOCAL_FADVISE == 0):
        fadv = "Disabled"
        USE_NOREUSE = USE_DONTNEED = False
    elif USE_NOREUSE:
        fadv = "NOREUSE"
    elif USE_DONTNEED:
        fadv = "DONTNEED"
    else:
        fadv = "None"
    print("[worker %d] Local fadvise: %s" % (workerid, fadv), file = options.outfile)

    try:
        f, size = do_open(srcdev, 'rb')
    except Exception as e:
        print("[worker %d] Error accessing source device! %s" % (workerid, e), file = options.outfile)
        sys.exit(1)

    chunksize = int(size / options.workers)
    startpos = workerid * chunksize
    if workerid == (options.workers - 1):
        chunksize += size - (chunksize * options.workers)
    print("[worker %d] Chunk size is %0.1f MB, offset is %d" % (workerid, chunksize / (1024.0 * 1024), startpos), file = options.outfile)

    pause_ms = 0
    if options.pause:
        # sleep() wants seconds...
        pause_ms = options.pause / 1000.0
        print("[worker %d] Slowing down for %d ms/block (%0.4f sec/block)" % (workerid, options.pause, pause_ms), file = options.outfile)

    hash1 = getattr(hashlib, options.hash.lower())
    hash1len = hash1().digest_size
    print("[worker %d] Hash 1: %s" % (workerid, options.hash.lower()), file = options.outfile)
    if options.addhash:
        hash2 = getattr(hashlib, options.addhash.lower())
        hash2len = hash2().digest_size
        print("[worker %d] Hash 2: %s" % (workerid, options.addhash.lower()), file = options.outfile)
    else:
        hash2 = False

    cmd = []
    if dsthost != 'localhost':
        if options.passenv:
            cmd += ['/usr/bin/env', 'SSHPASS=%s' % (os.environ[options.passenv]), 'sshpass', '-e']
        cmd += ['ssh', '-c', options.cipher]
        if options.keyfile:
            cmd += ['-i', options.keyfile]
        if options.compress:
            cmd += ['-C']
        if options.sshparams:
            cmd += options.sshparams.split()
        cmd += [dsthost]
    if options.sudo:
        cmd += ['sudo']

    if options.script:
        servercmd = 'server'
        remotescript = options.script
    elif (dsthost =='localhost'):
        servercmd = 'server'
        remotescript = __file__
    else:
        servercmd = 'tmpserver'
        remotescript = copy_self(workerid, cmd)

    cmd += [options.interpreter, remotescript, servercmd, dstdev, '-b', str(blocksize)]

    cmd += ['-d', str(options.fadvise), '-1', options.hash]
    if options.addhash:
        cmd += ['-2', options.addhash]

    print("[worker %d] Running: %s" % (workerid, " ".join(cmd[2 if options.passenv and (dsthost != 'localhost') else 0:])), file = options.outfile)

    p = subprocess.Popen(cmd, bufsize=0, stdin=subprocess.PIPE, stdout=subprocess.PIPE, close_fds=True)
    p_in, p_out = p.stdin, p.stdout

    line = p_out.readline().decode('UTF-8')
    p.poll()
    if (p.returncode is not None) or (line.strip() != 'init'):
        print("[worker %d] Error connecting to or invoking blocksync on the remote host!" % workerid, file = options.outfile)
        sys.exit(1)

    fadv = p_out.readline().decode('UTF-8').strip()
    print("[worker %d] Remote fadvise: %s" % (workerid, fadv), file = options.outfile)

    p_in.write(bytes(("%d\n" % (size if options.createdest else 0)).encode("UTF-8")))
    p_in.flush()

    line = p_out.readline().decode('UTF-8')
    p.poll()
    if p.returncode is not None:
      print("[worker %d] Failed creating destination file on the remote host!" % workerid, file = options.outfile)
      sys.exit(1)

    a, b = line.split()
    if a != dstdev:
        print("[worker %d] Dest device (%s) doesn't match with the remote host (%s)!" % (workerid, dstdev, a), file = options.outfile)
        sys.exit(1)
    if int(b) != blocksize:
        print("[worker %d] Source block size (%d) doesn't match with the remote host (%d)!" % (workerid, blocksize, int(b)), file = options.outfile)
        sys.exit(1)

    line = p_out.readline().decode('UTF-8')
    p.poll()
    if p.returncode is not None:
        print("[worker %d] Error accessing device on remote host!" % workerid, file = options.outfile)
        sys.exit(1)
    remote_size = int(line)
    if size > remote_size:
        print("[worker %d] Source device size (%d) doesn't fit into remote device size (%d)!" % (workerid, size, remote_size), file = options.outfile)
        sys.exit(1)
    elif size < remote_size:
        print("[worker %d] Source device size (%d) is smaller than remote device size (%d), proceeding anyway" % (workerid, size, remote_size), file = options.outfile)

    same_blocks = diff_blocks = last_blocks = 0
    interactive = os.isatty(sys.stdout.fileno())

    t0 = time.time()
    t_last = t0
    f.seek(startpos)
    size_blocks = ceil(chunksize / float(blocksize))
    p_in.write(bytes(("%d\n%d\n" % (startpos, size_blocks)).encode("UTF-8")))
    p_in.flush()
    print("[worker %d] Start syncing %d blocks..." % (workerid, size_blocks), file = options.outfile)
    for l_block in getblocks(f, blocksize):
        l1_sum = hash1(l_block).digest()
        r1_sum = p_out.read(hash1len)
        if hash2:
            l2_sum = hash2(l_block).digest()
            r2_sum = p_out.read(hash2len)
            r2_match = (l2_sum == r2_sum)
        else:
            r2_match = True
        if (l1_sum == r1_sum) and r2_match:
            same_blocks += 1
            p_in.write(SAME)
            p_in.flush()
        else:
            diff_blocks += 1
            if dryrun:
                p_in.write(SAME)
                p_in.flush()
            else:
                p_in.write(DIFF)
                p_in.flush()
                p_in.write(l_block)
                p_in.flush()

        if pause_ms:
            time.sleep(pause_ms)

        if not interactive:
            continue

        t1 = float(time.time())
        if (t1 - t_last) >= interval:
            done_blocks = same_blocks + diff_blocks
            delta_blocks = done_blocks - last_blocks
            rate = delta_blocks * blocksize / (1024 * 1024 * (t1 - t_last))
            print("[worker %d] same: %d, diff: %d, %d/%d, %5.1f MB/s (%s remaining)" % (workerid, same_blocks, diff_blocks, done_blocks, size_blocks, rate, timedelta(seconds = ceil((size_blocks - done_blocks) * (t1 - t0) / done_blocks))), file = options.outfile)
            last_blocks = done_blocks
            t_last = t1

        if (same_blocks + diff_blocks) == size_blocks:
            break

    rate = size_blocks * blocksize / (1024.0 * 1024) / (time.time() - t0)
    print("[worker %d] same: %d, diff: %d, %d/%d, %5.1f MB/s" % (workerid, same_blocks, diff_blocks, same_blocks + diff_blocks, size_blocks, rate), file = options.outfile)

    print("[worker %d] Completed in %s" % (workerid, timedelta(seconds = ceil(time.time() - t0))), file = options.outfile)

    return same_blocks, diff_blocks

if __name__ == "__main__":
    from optparse import OptionParser, SUPPRESS_HELP
    parser = OptionParser(usage = "%prog [options] /dev/source [user@]remotehost [/dev/dest]")
    parser.add_option("-w", "--workers", dest = "workers", type = "int", help = "number of workers to fork (defaults to 1)", default = 1)
    parser.add_option("-l", "--splay", dest = "splay", type = "int", help = "sleep between creating workers (ms, defaults to 0)", default = 250)
    parser.add_option("-b", "--blocksize", dest = "blocksize", type = "int", help = "block size (bytes, defaults to 1MB)", default = 1024 * 1024)
    parser.add_option("-1", "--hash", dest = "hash", help = "hash used for block comparison (defaults to \"sha512\")", default = "sha512")
    parser.add_option("-2", "--additionalhash", dest = "addhash", help = "second hash used for extra comparison (default is none)")
    parser.add_option("-d", "--fadvise", dest = "fadvise", type = "int", help = "lower cache pressure by using posix_fadivse (requires Python 3 or python-fadvise; 0 = off, 1 = local on, 2 = remote on, 3 = both on; defaults to 3)", default = 3)
    parser.add_option("-p", "--pause", dest = "pause", type="int", help = "pause between processing blocks, reduces system load (ms, defaults to 0)", default = 0)
    parser.add_option("-c", "--cipher", dest = "cipher", help = "cipher specification for SSH (defaults to blowfish)", default = "blowfish")
    parser.add_option("-C", "--compress", dest = "compress", action = "store_true", help = "enable compression over SSH (defaults to on)", default = True)
    parser.add_option("-i", "--id", dest = "keyfile", help = "SSH public key file")
    parser.add_option("-P", "--pass", dest = "passenv", help = "environment variable containing SSH password (requires sshpass)")
    parser.add_option("-s", "--sudo", dest = "sudo", action = "store_true", help = "use sudo on the remote end (defaults to off)", default = False)
    parser.add_option("-x", "--extraparams", dest = "sshparams", help = "additional parameters to pass to SSH")
    parser.add_option("-n", "--dryrun", dest = "dryrun", action = "store_true", help = "do a dry run (don't write anything, just report differences)", default = False)
    parser.add_option("-T", "--createdest", dest = "createdest", action = "store_true", help = "create destination file using truncate(2)", default = False)
    parser.add_option("-S", "--script", dest = "script", help = "location of script on remote host (otherwise current script is sent over)")
    parser.add_option("-I", "--interpreter", dest = "interpreter", help = "[full path to] interpreter used to invoke remote server (defaults to python2)", default = "python2")
    parser.add_option("-t", "--interval", dest = "interval", type = "int", help = "interval between stats output (seconds, defaults to 1)", default = 1)
    parser.add_option("-o", "--output", dest = "outfile", help = "send output to file instead of console")
    (options, args) = parser.parse_args()

    if len(args) < 2:
        parser.print_help()
        print(__doc__)
        sys.exit(1)

    aborting = False

    if options.outfile:
        options.outfile = open(options.outfile, 'a', 1)

    if args[0] == 'server':
        dstdev = args[1]
        server(dstdev, False, options)
    elif args[0] == 'tmpserver':
        dstdev = args[1]
        server(dstdev, True, options)
    else:
        srcdev = args[0]
        dsthost = args[1]
        if len(args) > 2:
            dstdev = args[2]
        else:
            dstdev = None

        if options.dryrun:
            print("Dryrun - will only report differences, no data will be written", file = options.outfile)
        else:
            print("\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!", file = options.outfile)
            print("!!!                                          !!!", file = options.outfile)
            print("!!! DESTINATION WILL BE PERMANENTLY CHANGED! !!!", file = options.outfile)
            print("!!!         PRESS CTRL-C NOW TO EXIT         !!!", file = options.outfile)
            print("!!!                                          !!!", file = options.outfile)
            print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n", file = options.outfile)
            time.sleep(5)

        splay_ms = 0
        if options.splay:
            # sleep() wants seconds...
            splay_ms = options.splay / 1000.0
        workers = {}
        for i in range(options.workers):
            pid = os.fork()
            if pid == 0:
                sync(i, srcdev, dsthost, dstdev, options)
                sys.exit(0)
            else:
                workers[pid] = i
            if splay_ms:
                time.sleep(splay_ms)

        for i in range(options.workers):
            pid, err = os.wait()
            print("Worker #%d exited with %d" % (workers[pid], err), file = options.outfile)
            if (err != 0) and not aborting:
                aborting = True
                print("Worker #%d caused ABORT" % workers[pid])
                del workers[pid]
                for pid in workers:
                    print("Terminating worker #%d" % workers[pid])
                    os.kill(pid, signal.SIGTERM)

    if options.outfile:
        options.outfile.close()

    if aborting:
        sys,exit(1)
