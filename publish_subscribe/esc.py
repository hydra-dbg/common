import sys

def esc(*args):
   '''Return a tuple with its string escaped:
        - if one element is a str object, escape it using 'encode: string_escape'
        - if it is a unicode, use 'encode: unicode_escape'
        - else, don't do anything.
   '''
   escaped = []

   if sys.version_info.major > 2:
       string_t = bytes
       text_t   = str
   else:
       string_t = str
       text_t   = unicode

   for arg in args:
      if isinstance(arg, string_t):
         escaped.append(arg.encode('string_escape'))
      elif isinstance(arg, text_t):
         escaped.append(arg.encode('unicode_escape'))
      else:
         escaped.append(arg)

   return tuple(escaped)
