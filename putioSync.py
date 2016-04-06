#!/usr/bin/python3
import copy
import json
import logging
import math
import os
import pycurl
import queue
import requests
import shutil
import threading
import time
import yaml
import tempfile
import fileinput
from datetime import datetime

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('putioSync')

MB = math.pow(2, 20)

config = {}
with open("config/config.yml", 'r') as stream:
    try:
        config = yaml.load(stream)
    except yaml.YAMLError as exc:
        raise Exception('No config.yml exists')

config["baseUrl"] = config["baseUrl"] if "baseUrl" in config else 'https://api.put.io/v2'
config["deleteAfterSync"] = config["deleteAfterSync"] if "deleteAfterSync" in config else True
config["minPartSize"] = config["minPartSize"] if "minPartSize" in config else 64 * MB
config["maxPartSize"] = config["maxPartSize"] if "maxPartSize" in config else 256 * MB
config["downloadPlaylist"] = config["downloadPlaylist"] if "downloadPlaylist" in config else False

if "syncDir" not in config:
    raise Exception('No syncDir specified in config')
complete = {}

if config["syncDir"][-1] != "/":
    config["syncDir"] += "/"


class PutIoAPI:
    def __init__(self):
        self.session = requests.Session()
        self.access_token = config["token"]

    def request(self, path, method='GET', params=None, data=None, files=None,
                headers=None, raw=False, stream=False):
        if not params:
            params = {}
        headers = {}

        params['oauth_token'] = self.access_token
        headers['Accept'] = 'application/json'

        url = config["baseUrl"] + path

        try:
            response = self.session.request(
                method, url, params=params, data=data, files=files,
                headers=headers, allow_redirects=True, stream=stream)
        except (requests.exceptions.ConnectionError, requests.exceptions.ConnectTimeout) as e:
            raise Exception('Problem connection to server {}'.format(e))

        try:
            response = json.loads(response.content.decode('utf-8'))
        except (ValueError, TypeError):
            raise Exception('Server didn\'t send valid JSON:\n%s\n%s' % (
                response, response.content))
        if response['status'] == 'ERROR':
            raise Exception(response['error_type'])

        return response

    def list(self, parent_id=0):
        try:
            l = self.request('/files/list', params={'parent_id': parent_id})
        except e:
            logger.debug("Error Getting file list: {}".format(s))
            return []
        files = l['files']
        return files

    def delete(self, file):
        logger.info("Deleting File with: {}".format(file['name']))
        result = self.request('/files/delete', 'POST', data={'file_ids': file['id']})
        logger.debug("Delete result: {}".format(result))

    def sync(self, parent=0, parent_path=config["syncDir"]):
        files = self.list(parent)
        params = {}
        params['oauth_token'] = self.access_token

        for file in files:
            if file['content_type'] == 'application/x-directory':
                if not os.path.exists(parent_path + file['name']):
                    os.makedirs(parent_path + file['name'])
                if self.sync(file['id'], parent_path + file['name'] + "/") == 0:  # delete empty folders
                    self.delete(file)
            else:
                org = {}
                org['file'] = file
                org['parent_path'] = parent_path
                if config["downloadPlaylist"] and "video" in file['content_type']:
                    downloadItem = copy.deepcopy(org)
                    queue.put(downloadItem)
                else:
                    partSize = file['size'] / 5
                    if partSize > config["maxPartSize"]:
                        partSize = config["maxPartSize"]
                    elif partSize < config["minPartSize"]:
                        partSize = config["minPartSize"]

                    if not file['id'] in complete.keys():
                        complete[file['id']] = {'parts': int(math.ceil(file['size'] / partSize)), 'started': datetime.now()}
                        total = 0
                        partId = 0
                        while total < file['size']:
                            downloadItem = copy.deepcopy(org)
                            downloadItem['partId'] = copy.copy(partId)
                            partId += 1
                            downloadItem['range_start'] = total + 1 if total > 0 else 0
                            downloadItem['range_end'] = file['size'] if total + partSize >= file[
                                'size'] else total + partSize
                            total += partSize
                            queue.put(downloadItem)
                        complete[file['id']]['parts'] = copy.copy(partId)

        return len(files)


