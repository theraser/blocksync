## About
This script is used to synchronize (large) files to a local/remote destination using a incremental algorithm. Devices are used as regular files and can be synchronized, too.

blocksync.py is also a workaround for a limitation when using [rsync](https://rsync.samba.org): rsync is unable to synchronize a *device* using its incremental algorithm. blocksync.py is able to sync a device file bit by bit to a remote SSH destination. When called multiple times it will only copy those blocks which were modified - this will speed up the copy process and save a lot of bandwidth.

## Use cases
* Moving physical machines to virtual ones ([p2v](https://en.wikipedia.org/wiki/Physical-to-Virtual))
* Backup failed machines' hard drives
* Synchronize large files to a (remote) destination using a fast and efficent algorithm

## Requirements
* SSH client on source server
* SSH server on destination server, with root permissions (directly using root login or using sudo) if syncing to a device file
* Python on both source and destination server
* blocksync.py in home directory of destination server (executable)

## Usage
Please make sure that the source file isn't changed during sync, blocksync.py will **not** notice any changes made at file positions which were already copied. You may want to boot a live linux ([grml](https://grml.org/), [knoppix](http://www.knoppix.org), [systemrescuecd](http://www.system-rescue-cd.org) etc.) if you want to sync the system drives from a running machine.

### Synchronize to a file on remote server
`root@source# python blocksync.py /dev/source/file user@destination.example.com /path/to/destination/file`

### Synchronize to a local file
`root@source# python blocksync.py /dev/source/file localhost /path/to/destination/file`

## Command line options
Please run python blocksync.py without any arguments to get a full list of possible options.

## Contributing
Please feel free to leave a bug report here at Github or drop a pull request - every help is welcome!

## Docker

Useful for imaging, re-imaging raspberry pi and similar SBC sd cards while only writing the minimum number of sectors.

```bash
# Double check that you're going to stomp the correct block device
lsblk

docker run -t --network=none \
    --device /dev/sda:/dev/target \
    -v "$PWD":/iso:ro \
    corycarson/blocksync -I python3 /iso/ubuntu-22.04.1-preinstalled-server-arm64+raspi.img localhost /dev/target
```

```
[worker 0] same: 46, diff: 128, 174/947,   4.6 MB/s (0:09:23 remaining)
[worker 0] same: 46, diff: 130, 176/947,   4.6 MB/s (0:09:23 remaining)
[worker 0] same: 46, diff: 132, 178/947,   4.5 MB/s (0:09:23 remaining)
[worker 0] same: 46, diff: 134, 180/947,   4.6 MB/s (0:09:23 remaining)
[worker 0] same: 46, diff: 136, 182/947,   4.6 MB/s (0:09:22 remaining)
[worker 0] same: 46, diff: 138, 184/947,   4.6 MB/s (0:09:22 remaining)
[worker 0] same: 46, diff: 140, 186/947,   4.6 MB/s (0:09:22 remaining)
[worker 0] same: 46, diff: 142, 188/947,   4.5 MB/s (0:09:22 remaining)
```

