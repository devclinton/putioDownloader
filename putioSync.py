#!/usr/bin/python3
import copy
import queue
import json
import logging
import math
import os
from functools import partial
import pycurl
import shutil
import threading
import time
from datetime import datetime
import requests
import yaml
from watchdog.events import FileSystemEventHandler
from watchdog.observers.polling import PollingObserver

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('putioSync')

UPLOADED = []

MB = math.pow(2, 20)

CONFIG = {}
with open("config/config.yml", 'r') as stream:
    try:
        config = yaml.safe_load(stream)
    except yaml.YAMLError as exc:
        raise Exception('No config.yml exists')

config["baseUrl"] = config["baseUrl"] if "baseUrl" in config else 'https://api.put.io/v2'
config["deleteAfterSync"] = config["deleteAfterSync"] if "deleteAfterSync" in config else True
config["minPartSize"] = config["minPartSize"] if "minPartSize" in config else 64 * MB
config["maxPartSize"] = config["maxPartSize"] if "maxPartSize" in config else 256 * MB
if "syncDir" not in config:
    raise Exception('No syncDir specified in config')
complete = {}

if config["syncDir"][-1] != "/":
    config["syncDir"] += "/"


def ascii_string(str):
    return str.encode('ascii', 'ignore').decode('ascii')


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
            raise Exception('Problem connection to server %s'.format(e))

        try:
            response = json.loads(response.content.decode('utf-8'))
        except (ValueError, TypeError):
            raise Exception('Server didn\'t send valid JSON:\n%s\n%s' % (
                response, response.content))
        if response['status'] == 'ERROR':
            raise Exception(response['error_type'])

        return response

    def upload_magnet(self, file):
        link = open(file, 'r').read().strip()
        try:
            logger.info('Uploading {}'.format(file))
            response = self.request('/transfers/add', method='POST', data={'url': link})
        except Exception as e:
            logger.error("Error Uploading the torrent file: %s".format(e))
            return False
        logger.info('Torrent Uploaded')
        return True

    def upload(self, file):
        try:
            logger.info('Uploading {}'.format(file))
            files = {'file': open(file, 'rb')}
            response = self.request('/files/upload', method='POST', files=files)
        except Exception as e:
            logger.error("Error Uploading the torrent file: %s".format(e))
            return False
        logger.info('Torrent Uploaded')
        return True

    def list(self, parent_id=0):
        try:
            response = self.request('/files/list', params={'parent_id': parent_id})
            logger.info("File List".format(str(response)))
        except Exception as e:
            logger.error(f"Error Getting file list: {str(e)}")
            return []
        files = response['files']
        return files

    def delete(self, file):
        logger.info(f"Deleting File with: {ascii_string(file['name'])}")
        result = self.request('/files/delete', 'POST', data={'file_ids': file['id']})
        logger.debug("Delete result: {}".format(result))

    def sync(self, queue, parent=0, parent_path=config["syncDir"]):
        files = self.list(parent)
        params = {'oauth_token': self.access_token}
        parent_path = ascii_string(parent_path)

        for file in files:
            if file['content_type'] == 'application/x-directory':
                if not os.path.exists(parent_path + ascii_string(file['name'])):
                    os.makedirs(parent_path + ascii_string(file['name']))
                if self.sync(queue, file['id'], parent_path + ascii_string(file['name']) + "/") == 0:  # delete empty folders
                    self.delete(file)
            else:
                org = {'file': file, 'parent_path': parent_path}
                part_size = round(file['size'] / 5)
                if part_size > config["maxPartSize"]:
                    part_size = config["maxPartSize"]
                elif part_size < config["minPartSize"]:
                    part_size = config["minPartSize"]

                if not file['id'] in complete.keys():
                    complete[file['id']] = {'parts': int(math.ceil(file['size'] / part_size)), 'started': datetime.now()}
                    total = 0
                    part_id = 0
                    while total < file['size']:
                        download_item = copy.deepcopy(org)
                        download_item['partId'] = copy.copy(part_id)
                        part_id += 1
                        download_item['range_start'] = total + 1 if total > 0 else 0
                        download_item['range_end'] = file['size'] if total + part_size >= file[
                            'size'] else total + part_size
                        total += part_size
                        queue.put(download_item)
                    complete[file['id']]['parts'] = copy.copy(part_id)

        return len(files)


