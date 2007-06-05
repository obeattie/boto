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

from boto.connection import AWSAuthConnection, AWSQueryConnection
import xml.sax
from boto.sqs.queue import Queue
from boto.sqs.attributes import Attributes
from boto import handler
from boto.resultset import ResultSet
from boto.exception import SQSError

class SQSQueryConnection(AWSQueryConnection):

    """
    This class uses the Query API (boo!) to SQS to access some of the
    new features which have not yet been added to the REST api (yeah!).
    """
    
    DefaultHost = 'queue.amazonaws.com'
    APIVersion = '2007-05-01'
    SignatureVersion = '1'
    DefaultContentType = 'text/plain'
    
    def __init__(self, aws_access_key_id=None, aws_secret_access_key=None,
                 is_secure=False, port=None, proxy=None, proxy_port=None,
                 host=DefaultHost, debug=0, https_connection_factory=None):
        AWSQueryConnection.__init__(self, aws_access_key_id,
                                    aws_secret_access_key,
                                    is_secure, port, proxy, proxy_port,
                                    host, debug, https_connection_factory)

    def get_queue_attributes(self, queue_url, attribute='All'):
        params = {'Attribute' : attribute}
        response = self.make_request('GetQueueAttributes', params, queue_url)
        body = response.read()
        if response.status == 200:
            attrs = Attributes()
            h = handler.XmlHandler(attrs, self)
            xml.sax.parseString(body, h)
            return attrs
        else:
            raise SQSError(response.status, response.reason, body)

    def set_queue_attribute(self, queue_url, attribute, value):
        params = {'Attribute' : attribute, 'Value' : value}
        response = self.make_request('SetQueueAttributes', params, queue_url)
        body = response.read()
        if response.status == 200:
            rs = ResultSet()
            h = handler.XmlHandler(rs, self)
            xml.sax.parseString(body, h)
            return rs.status
        else:
            raise SQSError(response.status, response.reason, body)
        
class SQSConnection(AWSAuthConnection):
    
    DefaultHost = 'queue.amazonaws.com'
    DefaultVersion = '2007-05-01'
    DefaultContentType = 'text/plain'
    
    def __init__(self, aws_access_key_id=None, aws_secret_access_key=None,
                 is_secure=False, port=None, proxy=None, proxy_port=None,
                 host=DefaultHost, debug=0, https_connection_factory=None):
        AWSAuthConnection.__init__(self, host,
                                   aws_access_key_id, aws_secret_access_key,
                                   is_secure, port, proxy, proxy_port, debug,
                                   https_connection_factory)
        self.query_conn = None

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

    def get_query_connection(self):
        if not self.query_conn:
            self.query_conn = SQSQueryConnection(self.aws_access_key_id,
                                                 self.aws_secret_access_key,
                                                 self.is_secure, self.port,
                                                 self.proxy, self.proxy_port,
                                                 self.server, self.debug,
                                                 self.https_connection_factory)
        return self.query_conn

    def get_all_queues(self, prefix=''):
        if prefix:
            path = '/?QueueNamePrefix=%s' % prefix
        else:
            path = '/'
        response = self.make_request('GET', path)
        body = response.read()
        if response.status >= 300:
            raise SQSError(response.status, response.reason, body)
        rs = ResultSet([('QueueUrl', Queue)])
        h = handler.XmlHandler(rs, self)
        xml.sax.parseString(body, h)
        return rs

    def get_queue(self, queue_name):
        i = 0
        rs = self.get_all_queues(queue_name)
        for q in rs:
            i += 1
        if i != 1:
            return None
        else:
            return q

    def get_queue_attributes(self, queue_url, attribute='All'):
        """
        Performs a GetQueueAttributes request and returns an Attributes
        instance (subclass of a Dictionary) holding the requested
        attribute name/value pairs.
        Inputs:
            queue_url - the URL of the desired SQS queue
            attribute - All|ApproximateNumberOfMessages|VisibilityTimeout
                        Default value is "All"
        Returns:
            An Attribute object which is a mapping type holding the
            requested name/value pairs
        """
        qc = self.get_query_connection()
        return qc.get_queue_attributes(queue_url, attribute)
    
    def set_queue_attribute(self, queue_url, attribute, value):
        """
        Performs a SetQueueAttributes request.
        Inputs:
            queue_url - The URL of the desired SQS queue
            attribute - The name of the attribute you want to set.  The
                        only valid value at this time is: VisibilityTimeout
                value - The new value for the attribute.
                        For VisibilityTimeout the value must be an
                        integer number of seconds from 0 to 86400.
        Returns:
            Boolean True if successful, otherwise False.
        """
        qc = self.get_query_connection()
        return qc.set_queue_attribute(queue_url, attribute, value)
    
    def create_queue(self, queue_name, visibility_timeout=None):
        """
        Create a new queue.
        Inputs:
            queue_name - The name of the new queue
            visibility_timeout - (Optional) The default visibility
                                 timeout for the new queue.
        Returns:
            A new Queue object representing the newly created queue.
        """
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

    def delete_queue(self, queue, force_deletion=False):
        """
        Delete an SQS Queue.
        Inputs:
            queue - a Queue object representing the SQS queue to be deleted.
            force_deletion - (Optional) Normally, SQS will not delete a
                             queue that contains messages.  However, if
                             the force_deletion argument is True, the
                             queue will be deleted regardless of whether
                             there are messages in the queue or not.
                             USE WITH CAUTION.  This will delete all
                             messages in the queue as well.
        Returns:
            An empty ResultSet object.  Not sure why, actually.  It
            should probably return a Boolean indicating success or
            failure.
        """
        if force_deletion:
            path = 'DELETE?ForceDeletion=true'
        else:
            path = 'DELETE'
        response = self.make_request(path, queue.id)
        body = response.read()
        if response.status >= 300:
            raise SQSError(response.status, response.reason, body)
        rs = ResultSet()
        h = handler.XmlHandler(rs, self)
        xml.sax.parseString(body, h)
        return rs

