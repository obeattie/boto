# Copyright (c) 2006, 2007 Mitch Garnaat http://garnaat.org/
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

"""
Represents an EC2 Instance
"""

from boto.resultset import ResultSet
import base64

class Reservation:
    
    def __init__(self, connection=None):
        self.connection = connection
        self.id = None
        self.owner_id = None
        self.groups = []
        self.instances = []

    def __repr__(self):
        return 'Reservation:%s' % self.id

    def startElement(self, name, attrs, connection):
        if name == 'instancesSet':
            self.instances = ResultSet('item', Instance)
            return self.instances
        elif name == 'groupSet':
            self.groups = ResultSet('item', Group)
            return self.groups
        else:
            return None

    def endElement(self, name, value, connection):
        if name == 'reservationId':
            self.id = value
        elif name == 'ownerId':
            self.owner_id = value
        else:
            setattr(self, name, value)

    def stop_all(self):
        for instance in self.instances:
            instance.stop()
            
class Instance:
    
    def __init__(self, connection=None):
        self.connection = connection
        self.id = None
        self.dns_name = None
        self.state = None
        self.key_name = None
        self.shutdown_state = None
        self.previous_state = None
        self.image_id = None

    def __repr__(self):
        return 'Instance:%s' % self.id
    
    def startElement(self, name, attrs, connection):
        if name == 'instanceState':
            self.state = InstanceState(self)
            return self.state
        else:
            return None

    def endElement(self, name, value, connection):
        if name == 'instanceId':
            self.id = value
        elif name == 'imageId':
            self.image_id = value
        elif name == 'dnsName':
            self.dns_name = value
        elif name == 'keyName':
            self.key_name = value
        elif name == 'amiLaunchIndex':
            self.ami_launch_index = value
        elif name == 'shutdownState':
            self.shutdown_state = value
        elif name == 'previousState':
            self.previous_state = value
        else:
            setattr(self, name, value)

    def _update(self, updated):
        self.updated = updated
        if hasattr(updated, 'dns_name'):
            self.dns_name = updated.dns_name
        if hasattr(updated, 'ami_launch_index'):
            self.ami_launch_index = updated.ami_launch_index
        self.shutdown_state = updated.shutdown_state
        self.previous_state = updated.previous_state
        if hasattr(updated, 'state'):
            self.state = updated.state
        else:
            self.state = None

    def update(self):
        rs = self.connection.get_all_instances([self.id])
        self._update(rs[0].instances[0])

    def stop(self):
        rs = self.connection.terminate_instances([self.id])
        self._update(rs[0])

    def reboot(self):
        return self.connection.reboot_instances([self.id])

    def get_console_output(self):
        return self.connection.get_console_output(self.id)

class Group:

    def __init__(self, parent=None):
        self.id = None

    def startElement(self, name, attrs, connection):
        return None

    def endElement(self, name, value, connection):
        if name == 'groupId':
            self.id = value
        else:
            setattr(self, name, value)
    
class InstanceState:
    
    def __init__(self, parent=None):
        self.parent = parent
        self.code = None
        self.name = None

    def __repr__(self):
        return 'state:%s' % self.name

    def startElement(self, name, attrs, connection):
        return None

    def endElement(self, name, value, connection):
        setattr(self, name, value)
        
class ConsoleOutput:

    def __init__(self, parent=None):
        self.parent = parent
        self.instance_id = None
        self.timestamp = None
        self.comment = None

    def startElement(self, name, attrs, connection):
        return None

    def endElement(self, name, value, connection):
        if name == 'instanceId':
            self.instance_id = value
        elif name == 'output':
            self.output = base64.b64decode(value)
        else:
            setattr(self, name, value)
