import sys

def esc(*args):
   '''Return a tuple with its string escaped:
        - if one element is a str object, escape it using 'encode: string_escape'
        - if it is a unicode, use 'encode: unicode_escape'
        - else, don't do anything.
   '''
   escaped = []

   if sys.version_info.major > 2:
       for arg in args:
          if isinstance(arg, bytes):
             escaped.append(str(arg, 'utf-8').encode('unicode_escape'))
          elif isinstance(arg, str):
             escaped.append(arg.encode('unicode_escape'))
          else:
             escaped.append(arg)
   else:
       for arg in args:
          if isinstance(arg, str):
             escaped.append(arg.encode('string_escape'))
          elif isinstance(arg, unicode):
             escaped.append(arg.encode('unicode_escape'))
          else:
             escaped.append(arg)

   return tuple(escaped)

def to_bytes(s, encoding='utf-8'):
   return s if isinstance(s, bytes) else s.encode(encoding)

def to_text(s, encoding='utf-8'):
   text_t = str if sys.version_info.major > 2 else unicode
   return s if isinstance(s, text_t) else text_t(s, encoding)
