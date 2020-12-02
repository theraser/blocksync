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
