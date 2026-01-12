from .url import UrlOutputHandler

class FacebookUrlOutputHandler(UrlOutputHandler):
    def __init__(self):
        super().__init__(platform="facebook")