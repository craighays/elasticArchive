"""
This script serializes the entire traffic dump, including websocket traffic,
as JSON, and either sends it to an elasticsearch endpoint for permenant storage.

Unlike some plugins, this one sends all requests and responses to elasticsearch
in real-time.

This script is based on the original mitmproxy scripts jsondump.py and har_dump.py

Usage:

    mitmproxy
        -s elasticArchive.py
        --set elasticsearch_URL=http://<your elasticsearch server>:9200/mitmproxy/_doc 

        --set encodecontent=false
        OR
        --set encodecontent=true

        OPTIONAL
        --set elastic_username=<username>
        --set elastic_password=<password>

You can also put those --set options inside ~/.mitmproxy/config.yaml but I've never been
able to get that to work when I run it through docker.
"""

from threading import Thread
from queue import Queue
import base64
import json
import requests

from mitmproxy import ctx

HTTP_WORKERS = 10

class elasticArchive:
    """
    elasticArchive performs JSON serialization and some extra processing
    for out-of-the-box Elasticsearch support, and then either writes
    the result to a file or sends it to a URL.
    """
    def __init__(self):
        self.transformations = None
        self.encode = None
        self.url = None
        self.auth = None
        self.queue = Queue()
        print("elasticArchive loaded")

    def done(self):
        self.queue.join()

    fields = {
        'timestamp': (
            ('error', 'timestamp'),

            ('request', 'timestamp_start'),
            ('request', 'timestamp_end'),

            ('response', 'timestamp_start'),
            ('response', 'timestamp_end'),

            ('client_conn', 'timestamp_start'),
            ('client_conn', 'timestamp_end'),
            ('client_conn', 'timestamp_tls_setup'),

            ('server_conn', 'timestamp_start'),
            ('server_conn', 'timestamp_end'),
            ('server_conn', 'timestamp_tls_setup'),
            ('server_conn', 'timestamp_tcp_setup'),
        ),
        'ip': (
            ('server_conn', 'source_address'),
            ('server_conn', 'ip_address'),
            ('server_conn', 'address'),
            ('client_conn', 'address'),
        ),
        'ws_messages': (
            ('messages', ),
        ),
        'headers': (
            ('request', 'headers'),
            ('response', 'headers'),
        ),
        'content': (
            ('request', 'content'),
            ('response', 'content'),
        ),
    }

    def _init_transformations(self):
        self.transformations = [
            {
                'fields': self.fields['headers'],
                'func': dict,
            },
            {
                'fields': self.fields['timestamp'],
                'func': lambda t: int(t * 1000),
            },
            {
                'fields': self.fields['ip'],
                'func': lambda addr: {
                    'host': addr[0].replace('::ffff:', ''),
                    'port': addr[1],
                },
            },
            {
                'fields': self.fields['ws_messages'],
                'func': lambda ms: [{
                    'type': m[0],
                    'from_client': m[1],
                    'content': base64.b64encode(bytes(m[2], 'utf-8')) if self.encode else m[2],
                    'timestamp': int(m[3] * 1000),
                } for m in ms],
            }
        ]

        if self.encode:
            self.transformations.append({
                'fields': self.fields['content'],
                'func': base64.b64encode,
            })

    @staticmethod
    def transform_field(obj, path, func):
        """
        Apply a transformation function `func` to a value
        under the specified `path` in the `obj` dictionary.
        """
        for key in path[:-1]:
            if not (key in obj and obj[key]):
                return
            obj = obj[key]
        if path[-1] in obj and obj[path[-1]]:
            obj[path[-1]] = func(obj[path[-1]])

    @classmethod
    def convert_to_strings(cls, obj):
        """
        Recursively convert all list/dict elements of type `bytes` into strings.
        """
        if isinstance(obj, dict):
            return {cls.convert_to_strings(key): cls.convert_to_strings(value)
                    for key, value in obj.items()}
        elif isinstance(obj, list) or isinstance(obj, tuple):
            return [cls.convert_to_strings(element) for element in obj]
        elif isinstance(obj, bytes):
            return str(obj)[2:-1]
        return obj

    def worker(self):
        while True:
            frame = self.queue.get()
            self.dump(frame)
            self.queue.task_done()

    def dump(self, frame):
        """
        Transform and dump (write / send) a data frame.
        """
        for tfm in self.transformations:
            for field in tfm['fields']:
                self.transform_field(frame, field, tfm['func'])
        frame = self.convert_to_strings(frame)

        print("Sending frame to Elasticsearch")
        # If you need to debug this, print/log frame and result as it will show you 
        # what wasc sent and what errors you got back. This generates a lot of noise though...

        print('Frame= %s' % frame)
        result = requests.post(self.url, json=frame, auth=(self.auth or None))
        print(result.text)


    @staticmethod
    def load(loader):
        """
        Extra options to be specified in `~/.mitmproxy/config.yaml`.
        """
        loader.add_option('encodecontent', bool, False,
                          'Encode content as base64.')
        loader.add_option('elasticsearch_URL', str, 'http://localhost:9200/mitmproxy/_doc',
                          'Elasticsearch resource path including index (mitmproxy) and type (usually _doc) ')
        loader.add_option('elastic_username', str, '',
                          'Basic auth username for URL destinations.')
        loader.add_option('elastic_password', str, '',
                          'Basic auth password for URL destinations.')

    def configure(self, _):
        """
        Determine the destination type and path, initialize the output
        transformation rules.
        """
        self.encode = ctx.options.encodecontent
        print('Encoding set to %s' % self.encode)
        print('Sending all data frames to %s' % ctx.options.elasticsearch_URL)
        if ctx.options.elasticsearch_URL.startswith('http'):
            self.url = ctx.options.elasticsearch_URL
            ctx.log.info('Sending all data frames to %s' % self.url)
            if ctx.options.elastic_username and ctx.options.elastic_password:
                self.auth = (ctx.options.elastic_username, ctx.options.elastic_password)
                ctx.log.info('HTTP Basic auth enabled.')
        else:
            print("Invalid elasticsearch_URL. Exiting.")
            exit()


        self._init_transformations()

        for i in range(HTTP_WORKERS):
            t = Thread(target=self.worker)
            t.daemon = True
            t.start()

    def response(self, flow):
        """
        Dump request/response pairs.
        """
        self.queue.put(flow.get_state())

    def error(self, flow):
        """
        Dump errors.
        """
        self.queue.put(flow.get_state())

    def websocket_end(self, flow):
        """
        Dump websocket messages once the connection ends.

        Alternatively, you can replace `websocket_end` with
        `websocket_message` if you want the messages to be
        dumped one at a time with full metadata. Warning:
        this takes up _a lot_ of space.
        """
        self.queue.put(flow.get_state())

    def websocket_error(self, flow):
        """
        Dump websocket errors.
        """
        self.queue.put(flow.get_state())


addons = [elasticArchive()]  # pylint: disable=invalid-name