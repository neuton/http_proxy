HTTP proxy
===========
A simple transparent HTTP proxy server in Python.

Usage
-----------
`./http_proxy.py [host] [port]`

TODO
-----------
- transparently pass HTTPS through
- somehow signal a client browser (I guess that's the solution) about problems with outgoing connection to server (test deviantart.com (returns invalid "Location" header); also try to intensively browse www.deviantart.com)
- refactor all this mess some day

Another usage example
-----------
```python
#!/usr/bin/env python

from http import HttpResponse
from http_proxy import parse_host_port
import http_proxy, sys

def filter_response(caddr, saddr, response):
	if '.'.join(saddr[0].split('.')[-2:]) == 'example.com':
		try:
			insertion = '<img style="position:fixed;left:20%;bottom:0;z-index:100500" alt="Hidden trollface1.png" src="//lurkmore.so/images/8/80/Hidden_trollface1.png" width="192" height="56">'
			meta = response.get_meta()
			if meta.has_key('Content-Type') and 'text/html' in meta['Content-Type'].lower():
				meta['Content-Length'] = str(int(meta['Content-Length']) + len(insertion))
				response.set_meta(meta)
				body = response.get_body()
				i = body.lower().rfind('</html>')
				response.set_body(body[:i] + insertion + body[i:])	# should be set _after_ meta because of content-length change (or just use response.set(...) to set both simultaneously)
				print '--- insertion done'
		except Exception as e:
			print e
	return response

if __name__ == '__main__':
	http_proxy.filter_response = filter_response
	http_proxy.Server(*parse_host_port(' '.join(sys.argv[1:]), 'localhost', 8080)).run()
```
