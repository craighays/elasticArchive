#!/bin/bash
here=`pwd`
elasticServer=http://elasticsearch.local:9200/mitmproxy/_doc


docker run --rm -it -p 8080:8080 -v $here/.mitmproxy:/home/mitmproxy/.mitmproxy -v $here/scripts:/scripts/ craighays/mitmproxy-pythonrequests mitmdump -s /scripts/elasticArchive.py --set elasticsearch_URL=$elasticServer
#visit http://mitm.it to install cert in browser.
