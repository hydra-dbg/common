import json
import threading
import socket
from threading import Lock
import syslog, traceback
from .connection import Connection, ConnectionClosed
from .message import pack_message, unpack_message_body
from .topic import build_topic_chain, fail_if_topic_isnt_valid
from .esc import esc, to_bytes, to_text
import random

class Publisher(object):
    def __init__(self, name="(publisher-only)", address=("localhost", 5555)):
        self.name = to_text(name) # for threading.Thread compatibility
        self.bin_name = to_bytes(name)

        self.said_goodbye = False

        try:
          self.connection = Connection(address, whoiam=self.name)
          self._log(syslog.LOG_DEBUG, "Established a connection with the notifier server (%s)." % esc(str(address)))
        except:
          self._log(syslog.LOG_ERR, "Error when creating a connection with the notifier server (%s): %s." % esc(str(address), traceback.format_exc()))
          raise 

        self.connection.send_object(pack_message(message_type='introduce_myself', name=self.bin_name))
        self._safe_topics = set()
        
    def publish(self, topic, data):
        topic = to_bytes(topic)
        if topic not in self._safe_topics:
            fail_if_topic_isnt_valid(topic, allow_empty=False)
            self._safe_topics.add(topic)

        #self._log(syslog.LOG_DEBUG, "Sending publication of an event with topic '%s'." % esc(topic))
        self.connection.send_object(pack_message(message_type='publish', topic=topic, obj=data, dont_pack_object=False))
        #self._log(syslog.LOG_DEBUG, "Publication of an event sent.")


    def close(self, *args, **kargs):
       assert isinstance(self.bin_name, bytes)
       if not self.connection.closed:
          self.connection.send_object(pack_message(message_type='goodbye', name=self.bin_name))
          self.said_goodbye = True
       self.connection.close()
    
    def __repr__(self):
        return "Endpoint (%s)" % self.name

    def _log(self, level, message): #TODO remove the "%" stuff over an unknown string (not local string)
        header = "%s: " % esc(repr(self))
        message = header + message

        syslog.syslog(level, message)
        return message


