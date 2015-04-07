#!/usr/bin/env python

import socket, multiprocessing as mp, sys, time
from http import HttpRequest, HttpResponse


def filter_request(request):
	return request


def filter_response(response):
	return response


def parse_host_port(string, default_host=None, default_port=None):
	host = port = None
	for arg in string.split():
		a = arg.split(':')
		if len(a) == 2:
			host = a[0] or host
			port = int(a[1] or port)
		elif len(a) == 1:
			try:
				port = int(a[0])
			except ValueError:
				host = a[0]
	return host or default_host, port or default_port


def conn_str(addr1, addr2):
	return addr1[0] + ':' + str(addr1[1]) + ' --> ' + addr2[0] + ':' + str(addr2[1])


class CommunicationProcess(mp.Process):
	
	def __init__(self, s1, s2, bufsize=4096):
		mp.Process.__init__(self)
		self.s1, self.s2, self.bufsize = s1, s2, bufsize
	
	def run(self):
		while True:
			r = self.s1.recv(self.bufsize)
			if not r:
				break
			self.s2.sendall(r)


class ClientProcess(mp.Process):
	
	def __init__(self, s, si, bufsize=4096):
		mp.Process.__init__(self)
		self.s = s
		self.si = si
		self.so = None
		self.bufsize = bufsize
		self.host = self.port = None
	
	def run_tunnel(self):
		print '--- TCP tunnel established'
		cp = CommunicationProcess(self.so, self.si, bufsize=self.bufsize)
		cp.start()
		CommunicationProcess(self.si, self.so, bufsize=self.bufsize).run()
		cp.terminate()
	
	def run(self):
		try:
			while True:
				request = HttpRequest()
				while not request.is_complete():
					r = self.si.recv(self.bufsize)
					if not r:
						raise socket.error
					request.append(r)
				meta = request.get_meta()
				if meta.has_key('Host'):
					host, port = parse_host_port(meta['Host'], default_port=80)
					if (host, port) == self.s.getsockname():	# prevent self-nuke
						raise socket.error
					if (host, port) != (self.host, self.port):
						if self.so is not None:
							print '[-] ' + conn_str(self.si.getpeername(), (self.host, self.port))
							self.so.shutdown(socket.SHUT_RDWR)
							self.so.close()
						print '[+] ' + conn_str(self.si.getpeername(), (host, port))
						self.host, self.port = host, port
				elif self.so is None:
					raise socket.error
				self.so = socket.socket()
				self.so.connect((host, port))
				self.so.sendall(filter_request(request).get_raw())
				response = HttpResponse()
				while not response.is_complete():
					r = self.so.recv(self.bufsize)
					if not r:
						break
					response.append(r)
				self.si.sendall(filter_response(response).get_raw())
				if request.get_method() == 'CONNECT' and response.get_status_comment() == 'OK':
					self.run_tunnel()
				rmeta = response.get_meta()
				keep_alive = meta.has_key('Connection') and meta['Connection'] == 'keep-alive'
				keep_alive = keep_alive and rmeta.has_key('Connection') and rmeta['Connection'] == 'keep-alive'
				if not keep_alive:
					self.clean()
					break
		except KeyboardInterrupt:
			self.clean()
		except Exception as e:
			print e
			self.clean()
	
	def clean(self):
		if self.so is not None:
			print '[-] ' + conn_str(self.si.getpeername(), (self.host, self.port))
			try:
				self.so.shutdown(socket.SHUT_RDWR)
				self.so.close()
			except:
				pass
		try:
			self.si.shutdown(socket.SHUT_RDWR)
			self.si.close()
		except:
			pass


class ServerProcess(mp.Process):
	
	def __init__(self, host, port):
		mp.Process.__init__(self)
		self.host = host
		self.port = port
	
	def run(self):
		try:
			self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			self.s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
			self.s.bind((self.host, self.port))
			self.s.listen(5)
			print 'Listening ' + self.host + ':' + str(self.port) + '...'
			while True:
				cs, addr = self.s.accept()
				ClientProcess(self.s, cs).start()
		except:
			print 'Shutting down...'
			try:
				self.s.shutdown(socket.SHUT_RDWR)
				self.s.close()
			except:
				pass


class Server():
	
	def __init__(self, host, port):
		self.process = ServerProcess(host, port)
	
	def run(self):
		try:
			self.process.start()
			self.process.join()
		except KeyboardInterrupt:
			pass


if __name__ == '__main__':
	
	host, port = parse_host_port(' '.join(sys.argv[1:]), 'localhost', 8080)
	Server(host, port).run()
