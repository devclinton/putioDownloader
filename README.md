putioDownloader
=============

This project can be used to download files from put.io to a local machine. The download is split into parts.

===

### Installation

`git clone git@github.com:oudenmallon/putioDownloader.git`

Run `pip install .`

### Configuring

You need to create a **config/config.yml** file. See config.yml.example for an example config

#### Configuration Options

* **syncDir** - Directory to download files to
* **token** - Put.io Token. You can acquire from this url
* **deleteAfterSync** - Boolean(True|False). If it is True, the file will be deleted from Putio after downloading. If downloading as Playlist is enabled, the file will not be deleted
* **minPartSize** - Minimum size in bytes for download parts - Defaults to 67108864(64MB)
* **maxPartSize** - Maximum size in bytes for a download parts - Defaults to 268435456(256MB)
* **downloadPlaylist** - Download item as playlist only

### Running

`python putioSync.py`