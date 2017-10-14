import json
import threading
import socket
from threading import Lock
import syslog, traceback
from connection import Connection
from message import pack_message, unpack_message_body
from topic import build_topic_chain, fail_if_topic_isnt_valid
from esc import esc
import random

class Publisher(object):
    def __init__(self, name="(publisher-only)"):
        self.name = name
        address = self._get_address()

        try:
          self.connection = Connection(address)
          self._log(syslog.LOG_DEBUG, "Stablished a connection with the notifier server (%s)." % esc(str(address)))
        except:
          self._log(syslog.LOG_ERR, "Error when creating a connection with the notifier server (%s): %s." % esc(str(address), traceback.format_exc()))
          raise 

        self.connection.send_object(pack_message(message_type='introduce_myself', name=name))
        
    def publish(self, topic, data):
        fail_if_topic_isnt_valid(topic, allow_empty=False)

        self._log(syslog.LOG_DEBUG, "Sending publication of an event with topic '%s'." % esc(topic))
        self.connection.send_object(pack_message(message_type='publish', topic=topic, obj=data, dont_pack_object=False))
        self._log(syslog.LOG_DEBUG, "Publication of an event sent.")


    def close(self, *args, **kargs):
       self.connection.close()
    
    def _get_address(self):
        import os, ConfigParser
        script_home = os.path.abspath(os.path.dirname(__file__))
        parent = os.path.pardir

        # TODO This shouldn't be hardcoded!
        config_file = os.path.join(script_home, parent, parent, parent, "config", "publish_subscribe.cfg")

        config = ConfigParser.SafeConfigParser(defaults={
                    'wait_on_address': "localhost",
                    'wait_on_port': "5555",
                     })

        config.read([config_file])
        if not config.has_section("notifier"):
           config.add_section("notifier")


        address = (config.get("notifier", 'wait_on_address'), config.getint("notifier", 'wait_on_port'))

        return address

    def __repr__(self):
        return "Endpoint (%s)" % self.name

    def _log(self, level, message): #TODO remove the "%" stuff over an unknow string (not local string)
        header = "%s: " % esc(repr(self))
        message = header + message

        syslog.syslog(level, message)
        return message


class EventHandler(threading.Thread, Publisher):
    
    def __init__(self, as_daemon=False, name="(bob-py)"):
        threading.Thread.__init__(self)
        if as_daemon:
           self.daemon = True

        Publisher.__init__(self, name=name)

        self.lock = Lock()
        self.callbacks_by_topic = {}
      
        self.subscriptions_by_id = {}
        self.next_valid_subscription_id = 0

        self.start()
        
    def __repr__(self):
        return "Endpoint (%s)" % self.name
        
    def subscribe(self, topic, callback, return_subscription_id=False, send_and_wait_echo=True):
        fail_if_topic_isnt_valid(topic, allow_empty=True)

        result = None
        self.lock.acquire()
        try:
           if self.callbacks_by_topic.has_key(topic):
               self.callbacks_by_topic[topic].append((callback, {'id': self.next_valid_subscription_id}))
               self._log(syslog.LOG_DEBUG, "Registered subscription locally. Subscription to the topic '%s' already sent." % esc(topic))
           else:
               self._log(syslog.LOG_DEBUG, "Sending subscription to the topic '%s'." % esc(topic))
               self.connection.send_object(pack_message(message_type='subscribe', topic=topic))
               self._log(syslog.LOG_DEBUG, "Subscription sent.")

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
          allow_unsubscription() #TODO very weak implementation: what happen if the callback is registered but an error happen and its subscriptio id is lost? How we can unsubscribe it?

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
                   
        except:
           self._log(syslog.LOG_ERR, "Exception when receiving a message: %s." % esc(traceback.format_exc()))
        finally:
           self.connection.close()

    def dispatch(self, topic, obj):
        topic_chain = build_topic_chain(topic)

        callbacks_collected = []
        self.lock.acquire()
        try:
           self._log(syslog.LOG_DEBUG, "Executing callback over the topic chain '%s'." % esc(", ".join(topic_chain))) ##TODO
           for t in topic_chain:
               callbacks = self.callbacks_by_topic.get(t, []);
               self._log(syslog.LOG_DEBUG, "For the topic '%s' there are %s callbacks." % esc( (t if t else "(the empty topic)"), str(len(callbacks))))
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
       self.connection.close()
       self.join(*args,  **kargs)

