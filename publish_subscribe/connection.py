
import socket
import syslog
import json
import time
import traceback

from esc import esc
from message import unpack_message_header

class ConnectionClosed(Exception):
    def __init__(self, msg=""):
        Exception.__init__(self, "The connection was closed between messages (no message was sent/received partially). " + msg)

class PartialMessageDueConnectionClose(Exception):
    def __init__(self, msg=""):
        Exception.__init__(self, "The message was sent/received partially due an unexpected connection close. " + msg)

class Connection(object):
   def __init__(self, address_or_already_open_socket, whoiam="(?)"):
      self.buf = ""
      self.end_of_the_communication = False
      self.closed = True
      self.whoiam = whoiam

      if isinstance(address_or_already_open_socket, (tuple, list)):
         address = address_or_already_open_socket

         self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
         connected = False
         attempts = 0
         while not connected:
            try:
               self.socket.connect(address)
               connected = True
            except:
               time.sleep(0.5)
               attempts += 1
               if attempts > 100: #approx 0.5*100 = 50 seconds
                  raise
         
         self.closed = False

      else:
         self.socket = address_or_already_open_socket
         self.closed = False


   def send_object(self, message):
      if self.end_of_the_communication:
         raise Exception("The communication is already close")

      #syslog.syslog(syslog.LOG_DEBUG, 
      #        " ".join(["%s is sending..." % self.whoiam, 
      #        str(len(message)), 
      #        repr(message), 
      #        ]))

      self.socket.sendall(message)

   def receive_object(self):
      if self.end_of_the_communication:
         raise Exception("The communication is already close")

      header = self._read_next_message_header()
      message_type, message_body = self._read_next_message_body(header)
      #syslog.syslog(syslog.LOG_DEBUG, 
      #        " ".join(["%s received" % self.whoiam, 
      #        str(len(header)), 
      #       repr(header), 
      #        "op:", 
      #        message_type, 
      #        str(len(message_body)), 
      #        repr(message_body)]))

      return message_type, message_body


   def close(self):
      if self.closed:
         return 

      self.closed = True
      self.end_of_the_communication = True

      try:
         self.socket.shutdown(socket.SHUT_RDWR)
      except:
         syslog.syslog(syslog.LOG_ERR, "Error in the shutdown: '%s'" % esc(traceback.format_exc()))

      try:
         self.socket.close()
      except:
         syslog.syslog(syslog.LOG_ERR, "Error in the close: '%s'" % esc(traceback.format_exc()))

    
   def _read_next_message_header(self):
      #syslog.syslog(syslog.LOG_DEBUG, "Waiting for the next message header")
      header_len = 3
      header = self._recv_all(header_len)

      if len(header) < header_len:
          self.end_of_the_communication = True
          if not header:
              raise ConnectionClosed()
          else:
              raise PartialMessageDueConnectionClose("Received %i bytes of the header" % (header_len-len(header)))

      return header

   def _read_next_message_body(self, header):
      message_type, message_body_len = unpack_message_header(header)
      #syslog.syslog(syslog.LOG_DEBUG, "Received '%s' with %i bytes to be read. Reading..." % esc(message_type, message_body_len))

      message_body = self._recv_all(message_body_len)

      if len(message_body) < message_body_len:
          self.end_of_the_communication = True
          raise PartialMessageDueConnectionClose("Received %i bytes of the message body" % (message_body_len-len(message_body)))

      return message_type, message_body

   
   def _recv_all(self, to_receive):
      chunks = []
      assert to_receive >= 0

      while to_receive > 0:
          chunk = self.socket.recv(to_receive)
          if not chunk:
              break

          chunks.append(chunk)
          to_receive -= len(chunk)
      
      return "".join(chunks)


   def __del__(self):
      self.close()
