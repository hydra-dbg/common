import os, sys
import os.path

DOCTEST_PATH=os.path.join(os.path.dirname(os.path.abspath(__file__)), "doctestpyjs.py")

def doctests(source_dir, whitelist):
   return [os.path.abspath(fname) for fname in whitelist if os.path.isfile(fname) \
                     and os.path.splitext(fname)[1] == ".rst"]


def run_doctests(sources, flags):
   for source in sources:
      print "Run tests in %s" % source
      cmd = ("python %s %s %s" % (
         DOCTEST_PATH,
         flags,
         source))

      os.system(cmd)
   
if __name__ == '__main__':
   working_directory = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.path.pardir)
   source_dir = os.path.join(working_directory, "regress")

   # Flags:
   #    d:  Diff output, doctest.REPORT_NDIFF
   #    L:  Log each test
   if sys.argv[1].startswith("-"):
      flags = sys.argv[1]
      del sys.argv[1]
   else:
      flags = ""

   try:
      blacklist_token_pos = sys.argv[1:].index("--")
      
      whitelist = set(sys.argv[1:1+blacklist_token_pos])
      blacklist = set(sys.argv[blacklist_token_pos+2:])

   except ValueError:
      whitelist = set(sys.argv[1:])
      blacklist = set()
      

   whitelist = list((whitelist - blacklist))
   whitelist.sort()

   sources = doctests(source_dir, whitelist)
   run_doctests(sources, flags)

