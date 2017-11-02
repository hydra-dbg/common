import doctest, re, sys, subprocess, time, socket, traceback, pprint
import argparse

GLOBAL_FLAGS = 0
PASS = doctest.register_optionflag("PASS")

old_OutputChecker_check_output = doctest.OutputChecker.check_output
def _custom_check_output(self, want, got, optionflags):
   if optionflags & PASS:
      return True

   return old_OutputChecker_check_output(self, want, got, optionflags)

doctest.OutputChecker.check_output = _custom_check_output


JS_SESSION_ADDRESS = ('', 5001)

class DocTestJSParser(doctest.DocTestParser):
   '''This is an adaptation of the original parser. Instead of
      be using '>>>' for the interactive session and '#' for commenting
      a line, they are replaced by 'js>' and '//' respectively, so they
      can be used with a javascript session.'''
   _EXAMPLE_RE = re.compile(r'''
        # Source consists of a PS1 line followed by zero or more PS2 lines.
        (?P<source>
            (?:^(?P<indent> [ ]*) js>    .*)        # PS1 line
            (?:\n           [ ]*  \.\.\. .*)*)      # PS2 lines
        \n?
        # Want consists of any non-blank lines that do not start with PS1.
        (?P<want> (?:(?![ ]*$)    # Not a blank line
                     (?![ ]*js>)  # Not a line starting with PS1
                     .*$\n?       # But any other line
                  )*)
        ''', re.MULTILINE | re.VERBOSE)


   _IS_BLANK_OR_COMMENT = re.compile(r'^[ ]*(//.*)?$').match
    
   _OPTION_DIRECTIVE_RE = re.compile(r'//\s*doctest:\s*([^\n\'"]*)$',
                                      re.MULTILINE)


class JavascriptSessionError(Exception):
   def __init__(self, *args, **kargs):
      Exception.__init__(self, *args, **kargs)

class JavascriptSession(object):
   def __init__(self, address):
      self.address = address
      self.PS1, self.PS2 = "js> ", "..."
      self.PS2_full = re.compile(r"\.\.\.[.]* ")

   def connect(self):
      # Connect with the remote javascript session
      # TODO this is a problem, the connection is not explicit closed
      self.remote_console = socket.socket()
      self.remote_console.settimeout(0.5)
      retries = 5
      connected = False
      while retries > 0 and  not connected:
         try:
            self.remote_console.connect(self.address)
            connected = True
         except socket.error as e:
            retries = retries - 1
            time.sleep(0.1)
            ex = e

      if not connected:
         raise JavascriptSessionError(str(ex))

      self.remote_console.settimeout(60*5)
      try:
         # Wait for the prompt of the remote session
         self.test(None, discard_response=True)

         return
      except socket.error as e:
         raise JavascriptSessionError(str(e))

   def close_connection(self):
      try:
         self.remote_console.shutdown(socket.SHUT_RDWR)
      except:
         pass

      self.remote_console.close()

   def shutdown(self):
      self.close_connection()


   def test(self, data, discard_response=False):
      '''Takes the data as valid javascript code and send it to the remote 
         javascript session. Then, waits for the prompt 'js> ' (see the
         PS1 attribute) so we can assume that the code was executed and 
         its output was received by us. Finally write this output into the 
         stdout stream (so it can be captured by the doctest's workflow.'''

      try:
         #import pdb
         #pdb.set_trace()
         if data is not None:
            self.remote_console.sendall(data)

         buf = self.remote_console.recv(1024)

         while True:
            while buf[:3] == self.PS2:
               PS2_prefix = self.PS2_full.match(buf)
               buf = buf[PS2_prefix.end():]

            if buf[-4:] == self.PS1:
               response = buf[:-4]
               if not response:
                  return None

               if not discard_response:
                  sys.stdout.write(response)

               return None

            next_chunk = self.remote_console.recv(1024)
            if not next_chunk:
               return None

            buf += next_chunk
      except socket.error as e:
         raise JavascriptSessionError("Original traceback:\n%s\n%s" % (traceback.format_exc(), str(e)))


