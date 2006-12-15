# Copyright (c) 2006 Mitch Garnaat http://garnaat.org/
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

#
# Parts of this code were copied or derived from sample code supplied by AWS.
# The following notice applies to that code.
#
#  This software code is made available "AS IS" without warranties of any
#  kind.  You may copy, display, modify and redistribute the software
#  code either by itself or as incorporated into your code; provided that
#  you do not remove any proprietary notices.  Your use of this software
#  code is at your own risk and you waive any claim against Amazon
#  Digital Services, Inc. or its affiliates with respect to your use of
#  this software code. (c) 2006 Amazon Digital Services, Inc. or its
#  affiliates.

"""
Handles basic connections to AWS
"""

import base64
import hmac
import httplib
import re
import sha
import sys
import time
import urllib
import os
import xml.sax
from boto.exception import SQSError, S3ResponseError, S3CreateError
from boto import handler
from boto.queue import Queue
from boto.bucket import Bucket
from boto.resultset import ResultSet
from boto.user import User
from boto.image import Image
from boto.instance import Reservation
from boto.keypair import KeyPair
from boto.securitygroup import SecurityGroup
import boto.utils

PORTS_BY_SECURITY = { True: 443, False: 80 }

class AWSAuthConnection:
    def __init__(self, server, aws_access_key_id=None,
                 aws_secret_access_key=None,
                 is_secure=True, port=None, debug=False):
        self.is_secure = is_secure
        self.server = server
        self.debug = debug
        if not port:
            port = PORTS_BY_SECURITY[is_secure]
        self.port = port

        if aws_access_key_id:
            self.aws_access_key_id = aws_access_key_id
        else:
            if os.environ.has_key('AWS_ACCESS_KEY_ID'):
                self.aws_access_key_id = os.environ['AWS_ACCESS_KEY_ID']

        if aws_secret_access_key:
            self.aws_secret_access_key = aws_secret_access_key
        else:
            if os.environ.has_key('AWS_SECRET_ACCESS_KEY'):
                self.aws_secret_access_key = os.environ['AWS_SECRET_ACCESS_KEY']

        self.make_http_connection()
        self._last_rs = None

    def make_http_connection(self):
        if self.debug:
            print 'establishing HTTP connection'
        if (self.is_secure):
            self.connection = httplib.HTTPSConnection("%s:%d" % (self.server,
                                                                 self.port))
        else:
            self.connection = httplib.HTTPConnection("%s:%d" % (self.server,
                                                                self.port))
        self.set_debug(self.debug)

    def set_debug(self, debug=0):
        self.debug = debug
        self.connection.set_debuglevel(debug)

    def make_request(self, method, path, headers=None, data='', metadata=None):
        if headers == None:
            headers = {}
        if metadata == None:
            metadata = {}
        final_headers = boto.utils.merge_meta(headers, metadata);
        # add auth header
        self.add_aws_auth_header(final_headers, method, path)

        self.connection.request(method, path, data, final_headers)
        try:
            return self.connection.getresponse()
        except httplib.HTTPException, e:
            self.make_http_connection()
            self.connection.request(method, path, data, final_headers)
            return self.connection.getresponse()

    def add_aws_auth_header(self, headers, method, path):
        if not headers.has_key('Date'):
            headers['Date'] = time.strftime("%a, %d %b %Y %H:%M:%S GMT",
                                            time.gmtime())

        c_string = boto.utils.canonical_string(method, path, headers)
        if self.debug:
            print '\n\n%s\n\n' % c_string
        headers['Authorization'] = \
            "AWS %s:%s" % (self.aws_access_key_id,
                           boto.utils.encode(self.aws_secret_access_key,
                                             c_string))
        
class SQSConnection(AWSAuthConnection):
    
    DefaultHost = 'queue.amazonaws.com'
    DefaultVersion = '2006-04-01'
    DefaultContentType = 'text/plain'
    
    def __init__(self, aws_access_key_id=None, aws_secret_access_key=None,
                 is_secure=False, port=None, debug=0):
        AWSAuthConnection.__init__(self, self.DefaultHost,
                                   aws_access_key_id, aws_secret_access_key,
                                   is_secure, port, debug)

    def make_request(self, method, path, headers=None, data=''):
        # add auth header
        if headers == None:
            headers = {}

        if not headers.has_key('AWS-Version'):
            headers['AWS-Version'] = self.DefaultVersion

        if not headers.has_key('Content-Type'):
            headers['Content-Type'] = self.DefaultContentType

        return AWSAuthConnection.make_request(self, method, path,
                                              headers, data)

    def get_all_queues(self, prefix=''):
        if prefix:
            path = '/?QueueNamePrefix=%s' % prefix
        else:
            path = '/'
        response = self.make_request('GET', path)
        body = response.read()
        if response.status >= 300:
            raise SQSError(response.status, response.reason, body)
        rs = ResultSet('QueueUrl', Queue)
        h = handler.XmlHandler(rs, self)
        xml.sax.parseString(body, h)
        return rs

    def create_queue(self, queue_name, visibility_timeout=None):
        path = '/?QueueName=%s' % queue_name
        if visibility_timeout:
            path = path + '&DefaultVisibilityTimeout=%d' % visibility_timeout
        response = self.make_request('POST', path)
        body = response.read()
        if response.status >= 300:
            raise SQSError(response.status, response.reason, body)
        q = Queue(self)
        h = handler.XmlHandler(q, self)
        xml.sax.parseString(body, h)
        return q

    def delete_queue(self, queue):
        response = self.make_request('DELETE', queue.id)
        body = response.read()
        if response.status >= 300:
            raise SQSError(response.status, response.reason, body)
        rs = ResultSet()
        h = handler.XmlHandler(rs, self)
        xml.sax.parseString(body, h)
        return rs

