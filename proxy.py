#!/usr/bin/env python

"""
Usage:
  proxy.py [-tT TARGET] [HOST | PORT | HOST PORT]
  proxy.py (-h | --help)

Options:
  -h --help                  show this help message
  -t --transparent           transparent proxy mode
  -T=TARGET --target=TARGET  specify fixed target host to proxy to
"""

from docopt import docopt

import socket, multiprocessing as mp, sys, time
from http import HttpRequest, HttpResponse


def d(func):
	globals()[func.__name__] = func
	return func


def prefilter_request(request):
	return request


def filter_request(request):
	return request


def filter_response(request, response):
	return response


def conn_str(addr1, addr2):
	return '[%s:%i] <=> [%s:%i]' % (addr1 + addr2)


def new_socket():
	s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
	return s


def socket_is_connected(s):
	if s is not None:
		try:
			s.getpeername()
			return True
		except socket.error:
			return False


def try_close_socket(s):
	if s is not None:
		try:
			s.shutdown(socket.SHUT_RDWR)
			s.close()
		except socket.error:
			pass


def http_should_keep_alive(http):
	meta = http.meta
	if http.version == '1.1':
		return not (meta.get('Connection') == 'close' or meta.get('Proxy-Connection') == 'close')
	else:
		return meta.get('Connection') == 'keep-alive' or meta.get('Proxy-Connection') == 'keep-alive'


class TunnelProcess(mp.Process):
	
	def __init__(self, s1, s2, bufsize=65535):
		mp.Process.__init__(self)
		self.s1, self.s2, self.bufsize = s1, s2, bufsize
	
	def run(self):
		try:
			while True:
				r = self.s1.recv(self.bufsize)
				if not r:
					break
				self.s2.sendall(r)
		except:
			pass


class ClientProcess(mp.Process):
	
	def __init__(self, client_socket, bufsize=65535):
		mp.Process.__init__(self)
		self.client_socket = client_socket
		self.server_socket = None
		self.bufsize = bufsize
	
	def run_tunnel(self):
		cp = TunnelProcess(self.server_socket, self.client_socket, bufsize=self.bufsize)
		cp.start()
		try:
			while True:
				r = self.client_socket.recv(self.bufsize)
				if not r:
					break
				self.server_socket.sendall(r)
		except socket.error:
			pass
		cp.terminate()
	
	def recv_request(self):
		request = HttpRequest()
		while not request.is_complete:
			r = self.client_socket.recv(self.bufsize)
			if not r:
				raise socket.error, 'Connection closed unexpectedly while getting request from client'
			request.append(r)
		return request
	
	def recv_response(self):
		response = HttpResponse()
		while not response.is_complete:
			r = self.server_socket.recv(self.bufsize)
			if not r:
				raise socket.error, 'Connection closed unexpectedly while getting response from server'
			response.append(r)
		return response
	
	def send_response(self, response):
		self.client_socket.sendall(response.raw)
	
	def send_request(self, request):
		self.server_socket.sendall(request.raw)
	
	def set_server(self, host):
		c_addr = self.client_socket.getpeername()
		s_h, s_p = (host.split(':') + [80])[:2]
		s_addr = s_h, int(s_p)
		try:
			ip = socket.gethostbyname(s_addr[0])
		except socket.error:
			resp = HttpResponse(sline='HTTP/1.1 502 DNS Lookup Failed', meta={'Connection': 'close'})
			self.send_response(resp)
			raise socket.error, 'DNS lookup failed'
		if (ip, s_addr[1]) == self.client_socket.getsockname():	# prevent self-nuke
			raise socket.error, "Can't proxy to self!"
		if socket_is_connected(self.server_socket):
			s_addr_0 = self.server_socket.getpeername()
			if s_addr == s_addr_0:
				return
			else:
				try_close_socket(self.server_socket)
				print '[-] ' + conn_str(c_addr, s_addr_0)
		self.server_socket = new_socket()
		try:
			self.server_socket.connect(s_addr)
		except socket.error:
			# should probably change behaviour for transparent usage scenario
			resp = HttpResponse(sline='HTTP/1.1 502 Connection Refused', meta={'Connection': 'close'})
			self.send_response(resp)
			raise socket.error, 'Connection Refused'
		print '[+] ' + conn_str(c_addr, (ip, s_addr[1]))
	
	def run(self):
		try:
			while True:
				req = prefilter_request(self.recv_request())
				print '[>]', req.sline
				if config['proxy'] and req.method == 'CONNECT':
					if config['target']:
						self.set_server(config['target'])
					else:
						self.set_server(req.path)
					resp = HttpResponse(sline='HTTP/1.1 200 OK')
					self.send_response(resp)
					self.run_tunnel()
					break
				if config['target']:
					self.set_server(config['target'])
				elif req.method == 'CONNECT':
					raise socket.error, 'No TARGET specified for proxying "CONNECT" method'
				elif 'Host' in req.meta:
					self.set_server(req.meta['Host'])
				elif not socket_is_connected(self.server_socket):
					raise socket.error, 'No "Host" header specified in request'
				self.send_request(filter_request(req))
				resp = self.recv_response()
				print '[<]', resp.sline
				self.send_response(filter_response(req, resp))
				if req.method == 'CONNECT' and resp.status == 'OK':
					self.run_tunnel()
					break
				if not http_should_keep_alive(req) or not http_should_keep_alive(resp):
					break
		except KeyboardInterrupt:
			pass
		except Exception, e:
			print '[E]', e
		finally:
			self.clean()
	
	def clean(self):
		if socket_is_connected(self.client_socket) and socket_is_connected(self.server_socket):
			print '[-] ' + conn_str(self.client_socket.getpeername(), self.server_socket.getpeername())
		try_close_socket(self.client_socket)
		try_close_socket(self.server_socket)


class Server(mp.Process):
	
	def __init__(self, host, port):
		mp.Process.__init__(self)
		self.host = host
		self.port = port
	
	def run(self):
		try:
			self.s = new_socket()
			self.s.bind((self.host, self.port))
			self.s.listen(5)
			print 'Listening ' + self.host + ':' + str(self.port) + '...'
			while True:
				cs, addr = self.s.accept()
				ClientProcess(cs).start()
		except KeyboardInterrupt:
			pass
		except Exception as e:
			print e
		finally:
			self.clean()
	
	def clean(self):
		try_close_socket(self.s)


def try_reverse_host_port(host, port):
	try:
		int(host)
	except (ValueError, TypeError):
		return host, port
	else:
		return port, host


config = {}


def run():
	args = docopt(__doc__.replace('proxy.py', sys.argv[0]))
	host, port = try_reverse_host_port(args['HOST'], args['PORT'])
	config['proxy'] = not args['--transparent']
	config['target'] = args['--target']
	Server(host or 'localhost', int(port or 8080)).run()


if __name__ == '__main__':
	run()
