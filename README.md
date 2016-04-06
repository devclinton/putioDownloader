putioDownloader
=============

This project can be used to download files from put.io to a local machine. The download is split into parts.

Requires Python3

===

### Installation

`git clone git@github.com:oudenmallon/putioDownloader.git`

Run `pip3 install .`

### Configuring

You need to create a **config/config.yml** file. See [config.yml.example](https://github.com/oudenmallon/putioDownloader/blob/master/config/config.yml.example)  for an example config

#### Configuration Options

* **syncDir** - Directory to download files to.
* **token** - Put.io Token. You can acquire from this url
* **deleteAfterSync** - Boolean(True|False). If it is True, the file will be deleted from Putio after downloading. If downloading as Playlist is enabled, the file will not be deleted
* **minPartSize** - Minimum size in bytes for download parts - Defaults to *67108864(64MB)*
* **maxPartSize** - Maximum size in bytes for a download parts - Defaults to *268435456(256MB)*
* **downloadPlaylist** - Download item as playlist only. Default to *False*
* **downloadThreads** - How many download threads to run simultanously. Default to *10*

### Running

`python3 putioSync.py`