class EventHandler(threading.Thread, Publisher):
    
    def __init__(self, as_daemon=False, name="(bob-py)", address=("localhost", 5555)):
        threading.Thread.__init__(self)
        if as_daemon:
           self.daemon = True

        Publisher.__init__(self, name=name, address=address)

        self.lock = Lock()
        self.callbacks_by_topic = {}
      
        self.subscriptions_by_id = {}
        self.next_valid_subscription_id = 0

        self.start()
        
    def __repr__(self):
        return "Endpoint (%s)" % self.name
        
    def subscribe(self, topic, callback, return_subscription_id=False, send_and_wait_echo=True):
        topic = to_bytes(topic)
        if topic not in self._safe_topics:
            fail_if_topic_isnt_valid(topic, allow_empty=True)
            if topic: # don't add an empty topic: whitelisting this kind of topics will defeat the publish's check. See this same check in the publish method.
                self._safe_topics.add(topic) 

        result = None
        self.lock.acquire()
        try:
           if topic in self.callbacks_by_topic:
               self.callbacks_by_topic[topic].append((callback, {'id': self.next_valid_subscription_id}))
           else:
               #self._log(syslog.LOG_DEBUG, "Sending subscription to the topic '%s'." % esc(topic))
               self.connection.send_object(pack_message(message_type='subscribe', topic=topic))
               #self._log(syslog.LOG_DEBUG, "Subscription sent.")

               self.callbacks_by_topic[topic] = [(callback, {'id': self.next_valid_subscription_id})]

           self.subscriptions_by_id[self.next_valid_subscription_id] = {
                 'callback': callback,
                 'topic': topic,
                 }

           self.next_valid_subscription_id += 1
           if return_subscription_id:
              result = self.next_valid_subscription_id - 1;

        finally:
           self.lock.release()

        if send_and_wait_echo:
           cookie = "echo-%i" % int(random.getrandbits(30))
         
           echo_received_flag = Lock()
           echo_received_flag.acquire()

           self.subscribe_for_once_call(cookie, lambda data: echo_received_flag.release(), send_and_wait_echo=False)
           self.publish(cookie, '')

           echo_received_flag.acquire()

        return result

   
    def unsubscribe(self, subscription_id):
        self.lock.acquire()
        try:
           self._unsubscribe(subscription_id)
        finally:
           self.lock.release()

    def wait(self, topic):
        topic = to_bytes(topic)
        flag = Lock()
        env = {}
        
        def set_data_and_release_flag(data):
            env['data'] = data
            flag.release()

        flag.acquire()
        self.subscribe_for_once_call(topic, set_data_and_release_flag)
        flag.acquire() # this will block us until the set_data_and_release_flag is called

        flag.release() # just for clean up
        return env['data']
        

    def _unsubscribe(self, subscription_id):
        try:
           subscription = self.subscriptions_by_id[subscription_id]
        except KeyError:
           raise Exception("The subscription id '%i' hasn't any callback registered to it." % esc(subscription_id))

        topic = subscription['topic']
        callbackToBeRemoved = subscription['callback']

        for i, callback_and_meta in enumerate(self.callbacks_by_topic[topic]):
           callback, meta = callback_and_meta
           if callback == callbackToBeRemoved and meta['id'] == subscription_id:
              del self.callbacks_by_topic[topic][i]
              break

        if not self.callbacks_by_topic[topic]:
           del self.callbacks_by_topic[topic]
           self.connection.send_object(pack_message(message_type='unsubscribe', topic=topic))
        
        del self.subscriptions_by_id[subscription_id]


    def subscribe_for_once_call(self, topic, callback, **kargs):
       topic = to_bytes(topic)
       subscription = {}
       temp_lock = Lock()

       def wait_until_i_can_unsubscribe_myself():
          temp_lock.acquire()
          temp_lock.release()

       def dont_allow_unsubscription():
          temp_lock.acquire()

       def allow_unsubscription():
          temp_lock.release()
          

       def wrapper(data):
          try:
             return callback(data)
          finally:
             wait_until_i_can_unsubscribe_myself()  
             self._unsubscribe(subscription['id'])


       return_subscription_id = kargs.get('return_subscription_id', False)
       kargs['return_subscription_id'] = True

       dont_allow_unsubscription()
       try:
          subscription['id'] = self.subscribe(topic, wrapper, **kargs)
       finally:
          allow_unsubscription() #TODO very weak implementation: what happen if the callback is registered but an error happen and its subscription id is lost? How we can unsubscribe it?

       return subscription['id'] if return_subscription_id else None

    def run(self):
        try:
           while not self.connection.end_of_the_communication:
               message_type, message_body = self.connection.receive_object()
               
               if message_type != "publish":
                   self._log(syslog.LOG_ERR, "Unexpected message of type '%s' (expecting a 'publish' message). Dropping the message and moving on." % esc(message_type))
                   continue

               topic, obj = unpack_message_body(message_type, message_body, dont_unpack_object=False)
               self.dispatch(topic, obj)


        except Exception as ex:
           if isinstance(ex, ConnectionClosed) and self.said_goodbye:
              self._log(syslog.LOG_NOTICE, "The connection was closed, it's ok, we said goodbye.")
              pass # okay, we said goodbye
           else:
              self._log(syslog.LOG_ERR, "Exception when receiving a message: %s." % esc(traceback.format_exc()))
        finally:
           self.connection.close()

    def dispatch(self, topic, obj):
        assert isinstance(topic, bytes)
        topic_chain = build_topic_chain(topic)

        callbacks_collected = []
        self.lock.acquire()
        try:
           for t in topic_chain:
               callbacks = self.callbacks_by_topic.get(t, []);
               callbacks_collected.append(list(callbacks)) # get a copy!
        finally:
           self.lock.release()
         
        for callbacks in callbacks_collected:   
            for callback, subscription in callbacks:
                self._execute_callback(callback, obj, t) #TODO what is 't'?

    def _execute_callback(self, callback, data, t):
       try:
          callback(data)
       except:
          self._log(syslog.LOG_ERR, "Exception in callback for the topic '%s': %s" % esc((t if t else "(the empty topic)"), traceback.format_exc()))
      

    def close(self, *args, **kargs):
       Publisher.close(self)
       self.join(*args,  **kargs)

