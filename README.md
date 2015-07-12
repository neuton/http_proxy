HTTP proxy
==========
A simple filtering HTTP proxy server in Python.

Usage
----------
`python proxy.py [host] [port]`

TODO
----------
- close sockets properly when required
- make nice logging
- add some initial requests modification to be transparent for a server (test en.wikipedia.org, arxiv.org)
- add addresses filtering for HTTPS

Filtering usage example
----------
```python
#!/usr/bin/env python

from traceback import print_exc
from http import *
import proxy

filter_hosts = ['example.com', 'example.org']

def filter_request(request):
	try:
		meta = request.get_meta()
		if 'Accept-Encoding' in meta:
			del meta['Accept-Encoding']	# make sure request doesn't allow encoded response
			request.set_meta(meta)
	except:
		print_exc()
	return request

def filter_response(request, response):
	insertion = '<img style="position:fixed;left:20%;bottom:0;z-index:100500" alt="Hidden trollface1.png" src="//lurkmore.so/images/8/80/Hidden_trollface1.png" width="192" height="56">'
	try:
		if request.get_meta().get('Host') in filter_hosts:
			meta = response.get_meta()
			content_type = meta.get('Content-Type')
			if content_type and 'text/html' in content_type.lower() and not 'Content-Encoding' in meta:
				meta['Content-Length'] = str(int(meta['Content-Length']) + len(insertion))
				response.set_meta(meta)
				body = response.get_body()
				i = body.lower().rfind('</body>')
				response.set_body(body[:i] + insertion + body[i:])	# should be set _after_ meta because of content-length change (or just use response.set(...) to set both simultaneously)
				print '>-< insertion done'
	except:
		print_exc()
	return response

if __name__ == '__main__':
	proxy.filter_request = filter_request
	proxy.filter_response = filter_response
	proxy.run()
```