class DocTestMixedParser(doctest.DocTestParser):
   '''This object will parse python and javascript code and will keep
      track of which type is each source code.
      Then, all the tests are mixed and sorted so their order match the 
      lexical order in which the tests were found during the parsing stage.'''

   def __init__(self):
      self.pyparser = doctest.DocTestParser()
      self.jsparser = DocTestJSParser()

      self.javascript_remote_session = JavascriptSession(JS_SESSION_ADDRESS)

   def get_doctest(self, string, globs, name, filename, lineno):
      try:
         self.javascript_remote_session.connect()
         self.skip_javascript_tests = False
      except JavascriptSessionError as e:
         self.skip_javascript_tests = True
         ex = e

      globs = globs.copy()
      globs["_js_test"] = self.javascript_remote_session.test

      _doctest = doctest.DocTest(self.get_examples(string, name), globs,
                       name, filename, lineno, string)     

      if self.skip_javascript_tests and self.has_javascript_tests:
         print("[Warning] The javascript tests will BE SKIPPED! because the connection failed:\n %s" % str(ex))

      return _doctest

   def get_examples(self, string, name):
      self.type_of_source = {}
      all_examples = []
      self.has_javascript_tests = False
      for type, parser in [("py", self.pyparser), ("js", self.jsparser)]:
         examples = parser.get_examples(string, name)

         if self.skip_javascript_tests and type == "js":
            for example in examples:
               example.options[doctest.OPTIONFLAGS_BY_NAME["SKIP"]] = True

         if type == "js":
            self.has_javascript_tests = len(examples) > 0

         for example in examples:
            link = (example.lineno, type)
            try:
               self.type_of_source[example.source].append(link)
            except KeyError:
               self.type_of_source[example.source] = [link]


         all_examples.extend(examples)

      # sort the examples and its types in the same order that were found in the file
      # the types are then reversed so they can be 'pop-ed' in the same order that
      # its example is executed.
      all_examples.sort(key=lambda this: this.lineno)
      for source in self.type_of_source.keys():
         self.type_of_source[source].sort(key=lambda this: this[0], reverse=True)

      return all_examples

   def shutdown(self):
      self.javascript_remote_session.shutdown()


# Create the mixed parser
mixed_parser = DocTestMixedParser()

# This a very funny and dirty part. Because the DocTestRunner uses the built-in
# 'compile' function to compile the source code (because he assume that it is python 
# code), this is the only way to change that behaviour so he can support python
# and javascript code.
try:
    import __builtin__ as builtins
except ImportError:
    import builtins

original_compile_func = builtins.compile
literal_string_re = re.compile(r"(\W|^)[uUbB]([rR]?[\'\"])", re.UNICODE)

def display(s):
    global literal_string_re
    if s is not None:
        _repr = pprint.pformat(s)
        _repr = re.sub(literal_string_re, r'\1\2', _repr)
        print(_repr)

def compile(source, filename, *args, **kargs):
   '''Take the source and compile it into a runnable python code.
      Each source is looked up in the global mixed parser table
      to know of what type the source is it.
      If it is python, just  execute the 'compile' built-in function.
      If it is javascript, invoke the _js_test function to send the
      source to the remote javascript session so it is evaluated there.'''
   # this custom compile function will apply to the particular doctest
   # any other file will not work
   if not filename.startswith("<doctest "):
       return original_compile_func(source, filename, *args, **kargs)

   _, source_type = mixed_parser.type_of_source[source].pop()

   sys.stderr.write(".")

   sys.stderr.flush()
   
   # hook the displayhook to use pprint instead of repr
   sys.displayhook = display

   if source_type == "js":
      js_code = source
      python_code_wrapper = "_js_test(r'''%s''')\n" % js_code

      source = python_code_wrapper

   elif source_type == "py":
      pass

   else:
      raise Exception("Unknown source's type: %s" % source_type)

   return original_compile_func(source, filename, *args, **kargs)

builtins.compile = compile    # patching!


# This is to override the default argument 'parser' so we can use DocTestMixedParser
# here, instead of the default DocTestParser.
original_testfile_func = doctest.testfile
def testfile(filename, *args, **kargs):

   global GLOBAL_FLAGS
   optionflags = kargs.get('optionflags', 0) | GLOBAL_FLAGS

   kargs['optionflags'] = optionflags
   kargs['parser'] = mixed_parser

   print(filename)
   try:
      return original_testfile_func(filename, *args, **kargs)
   finally:
      sys.stderr.write("\n")
      sys.stderr.flush()
      mixed_parser.shutdown() # this object is VERY coupled!!

doctest.testfile = testfile   # patching!

def parse_cmdline():
    global GLOBAL_FLAGS

    parser = argparse.ArgumentParser(description='Run doctests')
    parser.add_argument('-d', '--diff', action='store_true')
    parser.add_argument('-v', action='store_true')
    parser.add_argument('--skip', nargs='*', default=[])
    parser.add_argument('tests', nargs='+')

    args = parser.parse_args()

    if args.diff:
        GLOBAL_FLAGS |= doctest.REPORT_NDIFF

    blacklist = set(args.skip)
    whitelist = set(args.tests)
    
    tests = list((whitelist - blacklist))
    tests.sort()

    sys.argv[1:] = tests

    if args.v:
        sys.argv.insert(1, '-v') # used by the original doctests module

if __name__ == "__main__":
    parse_cmdline()
    sys.exit(doctest._test())

