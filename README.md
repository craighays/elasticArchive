# elasticArchive
An extension to mitmproxy to dump all proxied web traffic to elasticsearch where you can keep it forever (or until you run out of disk space)

My goal for this project was to create an open source way to proxy all of your web traffic and log it for analysis at a later date. There are 
commerical tools out there that will do this but I wanted to make one around the mitmproxy intercepting proxy to allow me to alter traffic on 
the fly as well as analyse it at a later date.

My setup for this is:
Browser -> Burp Suite -> mitmdump elasticArchive -> web

Based on:
- https://github.com/mitmproxy/mitmproxy/blob/master/examples/complex/har_dump.py
- https://github.com/mitmproxy/mitmproxy/blob/11da2f799c1189ea2a6c687ce55d23a28ab29236/examples/complex/jsondump.py

# How it works
This app: 
- runs docker
- downloads the craighays/mitmproxy-pythonrequests image
- mounts a .mitmproxy folder to keep your certs and config in
- mounts the local scripts folder to /scripts/ to include the elasticArchive.py addon
- binds the proxy to port 8080 on the host running it
- forwards all traffic to $elasticServer as configured in start.sh
- storeBinaryContent:true converts binary content to base64 to record it in elasticsearch. false... doesn't.
  plain text content is always stored in elasticsearch. Binray content like images, video, etc. is all pretty big
  my preference is to leave storeBinaryContent to false so only log text based content.

If you want, you can create .mitmproxy/config.yaml and add your own settings. I find using the start script
to work well enough for me.

      cat > .mitmproxy/config.yaml <<EOF
      elasticsearch_URL: "http://link.to.your.server:9200/mitmproxy/_doc
      
      # Optional
      # storeBinaryContent: true
      # elastic_username: "user"
      # elastic_password: "password"
      EOF

# Requirements
- Docker running locally
- An elasticsearch server running somewhere reachable from your docker host

# Installation
chmod +x start.sh

# Usage
```docker-compose up -d```

This will start all three required docker containers:
* Elasticsearch:9200:9200, 9300:9300
* Kibana:5601:5601
* mitmproxy:8008:8080 (Burp suite usually runs on 8080)

