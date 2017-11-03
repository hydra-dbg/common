import os
import contextlib
import time
import sys
from subprocess import check_output, check_call
import random
from threading import Lock

if __package__:
    from .publish_subscribe.eventHandler import EventHandler
else:
    from publish_subscribe.eventHandler import EventHandler

def start_notifier(path):
   notifier_path = os.path.join(path, "notifier").replace(os.sep, '.')
   def is_running_notifier(): 
      out = check_output(["python", "-m", notifier_path, "status"]) 
      return b"running" in out
   
   if not is_running_notifier():
      check_call(["python", "-m", notifier_path, "start"]) 

   t = 10
   while not is_running_notifier() and t > 0:
      time.sleep(0.1)
      t -= 0.1
 
   if not is_running_notifier():
      raise Exception("The notifier is not up and i cannot start it.")

def stop_notifier(path):   
   notifier_path = os.path.join(path, "notifier").replace(os.sep, '.')
   check_call(["python", "-m", notifier_path, "stop"]) 

def request(gdb, command, arguments=tuple(), return_none=False):
   cookie = int(random.getrandbits(30))
   request_topic = "request-gdb.%i.%i" % (gdb.get_gdb_pid(), cookie)
   response_topic = "result-gdb.%i.%i" % (gdb.get_gdb_pid(), cookie)

   # Build the command correctly: use always the MI interface and a cookie
   if not command.startswith("-"):
      interpreter = 'console'
   else:
      interpreter = 'mi'

   request_for_command = {
         'command': command,
         'token': cookie,
         'arguments': arguments,
         'interpreter': interpreter,
   }

   # Create a flag acquired by default
   response_received_flag = Lock()
   response_received_flag.acquire() 

   ctx = {}
   def _wait_and_get_response_from_gdb(event):
      ctx['response'] = event
      response_received_flag.release() # release the flag, response received!
      
   pubsub = EventHandler(name="requester")
   subscription_id = pubsub.subscribe(
                                 response_topic, 
                                 _wait_and_get_response_from_gdb, 
                                 return_subscription_id = True
                        )

   pubsub.publish(request_topic, request_for_command)
   response_received_flag.acquire() # block until the flag is release by the callback (and the respose was received)
   pubsub.unsubscribe(subscription_id)

   return None if return_none else ctx['response']


def collect(func_collector):
   '''Wrap a function, that should return some data, and returns its decorated version.
      This wrap will allow to call func_collector once and only once.
      After the first call, subsequent calls will block the thread.
      
      The wrap will also contain a method called 'get_next' that will block if
      no func_collector was done previously.

      After calling (successfully) func_collector, get_next is allowed to be called.
      After calling get_next, func_collector is allowed again.

      This interaction between func_collector and get_next allows to share results
      from one thread (calling func_collector) to another thread (calling get_next).
      The results are shared one at time.

      An additional method is added to the wrap named 'destroy'. When it is called,
      it will force to func_collector to drop any data. That means that a subsequent
      call to get_next will block (so don't do it!).

      Use this destroy method to make sure that all the resources are freed and that
      a call to func_collector will not block.

      This wrapper was mainly designed for testing purposes.
   '''
   ctx = {'drop': False}
   can_read_flag = Lock()
   can_read_flag.acquire()

   can_write_flag = Lock()

   def _collect(*args, **kargs):
      can_write_flag.acquire()

      c = func_collector(*args, **kargs)
      if c == None or ctx['drop']:
         can_write_flag.release()
         return # discard

      ctx['data'] = c
      can_read_flag.release()

   def _get_next(timeout=5, poll_time=0.1):
      can_read_acquired = can_read_flag.acquire(False)
      while not can_read_acquired and timeout > 0:
          time.sleep(poll_time)
          timeout -= poll_time
          can_read_acquired = can_read_flag.acquire(False)

      if not can_read_acquired:
          raise Exception("'get_next' data timed out.")

      c = ctx['data']
      can_write_flag.release()
      return c

   def _destroy():
      can_write_acquired = can_write_flag.acquire(False)
      while not can_write_acquired:
          # we couldn't acquire the write flag, this can means that:
          #  - or the _collect acquired it and eventually it will release
          #    it because the data may be discarded 
          #  - or the _collect acquired it and eventually it will release
          #    the can-read flag: we cannot relay in _get_next to release
          #    the write flag so we must to take care
          time.sleep(0.01)
          can_read_acquired = can_read_flag.acquire(False)
          if can_read_acquired:
              # drop the data of _get_next and release the write flag
              # this will simulate a _get_next call dropping any 
              # pending data
              can_write_flag.release()
          
          can_write_acquired = can_write_flag.acquire(False)

      # this will force to _collect to drop all the pending and future
      # data, acquiring and releasing the can-write flag ignoring the 
      # can-read one. Because of this, a call to _get_next will block
      # forever
      ctx['drop'] = True
      can_write_flag.release()

   _collect.get_next = _get_next
   _collect.destroy = _destroy

   return _collect

def poll_process(proc, tries, poll_time):
   ''' Poll for the finish of the process proc. If proc is None or it has
       not finished yet, keep polling at most 'tries' tries, waiting for
       'poll_time' seconds between each try.

       Return None. It is the caller responsibility to check if proc
       finished or not.
       '''
   while proc and proc.poll() is None and tries > 0:
      time.sleep(poll_time)
      tries -= 1

@contextlib.contextmanager
def noexception():
   ''' Silent any possible exception. This is useful only in 
       situations that you cannot do anything like when you are
       finalizing a process and you want to close everything.
       '''
   try:
      yield
   except:
      pass


def to_bytes(s, encoding='utf-8'):
   return s if isinstance(s, bytes) else s.encode(encoding)

def to_text(s, encoding='utf-8'):
   text_t = str if sys.version_info.major > 2 else unicode
   return s if isinstance(s, text_t) else text_t(s, encoding)