class S3Connection(AWSAuthConnection):

    DefaultHost = 's3.amazonaws.com'

    def __init__(self, aws_access_key_id=None, aws_secret_access_key=None,
                 is_secure=False, port=None, debug=0):
        AWSAuthConnection.__init__(self, self.DefaultHost,
                                   aws_access_key_id, aws_secret_access_key,
                                   is_secure, port, debug)
    
    def generate_url(self, request, bits=None, expires_in=60):
        if bits:
            if not isinstance(bits, Bits):
                raise BitBucketTypeError('Value must be of type Bits')
        self.connection.query_gen.set_expires_in(expires_in)
        if request == 'get':
            return self.connection.query_gen.get(self.name, bits.key)
        elif request == 'delete':
            return self.connection.query_gen.delete(self.name, bits.key)
        else:
            raise BitBucketError('Invalid request: %s' % request)

    def get_all_buckets(self):
        path = '/'
        response = self.make_request('GET', urllib.quote(path))
        body = response.read()
        if response.status > 300:
            raise S3ResponseError(response.status, response.reason)
        rs = ResultSet('Bucket', Bucket)
        h = handler.XmlHandler(rs, self)
        xml.sax.parseString(body, h)
        return rs

    def create_bucket(self, bucket_name, headers={}):
        path = '/%s' % bucket_name
        response = self.make_request('PUT', urllib.quote(path), headers)
        body = response.read()
        if response.status == 409:
             raise S3CreateError(response.status, response.reason)
        if response.status == 200:
            b = Bucket(self, bucket_name, debug=self.debug)
            return b
        else:
            raise S3ResponseError(response.status, response.reason)

    def delete_bucket(self, bucket):
        path = '/%s' % bucket.name
        response = self.make_request('DELETE', urllib.quote(path))
        body = response.read()
        if response.status != 204:
            raise S3ResponseError(response.status, response.reason)

class EC2Connection(AWSAuthConnection):

    DefaultHost = 'ec2.amazonaws.com'
    EC2Version = '2006-10-01'
    SignatureVersion = '1'

    def __init__(self, aws_access_key_id=None, aws_secret_access_key=None,
                 is_secure=True, port=None, debug=0):
        AWSAuthConnection.__init__(self, self.DefaultHost,
                                   aws_access_key_id, aws_secret_access_key,
                                   is_secure, port, debug)

    def make_request(self, action, params=None):
        if params == None:
            params = {}
        h = hmac.new(key=self.aws_secret_access_key, digestmod=sha)
        params['Action'] = action
        params['Version'] = self.EC2Version
        params['AWSAccessKeyId'] = self.aws_access_key_id
        params['SignatureVersion'] = self.SignatureVersion
        params['Timestamp'] = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
        keys = params.keys()
	keys.sort(cmp = lambda x, y: cmp(x.lower(), y.lower()))
        qs = ''
        for key in keys:
            h.update(key)
            h.update(str(params[key]))
            qs += key + '=' + urllib.quote(str(params[key])) + '&'
        signature = base64.b64encode(h.digest())
        qs += 'Signature=' + urllib.quote(signature)
        self.connection.request('GET', '/?%s' % qs)
        try:
            return self.connection.getresponse()
        except httplib.HTTPException, e:
            self.make_http_connection()
            self.connection.request('GET', '/?%s' % qs)
            return self.connection.getresponse()

    def build_list_params(self, params, items, label):
        for i in range(1, len(items)+1):
            params['%s.%d' % (label, i)] = items[i-1]
        
    def describe_images(self, image_ids=None, owners=None, executable_by=None):
        params = {}
        if image_ids:
            self.build_list_params(params, image_ids, 'ImageId')
        if owners:
            self.build_list_params(params, owners, 'Owner')
        if executable_by:
            self.build_list_params(params, executable_by, 'ExecutableBy')
        response = self.make_request('DescribeImages')
        body = response.read()
        if response.status == 200:
            rs = ResultSet('item', Image)
            h = handler.XmlHandler(rs, self)
            xml.sax.parseString(body, h)
            return rs
        else:
            raise S3ResponseError(response.status, response.reason)

    def describe_instances(self, instance_ids=None):
        params = {}
        if instance_ids:
            self.build_list_params(params, instance_ids, 'InstanceId')
        response = self.make_request('DescribeInstances')
        body = response.read()
        if response.status == 200:
            rs = ResultSet('item', Reservation)
            h = handler.XmlHandler(rs, self)
            xml.sax.parseString(body, h)
            return rs
        else:
            raise S3ResponseError(response.status, response.reason)

    def describe_keypairs(self, keynames=None):
        params = {}
        if keynames:
            self.build_list_params(params, keynames, 'KeyName')
        response = self.make_request('DescribeKeyPairs', params)
        body = response.read()
        if response.status == 200:
            rs = ResultSet('item', KeyPair)
            h = handler.XmlHandler(rs, self)
            xml.sax.parseString(body, h)
            return rs
        else:
            raise S3ResponseError(response.status, response.reason)
        
    def describe_securitygroups(self, groupnames=None):
        params = {}
        if groupnames:
            self.build_list_params(params, groupnames, 'GroupName')
        response = self.make_request('DescribeSecurityGroups')
        body = response.read()
        if response.status == 200:
            rs = ResultSet('item', SecurityGroup)
            h = handler.XmlHandler(rs, self)
            xml.sax.parseString(body, h)
            return rs
        else:
            raise S3ResponseError(response.status, response.reason)
