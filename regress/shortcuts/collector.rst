Collect decorator
=================

Mainly for testing purposes there is a convenient 'collect' decorator.
This decorator will collect all the events captured by a subscribed function
in a thread-safe way.

Let's see how to create one by example

.. code:: python

   >>> import sys, os, time
   >>> sys.path.append(os.getcwd())
   
   >>> from shortcuts import collect
   
   >>> @collect
   ... def collector(data):
   ...   if not data['is_important?']:
   ...      return None # discard
   ...   return data

The decorated function well receive the data from the publish-subscribe system as
usual and it will return any interesting data or None if the data needs to be
discarded.

Let's set up a scenario for this

.. code:: python

   >>> from shortcuts import start_notifier, stop_notifier
   >>> start_notifier("publish_subscribe/")

   >>> from publish_subscribe.eventHandler import EventHandler
   >>> EH = EventHandler(name="TheTest")
   
   >>> @collect
   ... def collector(data):
   ...   if not data['is_important?']:
   ...      return None # discard
   ...   return data['msg']
   
   >>> EH.subscribe('some-topic', collector)

Now if we emit a "very important" event, we can fetch it in the same current
thread with the ``get_next`` method
 
.. code:: python

   >>> EH.publish('some-topic', {'is_important?': True, 'msg': 'awesome'})
   >>> collector.get_next()
   u'awesome'

Data discarded by the callback will not be captured nor returned by ``get_next``

.. code:: python

   >>> EH.publish('some-topic', {'is_important?': True,  'msg': 'cool'})
   >>> EH.publish('some-topic', {'is_important?': False, 'msg': 'bla-bla-bla'})
   >>> EH.publish('some-topic', {'is_important?': True,  'msg': 'good'})

   >>> collector.get_next()
   u'cool'

   >>> collector.get_next()
   u'good'

The ``get_next`` method will block until the data is collected by our ``collector``
function.

By default there is a timeout of 5 secs, but you can change it if you need. 
If no data is received by that time, raise an exception

.. code:: python

   >>> collector.get_next(timeout=1)
   Traceback (most recent call last):
   Exception: 'get_next' data timed out.


Beware that the collector is a blocking function that it will unblock only when
the previous event was fetched by ``get_next``. 
This could lead to a deadblock if the publish-subscribe system is trying to call
``collect``, pushing a new event but nobody is fetching it.

This could happen of you are receiving more events than you expect.
To avoid any problem, call ``destroy`` before closing the publish-subscribe handler.

Current pending and future events will be dropped. Beware that any call to ``get_next``
will block your thread!

.. code:: python

   >>> collector.destroy()

Now it is safe to close everything else

.. code:: python

   >>> EH.close()
   >>> stop_notifier("publish_subscribe/")

