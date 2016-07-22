#!/usr/bin/env python
"""
Synchronise block devices over the network

Copyright 2006-2008 Justin Azoff <justin@bouncybouncy.net>
Copyright 2011 Robert Coup <robert@coup.net.nz>
Copyright 2012 Holger Ernst <info@ernstdatenmedien.de>
Copyright 2014 Robert McQueen <robert.mcqueen@collabora.co.uk>
Copyrught 2016 Theodor Ciobanu
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

import os
import sys
from hashlib import sha512
from base64 import b64encode
from math import ceil
import subprocess
import time

SAME = "0"
DIFF = "1"
COMPLEN = len(SAME)  # SAME/DIFF length

B64SHA = int(ceil(sha512().digest_size * 4 / 3.0))
#HASHLEN = B64SHA + (4 - B64SHA % 4)
HASHLEN = sha512().digest_size


def do_open(f, mode):
    f = open(f, mode)
    f.seek(0, 2)
    size = f.tell()
    f.seek(0)
    return f, size


def getblocks(f, blocksize):
    while 1:
        block = f.read(blocksize)
        if not block:
            break
        yield block


def server(dev, blocksize):
    print dev, blocksize
    f, size = do_open(dev, 'r+')
    print size
    sys.stdout.flush()

    startpos = int(sys.stdin.readline().strip())
    maxblock = int(sys.stdin.readline().strip()) - 1

    f.seek(startpos)

    for i, block in enumerate(getblocks(f, blocksize)):
        #sys.stdout.write(b64encode(sha512(block).digest()))
        sys.stdout.write(sha512(block).digest())
        sys.stdout.flush()
        res = sys.stdin.read(COMPLEN)
        if res != SAME:
            newblock = sys.stdin.read(blocksize)
            f.seek(-len(newblock), 1)
            f.write(newblock)
        if i == maxblock:
            break


def sync(workerid, srcdev, dsthost, dstdev = None, blocksize = 1024 * 1024, keyfile = None, pause = 0, sudo = False, compress = False, workers = 1):

    if not dstdev:
        dstdev = srcdev

    print "Starting worker #%d (pid: %d)" % (workerid, os.getpid())
    print "[worker %d] Block size is %0.1f MB" % (workerid, float(blocksize) / (1024 * 1024))

    try:
        f, size = do_open(srcdev, 'r')
    except Exception, e:
        print "[worker %d] Error accessing source device! %s" % (workerid, e)
        sys.exit(1)

    chunksize = int(size / workers)
    startpos = workerid * chunksize
    if workerid == (workers - 1):
        chunksize += size - (chunksize * workers)
    print "[worker %d] Chunk size is %0.1f MB, offset is %d" % (workerid, float(chunksize) / (1024 * 1024), startpos)

    pause_ms = 0
    if pause:
        # sleep() wants seconds...
        pause_ms = float(pause) / 1000
        print "[worker %d] Slowing down for %d ms/block (%0.4f sec/block)" % (workerid, pause, pause_ms)

    cmd = []
    if dsthost != 'localhost':
        cmd += ['ssh', '-c', 'blowfish']
        if keyfile:
            cmd += ['-i', keyfile]
        if compress:
            cmd += ['-C']
        cmd += [dsthost]
    if sudo:
        cmd += ['sudo']
    cmd += ['python', os.path.basename(__file__), 'server', dstdev, '-b', str(blocksize)]

    print "[worker %d] Running: %s" % (workerid, " ".join(cmd))

    p = subprocess.Popen(cmd, bufsize=0, stdin=subprocess.PIPE, stdout=subprocess.PIPE, close_fds=True)
    p_in, p_out = p.stdin, p.stdout

    line = p_out.readline()
    p.poll()
    if p.returncode is not None:
        print "[worker %d] Error connecting to or invoking blocksync on the remote host!" % (workerid)
        sys.exit(1)

    a, b = line.split()
    if a != dstdev:
        print "[worker %d] Dest device (%s) doesn't match with the remote host (%s)!" % (workerid, dstdev, a)
        sys.exit(1)
    if int(b) != blocksize:
        print "[worker %d] Source block size (%d) doesn't match with the remote host (%d)!" % (workerid, blocksize, int(b))
        sys.exit(1)

    line = p_out.readline()
    p.poll()
    if p.returncode is not None:
        print "[worker %d] Error accessing device on remote host!" % (workerid)
        sys.exit(1)
    remote_size = int(line)
    if size > remote_size:
        print "[worker %d] Source device size (%d) doesn't fit into remote device size (%d)!" % (workerid, size, remote_size)
        sys.exit(1)
    elif size < remote_size:
        print "[worker %d] Source device size (%d) is smaller than remote device size (%d), proceeding anyway" % (workerid, size, remote_size)

    same_blocks = diff_blocks = 0
    interactive = os.isatty(sys.stdout.fileno())

    t0 = time.time()
    t_last = t0
    f.seek(startpos)
    size_blocks = ceil(chunksize / float(blocksize))
    p_in.write("%d\n%d\n" % (startpos, size_blocks))
    print "[worker %d] Start syncing %d blocks..." % (workerid, size_blocks)
    for l_block in getblocks(f, blocksize):
        #l_sum = b64encode(sha512(l_block).digest())
        l_sum = sha512(l_block).digest()
        r_sum = p_out.read(HASHLEN)
        #print "[worker %d] %s %s" % (workerid, b64encode(l_sum), b64encode(r_sum))
        if l_sum == r_sum:
            p_in.write(SAME)
            p_in.flush()
            same_blocks += 1
        else:
            p_in.write(DIFF)
            p_in.flush()
            p_in.write(l_block)
            p_in.flush()
            diff_blocks += 1

        if pause_ms:
            time.sleep(pause_ms)

        if not interactive:
            continue

        t1 = time.time()
        if t1 - t_last > 1:
            rate = (i + 1.0) * blocksize / (1024.0 * 1024.0) / (t1 - t0)
            print "[worker %d] same: %d, diff: %d, %d/%d, %5.1f MB/s\n" % (workerid, same_blocks, diff_blocks, same_blocks + diff_blocks, size_blocks, rate),
            t_last = t1

        if (same_blocks + diff_blocks) == size_blocks:
            break

    rate = (i + 1.0) * blocksize / (1024.0 * 1024.0) / (time.time() - t0)
    print "[worker %d] same: %d, diff: %d, %d/%d, %5.1f MB/s" % (workerid, same_blocks, diff_blocks, same_blocks + diff_blocks, size_blocks, rate)

    print "[worker %d] Completed in %d seconds" % (workerid, time.time() - t0)

    return same_blocks, diff_blocks

if __name__ == "__main__":
    from optparse import OptionParser, SUPPRESS_HELP
    parser = OptionParser(usage = "%prog [options] /dev/source [user@]remotehost [/dev/dest]")
    parser.add_option("-b", "--blocksize", dest = "blocksize", type = "int", help = "block size (bytes, defaults to 1MB)", default = 1024 * 1024)
    parser.add_option("-i", "--id", dest = "keyfile", help = "ssh public key file")
    parser.add_option("-p", "--pause", dest = "pause", type="int", help = "pause between processing blocks, reduces system load (ms, defaults to 0)", default = 0)
    parser.add_option("-s", "--sudo", dest = "sudo", action = "store_true", help = "use sudo on the remote end (defaults to off)", default = False)
    parser.add_option("-c", "--compress", dest = "compress", action = "store_true", help = "enable compression over SSH (default to off)", default = False)
    parser.add_option("-w", "--workers", dest = "workers", type = "int", help = "number of workers to fork (defaults to 1)", default = 1)
    (options, args) = parser.parse_args()

    if len(args) < 2:
        parser.print_help()
        print __doc__
        sys.exit(1)

    if args[0] == 'server':
        dstdev = args[1]
        server(dstdev, options.blocksize)
    else:
        srcdev = args[0]
        dsthost = args[1]
        if len(args) > 2:
            dstdev = args[2]
        else:
            dstdev = None

        workers = {}
        for i in xrange(options.workers):
            pid = os.fork()
            if pid == 0:
                sync(i, srcdev, dsthost, dstdev, options.blocksize, options.keyfile, options.pause, options.sudo, options.compress, options.workers)
                sys.exit(0)
            else:
                workers[pid] = i

        for i in xrange(options.workers):
            pid, err = os.wait()
            print "Worker #%d exited with %d" % (workers[pid], err)
