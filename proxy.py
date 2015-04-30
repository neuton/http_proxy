#!/usr/bin/env python

import socket, multiprocessing as mp, sys, time
from http import HttpRequest, HttpResponse
import select


def filter_request(request):
	return request


def filter_response(request, response):
	return response


def parse_host_port(string, default_host=None, default_port=None):
	host = port = None
	for arg in string.split():
		a = arg.split(':')
		try:
			port = int(a[-1])
		except ValueError:
			host = arg or host
		else:
			host = ':'.join(a[:-1]) or host
	return host or default_host, port or default_port


def conn_str(addr1, addr2):
	return '[%s:%i] <=> [%s:%i]' % (addr1[0], addr1[1], addr2[0], addr2[1])


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
	meta = http.get_meta()
	if http.get_version() == '1.1':
		return (not (meta.has_key('Connection') and meta['Connection'] == 'close')
			and not (meta.has_key('Proxy-Connection') and meta['Proxy-Connection'] == 'close'))
	else:
		return ((meta.has_key('Connection') and meta['Connection'] == 'keep-alive')
			or (meta.has_key('Proxy-Connection') and meta['Proxy-Connection'] == 'keep-alive'))


class CommunicationProcess(mp.Process):
	
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
		cp = CommunicationProcess(self.server_socket, self.client_socket, bufsize=self.bufsize)
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
		while not request.is_complete():
			r = self.client_socket.recv(self.bufsize)
			if not r:
				raise socket.error, 'Connection closed unexpectedly while getting request from client'
			request.append(r)
		return request
	
	def recv_response(self):
		response = HttpResponse()
		#while not response.is_complete()
		while True:														#
			r = self.server_socket.recv(self.bufsize)
			if not r:
				raise socket.error, 'Connection closed unexpectedly while getting response from server'
			#response.append(r)
			whats_left = response.append(r)								#
			response._body += whats_left								#
			a, _, _ = select.select([self.server_socket], [], [], 0.3)	# temporal (hopefully) hack
			if not a:													#
				break													#
		return response
	
	def send_response(self, response):
		self.client_socket.sendall(response.get_raw())
	
	def send_request(self, request):
		self.server_socket.sendall(request.get_raw())
	
	def set_server(self, host):
		c_addr = self.client_socket.getpeername()
		s_addr = parse_host_port(host, default_port=80)
		try:
			socket.gethostbyname(s_addr[0])
		except socket.error:
			resp = HttpResponse(sline='HTTP/1.1 502 DNS Lookup Failed', meta={'Connection': 'close'})
			self.send_response(resp)
			raise socket.error, 'DNS lookup failed'
		if s_addr == self.client_socket.getsockname():	# prevent self-nuke
			raise socket.error, "Can't proxy to self!"
		if socket_is_connected(self.server_socket):
			s_addr_0 = self.server_socket.getpeername()
			if s_addr == s_addr_0:
				return
			else:
				try_close_socket(self.server_socket)
				print '[-] ' + conn_str(c_addr, s_addr_0)
		self.server_socket = new_socket()
		self.server_socket.connect(s_addr)
		print '[+] ' + conn_str(c_addr, s_addr)
	
	def run(self):
		try:
			while True:
				req = self.recv_request()
				print '[>]', req.get_sline()
				if req.get_method() == 'CONNECT':
					self.set_server(req.get_path())
					resp = HttpResponse(sline='HTTP/1.1 200 OK')
					self.send_response(resp)
					self.run_tunnel()
					break
				headers = req.get_meta()
				if headers.has_key('Host'):
					host = headers['Host']
					self.set_server(host)
				elif not socket_is_connected(self.server_socket):
					raise socket.error, 'No "Host" header specified in request'
				self.send_request(filter_request(req))
				resp = self.recv_response()
				print '[<]', resp.get_sline()
				self.send_response(filter_response(req, resp))
				if not http_should_keep_alive(req) or not http_should_keep_alive(resp):
					break
		except KeyboardInterrupt:
			pass
		except Exception, e:
			print '[E]', e
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
		self.clean()
	
	def clean(self):
		try_close_socket(self.s)


def run():
	host, port = parse_host_port(' '.join(sys.argv[1:]), 'localhost', 8080)
	Server(host, port).run()


if __name__ == '__main__':
	run()
