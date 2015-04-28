#!/usr/bin/env python

#from traceback import print_exc
import socket, multiprocessing as mp, sys, time
from http import HttpRequest, HttpResponse


valid_request_methods = ['OPTIONS', 'GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'TRACE', 'CONNECT']


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


def conn_str(addr1, addr2, sep=' --> '):
	return addr1[0] + ':' + str(addr1[1]) + sep + addr2[0] + ':' + str(addr2[1])


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
		return not (meta.has_key('Connection') and meta['Connection'] == 'close')
	else:
		return meta.has_key('Connection') and meta['Connection'] == 'keep-alive'


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
		cp.join()
	
	def recv_http(self, s, http):
		while not http.is_complete():
			r = s.recv(self.bufsize)
			if not r:
				raise socket.error, 'Connection closed unexpectedly'
			http.append(r)
		return http
	
	def recv_request(self):
		s = self.client_socket
		r = s.recv(self.bufsize)
		if not r:
			raise socket.error, 'Connection closed unexpectedly'
		m = r.split()[0].upper()
		if m not in map(lambda a: a[:len(m)], valid_request_methods): # if request is definitely invalid
			return None
		request = HttpRequest()
		request.append(r)
		return self.recv_http(s, request)
	
	def recv_response(self):
		s = self.server_socket
		r = s.recv(self.bufsize)
		if not r:
			raise socket.error, 'Connection closed unexpectedly'
		#m = r.split()[0].upper()
		#if m[:4] != 'HTTP'[:len(m)]: # if response is definitely invalid
		#	return None
		response = HttpResponse()
		response.append(r)
		return self.recv_http(s, response)
	
	def send_http(self, s, http):
		s.sendall(http.get_raw())
	
	def send_response(self, response):
		self.send_http(self.client_socket, response)
	
	def send_request(self, request):
		self.send_http(self.server_socket, request)
	
	def set_server(self, host):
		c_addr = self.client_socket.getpeername()
		s_addr = parse_host_port(host, default_port=80)
		if s_addr == self.client_socket.getsockname():	# prevent self-nuke
			raise socket.error, "Can't proxy to self!"
		if socket_is_connected(self.server_socket):
			s_addr_0 = self.server_socket.getpeername()
			if s_addr != s_addr_0:
				try_close_socket(self.server_socket)
				print '[-] ' + conn_str(c_addr, s_addr_0)
		self.server_socket = new_socket()
		self.server_socket.connect(s_addr)
		print '[+] ' + conn_str(c_addr, s_addr)
	
	def run(self):
		try:
			while True:
				req = self.recv_request()
				if req is None:
					raise socket.error, 'Invalid HTTP request'
				if req.get_method() == 'CONNECT':
					self.send_response(HttpResponse(raw='HTTP/1.1 200 OK\r\n\r\n'))
					self.set_server(req.get_path())
					self.run_tunnel()
					break
				headers = req.get_meta()
				if headers.has_key('Host'):
					try:
						socket.gethostbyname(headers['Host'])
					except socket.error:
						self.send_response(HttpResponse(raw='HTTP/1.1 502 DNS Lookup Failed\r\nConnection: close\r\n\r\n'))
						break
					self.set_server(headers['Host'])
				elif not socket_is_connected(self.server_socket):
					raise socket.error, 'No "Host" header specified in request'
				self.send_request(filter_request(req))
				resp = self.recv_response()
				self.send_response(filter_response(req, resp))
				if not http_should_keep_alive(req) or not http_should_keep_alive(resp):
					break
		except KeyboardInterrupt:
			pass
		except Exception, e:
			if str(e).strip():
				print e
			#print_exc()
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
			if str(e).strip():
				print e
		self.clean()
	
	def clean(self):
		try_close_socket(self.s)


if __name__ == '__main__':
	
	host, port = parse_host_port(' '.join(sys.argv[1:]), 'localhost', 8080)
	Server(host, port).run()
