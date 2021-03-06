import re

class Http(object):
	
	def __init__(self, *args, **kwargs):
		self.clean()
		self.set(*args, **kwargs)
	
	def __str__(self):
		return self.raw
	
	def clean(self):
		self._sline = ''
		self._headers = ''
		self._body = ''
		self._sline_is_complete = False
		self._meta_is_complete = False
		self._is_complete = False
		self._chunk_size = 0
		self._chunk_size_s = ''
	
	def append(self, content):
		if not self._sline_is_complete:
			s = re.split('\r\n|\n', (self._sline + content), 1)
			self._sline, content = (s + [''])[:2]
			if len(s) == 2:
				self._sline_is_complete = True
		if self._sline_is_complete and not self._meta_is_complete:
			s = re.split('\r\n\r\n|\n\n', (self._headers + content), 1)
			self._headers, content = (s + [''])[:2]
			if len(s) == 2:
				self._meta_is_complete = True
			if self._headers and (self._headers[:2] == '\r\n' or self._headers[0] == '\n'):
				self._meta_is_complete = True
				self._is_complete = True
				content, self._headers = re.split('\r\n|\n', self._headers, 1)[1], ''
		if self._meta_is_complete and not self._is_complete:
			if 'chunked' in (self.get_meta().get('Transfer-Encoding') or '').lower():	# RFC 7230 sec. 4.1
				while content:
					if self._chunk_size == 0:
						s = re.split('\r\n|\n', (self._chunk_size_s + content).lstrip(), 1)
						self._chunk_size_s, content = (s + [''])[:2]
						if len(s) == 2:
							self._chunk_size = int(self._chunk_size_s.split()[0], 16)
							self._chunk_size_s = ''
							if self._chunk_size == 0:
								self._chunk_size = -1
					if self._chunk_size > 0:
						cs = self._chunk_size
						self._chunk_size -= min(cs, len(content))
						self._body += content[:cs]
						content = content[cs:]
					if self._chunk_size == -1:	# trailer-part
						meta = self.get_meta()
						tes = [e.strip().lower() for e in meta['Transfer-Encoding'].split(',')].remove('chunked')
						if tes:
							meta['Transfer-Encoding'] = ','.join(tes)
						else:
							del meta['Transfer-Encoding']
						meta['Content-Length'] = str(len(self._body))
						self.set_meta(meta)
						self._meta_is_complete = False
						self._is_complete = True
						content = self.append('\r\n' + content)
						break
			else:
				i = int(self.get_meta().get('Content-Length') or 0) - len(self._body)
				if i <= len(content):
					self._is_complete = True
				self._body += content[:i]
				content = content[i:]
		return content
	
	def set_raw(self, content):
		self.clean()
		self.append(content)
	
	def set(self, raw=None, sline=None, meta=None, body=None):
		if raw:
			self.set_raw(raw)
		else:
			if body:
				self._body = body
				self._sline_is_complete = True
				self._meta_is_complete = True
				self._is_complete = True
			if meta:
				self._headers = '\r\n'.join([key + ': ' + value for key, value in meta.iteritems()])
				self._sline_is_complete = True
				self._meta_is_complete = True
			if sline:
				self._sline = sline
				self._sline_is_complete = True
				if not self._headers:
					self._meta_is_complete = True
			self.set_raw(self.get_raw())
	
	def set_sline(self, sline):
		self.set(sline=sline)
	
	def set_meta(self, meta):
		self.set(meta=meta)
	
	def set_body(self, body):
		self.set(body=body)
	
	def get_raw(self):
		r = self._sline
		if self._headers:
			r += '\r\n' + self._headers
		if self._meta_is_complete:
			r += '\r\n\r\n' + self._body
		return r
	
	def get_sline(self):
		return self._sline
	
	def get_body(self):
		return self._body
	
	def get_meta(self):
		if self._sline_is_complete and self._headers:
			return dict([[a.strip() for a in l.split(':', 1)] for l in re.split('\r\n|\n', self._headers)])
		else:
			return dict()
	
	@property
	def sline_is_complete(self):
		return self._sline_is_complete
	
	@property
	def meta_is_complete(self):
		return self._meta_is_complete
	
	@property
	def is_complete(self):
		return self._is_complete
	
	raw = property(get_raw, set_raw)
	sline = property(get_sline, set_sline)
	meta = property(get_meta, set_meta)
	body = property(get_body, set_body)


class HttpRequest(Http):
	
	def get_method(self):
		return self.get_sline().split()[0].upper()
	
	def get_path(self):
		return self.get_sline().split()[1]
	
	def get_version(self):
		s = self.get_sline().split()
		if len(s) > 2:
			return s[2].split('/')[1]
		else:
			return '0.9'
	
	method = property(get_method)
	path = property(get_path)
	version = property(get_version)


class HttpResponse(Http):
	
	def get_version(self):
		return self.get_sline().split()[0].split('/')[1]
	
	def get_status(self):
		return int(self.get_sline().split()[1])
	
	def get_status_comment(self):
		return self.get_sline().split(maxsplit=2)[2]
	
	version = property(get_version)
	status = property(get_status)
	status_comment = property(get_status_comment)
