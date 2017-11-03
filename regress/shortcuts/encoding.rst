Encoding: bytes/unicode duality
===============================

We have some useful functions to transform a raw string of bytes to an human
text (aka unicode) and to do the inverse.

This is quite tricky because in Python 2.x those types are represented by ``str``
(or ``bytes``) and by ``unicode`` but in Python 3.x the types are ``bytes`` and
``str``

.. code:: python

   >>> import sys, os, time
   >>> sys.path.append(os.getcwd())
   
   >>> from shortcuts import to_bytes, to_text
   
   >>> byte_string = b'foo'
   >>> text_string = u'bar'

Convert to and from bytes (by default using 'utf-8')

.. code:: python

   >>> to_bytes(text_string) == b'bar'
   True

   >>> to_text(byte_string) == u'foo'
   True

The encoding can be changed

.. code:: python

   >>> valid_utf8_bytes = b'\xc3\x91' # but it is not an ascii valid string

   >>> _ = to_text(valid_utf8_bytes) # no exception, good

   >>> _ = to_text(valid_utf8_bytes, encoding='ascii')
   Traceback (most recent call last):
   UnicodeDecodeError: 'ascii' codec can't decode byte 0xc3 in position 0: ordinal not in range(128)


The functions are also idempotent

.. code:: python

   >>> to_bytes(byte_string) == byte_string
   True

   >>> to_text(text_string) == text_string
   True
   
