# Copyright (c) 2006,2007 Mitch Garnaat http://garnaat.org/
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish, dis-
# tribute, sublicense, and/or sell copies of the Software, and to permit
# persons to whom the Software is furnished to do so, subject to the fol-
# lowing conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABIL-
# ITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT
# SHALL THE AUTHOR BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, 
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.

import urllib
import mimetypes
import md5
import StringIO
import base64
import boto
import boto.utils
from boto.exception import S3ResponseError, S3DataError
from boto.s3.user import User

class Key:

    def __init__(self, bucket=None):
        self.bucket = bucket
        self.metadata = {}
        self.content_type = 'application/octet-stream'
        self.filename = None
        self.etag = None
        self.key = None
        self.last_modified = None
        self.owner = None
        self.storage_class = None
        self.md5 = None
        self.base64md5 = None

    def startElement(self, name, attrs, connection):
        if name == 'Owner':
            self.owner = User(self)
            return self.owner
        else:
            return None

    def endElement(self, name, value, connection):
        if name == 'Key':
            self.key = value
        elif name == 'ETag':
            self.etag = value
        elif name == 'LastModified':
            self.last_modified = value
        elif name == 'Size':
            self.size = value
        elif name == 'StorageClass':
            self.storage_class = value
        elif name == 'Owner':
            pass
        else:
            setattr(self, name, value)

    def get_metadata(self, key):
        return self.metadata[key]

    def set_metadata(self, key, value):
        self.metadata[key] = value
    
    def send_file(self, fp, headers=None):
        http_conn = self.bucket.connection.connection
        if not headers:
            headers = {}
        headers['Content-MD5'] = self.base64md5
        if headers.has_key('Content-Type'):
            self.content_type = headers['Content-Type']
        elif hasattr(fp, 'name'):
            self.content_type = mimetypes.guess_type(fp.name)[0]
            headers['Content-Type'] = self.content_type
        else:
            headers['Content-Type'] = self.content_type
        headers['Content-Length'] = self.size
        final_headers = boto.utils.merge_meta(headers, self.metadata);
        path = '/%s/%s' % (self.bucket.name, self.key)
        path = urllib.quote(path)
        self.bucket.connection.add_aws_auth_header(final_headers, 'PUT', path)
        #the prepending of the protocol and true host must occur after
        #the authentication header is computed (line above). The
        #authentication includes the path, which for authentication is
        #only the bucket and key
        if self.bucket.connection.use_proxy:
            path = self.bucket.connection.prefix_proxy_to_path(path)
        http_conn.putrequest('PUT', path)
        for key in final_headers:
            http_conn.putheader(key,final_headers[key])
        http_conn.endheaders()
        try:
            l = fp.read(4096)
            while len(l) > 0:
                http_conn.send(l)
                l = fp.read(4096)
            response = http_conn.getresponse()
            body = response.read()
        except Exception, e:
            self.bucket.connection.make_http_connection()
            print 'Caught an unexpected exception'
            raise e
        if response.status != 200:
            raise S3ResponseError(response.status, response.reason)
        self.etag = response.getheader('etag')
        if self.etag != '"%s"'  % self.md5:
            raise S3DataError('Injected data did not return correct MD5')

    def _compute_md5(self, fp):
        m = md5.new()
        s = fp.read(4096)
        while s:
            m.update(s)
            s = fp.read(4096)
        self.md5 = m.hexdigest()
        self.base64md5 = base64.b64encode(m.digest())
        self.size = fp.tell()
        fp.seek(0)

    def set_contents_from_file(self, fp, headers=None):
        if self.bucket != None:
            if self.md5 == None:
                self._compute_md5(fp)
            self.send_file(fp, headers)

    def set_contents_from_filename(self, filename, headers=None):
        fp = open(filename, 'rb')
        self.set_contents_from_file(fp, headers)
        fp.close()

    def set_contents_from_string(self, s, headers=None):
        fp = StringIO.StringIO(s)
        self.set_contents_from_file(fp, headers)
        fp.close()

    def get_file(self, fp, headers={}):
        http_conn = self.bucket.connection.connection
        final_headers = boto.utils.merge_meta(headers, {})
        path = '/%s/%s' % (self.bucket.name, self.key)
        path = urllib.quote(path)
        self.bucket.connection.add_aws_auth_header(final_headers, 'GET', path)
        #the prepending of the protocol and true host must occur after
        #the authentication header is computed (line above). The
        #authentication includes the path, which for authentication is
        #only the bucket and key
        if (self.bucket.connection.use_proxy == True):
            path = self.bucket.connection.prefix_proxy_to_path(path)
        http_conn.putrequest('GET', path)
        for key in final_headers:
            http_conn.putheader(key,final_headers[key])
        http_conn.endheaders()
        resp = http_conn.getresponse()
        if resp.status != 200:
            raise S3ResponseError(resp.status, resp.reason)
        response_headers = resp.msg
        self.metadata = boto.utils.get_aws_metadata(response_headers)
        for key in response_headers.keys():
            if key.lower() == 'content-length':
                self.size = response_headers[key]
            elif key.lower() == 'etag':
                self.etag = response_headers[key]
            elif key.lower() == 'content-type':
                self.content_type = response_headers[key]
        l = resp.read(4096)
        while len(l) > 0:
            fp.write(l)
            l = resp.read(4096)
        resp.read()

    def get_contents_to_file(self, file):
        if self.bucket != None:
            self.get_file(file)

    def get_contents_to_filename(self, filename):
        fp = open(filename, 'wb')
        self.get_contents_to_file(fp)
        fp.close()

    def get_contents_as_string(self):
        fp = StringIO.StringIO()
        self.get_contents_to_file(fp)
        return fp.getvalue()

    # convenience methods for setting/getting ACL
    def set_acl(self, acl_str):
        if self.bucket != None:
            self.bucket.set_acl(acl_str, self.key)

    def get_acl(self):
        if self.bucket != None:
            return self.bucket.get_acl(self.key)
