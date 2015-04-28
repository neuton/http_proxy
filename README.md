HTTP proxy
==========
A simple filtering HTTP proxy server in Python.

Usage
----------
`python proxy.py [host] [port]`

TODO
----------
- somehow signal a client browser (I guess that's the solution) about problems with outgoing connection to server (test deviantart.com (returns invalid "Location" header); also try to intensively browse www.deviantart.com)
- actually, www.deviantart.com doesn't work anymore at all
- as well as www.wikipedia.com
- while en.wikipedia.org works only partially
- ...
- maybe make nice logging

Filtering usage example
----------
```python
#!/usr/bin/env python

from traceback import print_exc
from http import HttpRequest, HttpResponse
from proxy import parse_host_port
import proxy, sys

filter_hosts = ['example.com', 'example.org']

def filter_request(request):
	try:
		meta = request.get_meta()
		if meta.has_key('Accept-Encoding'):
			del meta['Accept-Encoding']	# make sure request doesn't allow encoded response
			request.set_meta(meta)
	except:
		print_exc()
	return request

def filter_response(request, response):
	try:
		if request.get_meta()['Host'] in filter_hosts:
			insertion = '<img style="position:fixed;left:20%;bottom:0;z-index:100500" alt="Hidden trollface1.png" src="//lurkmore.so/images/8/80/Hidden_trollface1.png" width="192" height="56">'
			meta = response.get_meta()
			if meta.has_key('Content-Type') and 'text/html' in meta['Content-Type'].lower():
				if meta.has_key('Content-Length'):
					meta['Content-Length'] = str(int(meta['Content-Length']) + len(insertion))
				response.set_meta(meta)
				body = response.get_body()
				find_tag = '<body>'
				i = body.lower().find(find_tag) + len(find_tag)
				response.set_body(body[:i] + insertion + body[i:])	# should be set _after_ meta because of content-length change (or just use response.set(...) to set both simultaneously)
				print '>-< insertion done'
	except:
		print_exc()
	return response

if __name__ == '__main__':
	proxy.filter_request = filter_request
	proxy.filter_response = filter_response
	proxy.Server(*parse_host_port(' '.join(sys.argv[1:]), 'localhost', 8080)).run()
```
