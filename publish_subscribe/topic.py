from .esc import esc, to_bytes

def build_topic_chain(topic):
   ''' We build the topic chain:
         if the event's topic is empty, the chain is ['']
         if the event's topic was A, the chain is ['', A]
         if the event's topic was A.B, the chain is ['', A, B]
         and so on

       Then, the chain is reversed, so instead ['', A, B] you get [B, A, ''].
       With this, the more specific topic come first.
       '''

   subtopics = topic.split(b".")
   topic_chain = [b""] # the empty topic
   for i in range(len(subtopics)):
      topic_chain.append(b'.'.join(subtopics[:i+1]))

   topic_chain.reverse()

   return topic_chain



def fail_if_topic_isnt_valid(topic, allow_empty=False):
   ''' Validate the topic and raise an exception if it fails.
       Only letters, digits, underscore, dashes and dots are allowed.

       If 'allow_empty' is true, the empty topic is allowed too.
       '''
   import string
   VALID = to_bytes(string.ascii_letters + string.digits + "_-.")

   for i, c in enumerate(topic):
      if c not in VALID:
         raise Exception("Character number %i is not a valid character '%s' in the topic '%s'." % esc(i+1, c, topic))

   if topic.startswith(b".") or topic.endswith(b"."):
      raise Exception("The topic can not start or end with a dot. The topic is '%s'." % esc(topic))
   
   if topic.startswith(b" ") or topic.endswith(b" "):
      raise Exception("The topic can not start or end with a space. The topic is '%s'." % esc(topic))

   if not allow_empty and topic == b"":
      raise Exception("The topic cannot be empty: '%s'" % esc(topic))

   subtopics = topic.split(b".")
   if len(subtopics) > 1:
      for subtopic in subtopics:
         fail_if_topic_isnt_valid(subtopic, allow_empty=False)

