class Http():
	
	def __init__(self, *args, **kwargs):
		self.clean()
		self.set(*args, **kwargs)
	
	def clean(self):
		self._sline = ''
		self._headers = ''
		self._body = ''
		self._sline_is_complete = False
		self._meta_is_complete = False
		self._is_complete = False
		self._sep1 = '\r\n'
		self._sep2 = '\r\n\r\n'
	
	def append(self, content):
		if not self._sline_is_complete:
			self._sline += content
			sep = ''
			if '\r\n' in self._sline:
				sep = '\r\n'
			elif '\n' in self._sline:
				sep = '\n'
			if sep:
				s = self._sline.split(sep)
				self._sline = s[0]
				content = sep.join(s[1:])
				self._sep1 = sep
				self._sline_is_complete = True
			else:
				content = ''
		if not self._meta_is_complete and self._sline_is_complete:
			self._headers += content
			sep = ''
			if '\r\n\r\n' in self._headers:
				sep = '\r\n\r\n'
			elif '\n\n' in self._headers:
				sep = '\n\n'
			if sep:
				s = self._headers.split(sep)
				self._headers = s[0]
				content = sep.join(s[1:])
				self._sep2 = sep
				self._meta_is_complete = True
				meta = self.get_meta()
				if meta.has_key('Content-Length'):
					self._body_size = int(meta['Content-Length'])
				else:
					self._is_complete = True
			else:
				content = ''
		if not self._is_complete and self._meta_is_complete:
			i = self._body_size - len(self._body)
			if i > len(content):
				self._body += content
				content = ''
			else:
				self._body += content[:i]
				content = content[i:]
				self._is_complete = True
		return content
	
	def set_raw(self, content):
		self.clean()
		self.append(content)
	
	def set(self, raw=None, sline=None, meta=None, body=None):
		if raw:
			self.set_raw(raw)
		else:
			if sline:
				self._sline = sline
				self._sline_is_complete = True
			if meta:
				self._headers = self._sep1.join([key + ': ' + value for key, value in meta.iteritems()])
				self._sline_is_complete = True
				self._meta_is_complete = True
			if body:
				self._body = body
				self._sline_is_complete = True
				self._meta_is_complete = True
				self._is_complete = True
			self.set_raw(self.get_raw())
	
	def set_sline(self, sline):
		self.set(sline=sline)
	
	def set_meta(self, meta):
		self.set(meta=meta)
	
	def set_body(self, body):
		self.set(body=body)
	
	def get_raw(self):
		if not self._sline_is_complete:
			return self._sline
		elif not self._meta_is_complete:
			return self._sline + self._sep1 + self._headers
		else:
			return self._sline + self._sep1 + self._headers + self._sep2 + self._body
	
	def get_sline(self):
		return self._sline
	
	def get_body(self):
		return self._body
	
	def get_meta(self):
		if self._sline_is_complete:
			return dict([[a[0], ':'.join(a[1:]).strip()] for a in [l.split(':') for l in self._headers.split(self._sep1)]])
		else:
			return dict()
	
	def sline_is_complete(self):
		return self._sline_is_complete
	
	def meta_is_complete(self):
		return self._meta_is_complete
	
	def is_complete(self):
		return self._is_complete


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


class HttpResponse(Http):
	
	def get_version(self):
		return self.get_sline().split()[0].split('/')[1]
	
	def get_status(self):
		return int(self.get_sline().split()[1])
	
	def get_status_comment(self):
		return ' '.join(self.get_sline().split(' ')[2:])
