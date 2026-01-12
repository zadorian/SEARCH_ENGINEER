from .url import UrlOutputHandler

class GoogleMapsUrlOutputHandler(UrlOutputHandler):
    def __init__(self):
        super().__init__(platform="google_maps")