class DownloadThread(threading.Thread):
    def __init__(self, queue, pdm):
        threading.Thread.__init__(self)
        self.queue = queue
        self.pdm = pdm

    def assembleFile(self, info):
        parent_path = info['parent_path']
        file = info['file']
        tmpName = os.sep.join([tempfile.gettempdir(), file['name']])

        # check that all the parts are done
        total = 0

        logger.debug(complete[file['id']])

        logger.debug("Checking for parts of file {}".format(file['name']))
        for i in range(complete[file['id']]['parts']):
            partName = tmpName + ".part.%i" % i
            if os.path.exists(partName):
                total += os.path.getsize(partName)
        logger.debug("Found {} of {}".format(total, file['size']))
        if total >= file['size']:
            ended = datetime.now()
            totalTime = ended - complete[file['id']]['started']
            logger.info("Download Time: {}".format(totalTime.total_seconds()))
            logger.info("Assembing {}".format(file['name']))
            with open(tmpName, 'wb') as f:
                for i in range(complete[file['id']]['parts']):
                    partName = tmpName + ".part.%i" % i
                    logger.debug("Appending part: {}".format(partName))
                    with open(partName, 'rb') as sf:
                        f.write(sf.read())
                    os.remove(partName)
            logger.info("Moving file {} to {}".format(file['name'], config["syncDir"]))
            if not os.path.exists(parent_path):
                os.makedirs(parent_path)
            shutil.move(tmpName, parent_path + file['name'])
            del complete[file['id']]
            if config["deleteAfterSync"]:
                logger.info("Deleteing fie {} from put.io".format(file['name']))
                self.pdm.delete(file)
    def replaceInFile(self,file):
        with fileinput.FileInput(file, inplace=True) as file:
            for line in file:
                print(line.replace('/v2/files', 'http://put.io/v2/files'), end='')
    def downloadFile(self, info):
        file = info['file']
        mode = "wb"
        c = pycurl.Curl()
        c.setopt(c.FOLLOWLOCATION, True)
        parent_path = info['parent_path']
        if config["downloadPlaylist"] and "video" in file['content_type']:
            logger.info("Downloading {} as a playlist".format(parent_path + file['name']))
            logger.info('{}/files/{}/hls/media.m3u8?oauth_token={}'.format(config["baseUrl"], file['id'], pdm.access_token))
            c.setopt(c.URL,'{}/files/{}/hls/media.m3u8?oauth_token={}'.format(config["baseUrl"], file['id'], pdm.access_token))
            tmpName = os.sep.join([tempfile.gettempdir(), "{}.m3u8".format(file['name'])])
        else:
            logger.info("Downloading {}, Part: {}".format(parent_path + file['name'], info['partId']))
            tmpName = os.sep.join([tempfile.gettempdir(),"{}.part.{}" .format(file['name'],info['partId'])])
            c = pycurl.Curl()
            c.setopt(c.URL,'{}/files/{}/download?oauth_token={}'.format(config["baseUrl"], file['id'], pdm.access_token))
            logger.info("[{}] Range: {}-{}".format(tmpName, info['range_start'], info['range_end']))
            if os.path.exists(tmpName):
                mode = "ab"
                info['range_start'] += os.path.getsize(tmpName)
                logger.info("[{}] Adjusted Range: {}-{}".format(tmpName, info['range_start'], info['range_end']))
            c.setopt(pycurl.RANGE, "%i-%i" % (info['range_start'], info['range_end']))
        with open(tmpName, mode) as f:
            c.setopt(c.WRITEDATA, f)
            c.perform()
            c.close()
        if config["downloadPlaylist"] and "video" in file['content_type']:
            self.replaceInFile(tmpName)
            shutil.move(tmpName, parent_path + file['name'] + ".m3u8")
        else:
            self.assembleFile(info)

    def run(self):
        while True:
            # grabs host from queue
            item = self.queue.get()
            logger.debug("Queue Item: {}".format(item))
            if not item is None:
                self.downloadFile(item)

            # signals to queue job is done
            self.queue.task_done()
            time.sleep(1)


def syncIt():
    pdm.sync()
    # queue.join() #wait on initial set to sync before starting over
    threading.Timer(180, syncIt).start()


queue = queue.Queue()
pdm = PutIoAPI()

for i in range(10):
    t = DownloadThread(queue, pdm)
    t.setDaemon(True)
    t.start()

syncIt()