class DownloadThread(threading.Thread):
    def __init__(self, queue, pdm):
        threading.Thread.__init__(self)
        self.queue = queue
        self.pdm = pdm

    def assemble_file(self, info):
        parent_path = ascii_string(info['parent_path'])
        file = info['file']
        tmp_name = "/tmp/" + ascii_string(file['name'])

        # check that all the parts are done
        total = 0

        logger.debug(complete[file['id']])

        logger.debug("Checking for parts of file {}".format(ascii_string(file['name'])))
        for i in range(complete[file['id']]['parts']):
            part_name = tmp_name + ".part.%i" % i
            if os.path.exists(part_name):
                total += os.path.getsize(part_name)
        logger.debug("Found {} of {}".format(total, file['size']))
        if total >= file['size']:
            ended = datetime.now()
            total_time = ended - complete[file['id']]['started']
            logger.info("Download Time: {}".format(total_time.total_seconds()))
            logger.info("Assembling {}".format(ascii_string(file['name'])))
            with open(tmp_name, 'wb') as f:
                for i in range(complete[file['id']]['parts']):
                    part_name = tmp_name + ".part.%i" % i
                    logger.debug("Appending part: {}".format(part_name))
                    with open(part_name, 'rb') as sf:
                        f.write(sf.read())
                    os.remove(part_name)
            logger.info("Moving file {} to {}".format(ascii_string(file['name']), config["syncDir"]))
            if not os.path.exists(parent_path):
                os.makedirs(parent_path)
            shutil.move(tmp_name, parent_path + ascii_string(file['name']))
            del complete[file['id']]
            if config["deleteAfterSync"]:
                logger.info("Deleting fie {} from put.io".format(ascii_string(file['name'])))
                self.pdm.delete(file)

    def download_file(self, info):
        parent_path = info['parent_path']
        file = info['file']
        logger.info("Downloading {}, Part: {}".format(parent_path + file['name'], info['partId']))
        tmp_name = "/tmp/" + ascii_string(file['name']) + ".part.%i" % info['partId']
        c = pycurl.Curl()
        c.setopt(c.URL, config["baseUrl"] + '/files/%s/download?oauth_token=%s' % (file['id'], self.pdm.access_token))
        mode = "wb"
        logger.info("[{}] Range: {}-{}".format(tmp_name, info['range_start'], info['range_end']))
        if os.path.exists(tmp_name):
            mode = "ab"
            info['range_start'] += os.path.getsize(tmp_name)
            logger.info("[{}] Adjusted Range: {}-{}".format(tmp_name, info['range_start'], info['range_end']))
        c.setopt(pycurl.RANGE, "%i-%i" % (info['range_start'], info['range_end']))
        c.setopt(c.FOLLOWLOCATION, True)
        with open(tmp_name, mode) as f:
            c.setopt(c.WRITEDATA, f)
            c.perform()
            c.close()
        self.assemble_file(info)

    def run(self):
        while True:
            # grabs host from queue
            item = self.queue.get()
            logger.debug("Queue Item: {}".format(item))
            if item is not None:
                self.download_file(item)

            # signals to queue job is done
            self.queue.task_done()
            time.sleep(1)


class TorrentFileEventHandler(FileSystemEventHandler):

    def __init__(self, pdm):
        self.pdm = pdm

    def process_new_event(self, event):
        logger.info("New Event: {}".format(event.src_path))
        time.sleep(5)
        if not event.is_directory:
            logger.info("Checking if {} is a download".format(event.src_path))
            if event.src_path not in UPLOADED:
                if (event.src_path.endswith(".magnet") and self.pdm.upload_magnet(event.src_path)) or (
                        event.src_path.endswith(".torrent") and self.pdm.upload(event.src_path)):
                    os.remove(event.src_path)
                    UPLOADED.append(event.src_path)

    def on_created(self, event):
        self.process_new_event(event)

    def on_modified(self, event):
        self.process_new_event(event)


def sync_it(pdm, queue):
    pdm.sync(queue)
    # queue.join() #wait on initial set to sync before starting over
    threading.Timer(180, partial(sync_it, pdm, queue)).start()


def main():
    pdm = PutIoAPI()
    for dirpath, dnames, fnames in os.walk(config['blackholeDir']):
        for f in fnames:
            full_name = os.path.join(dirpath, f)
            if (full_name.endswith(".magnet") and pdm.upload_magnet(full_name)) or (full_name.endswith(".torrent") and pdm.upload(full_name)):
                os.remove(full_name)

    observer = PollingObserver(timeout=60)
    observer.schedule(TorrentFileEventHandler(pdm), config['blackholeDir'], recursive=True)
    observer.start()

    download_queue = queue.Queue()
    for i in range(10):
        t = DownloadThread(download_queue, pdm)
        t.setDaemon(True)
        t.start()
    sync_it(pdm, download_queue)


if __name__ == "__main__":
    main()
