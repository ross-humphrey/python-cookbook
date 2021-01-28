"""
This script imports a python module via url.

This solution installs an instance of a finder object UrlMetaFinder
as the last entry in the sys.meta_path. When
modules are imported the finders in sys.meta_path are stepped thru
in order to locate the module. UrlMetaFinder becomes a finder of last
resort when the normal options are exhausted.

UrlMetaFinder wraps around a user-specified URL. Internally
said finder builds a set of valid links by scraping them from the URL. When
the import is done - the module name is compared against this set of
known links. If a match is found, a separate UrlModuleLoader class is
used to load source code from the remote machine and create the resulting
module object.
"""
import sys
import importlib.abc
import imp
from urllib.request import urlopen
from urllib.error import HTTPError, URLError
from html.parser import HTMLParser

# Debugging
import logging

log = logging.getLogger(__name__)


# Get links from a given URL
def _get_links(url):
    class LinkParser(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag == "a":
                attrs = dict(attrs)
                links.add(attrs.get("href").rstrip("/"))

    links = set()
    try:
        log.debug("Getting links from %s" % url)
        u = urlopen(url)
        parser = LinkParser()
        parser.feed(u.read().decode("utf-8"))
    except Exception as e:
        log.debug("Could not get links %s" % e)
    log.debug("links: %r", links)
    return links


class UrlMetaFinder(importlib.abc.MetaPathFinder):
    def __init__(self, baseurl):
        self._baseurl = baseurl
        self._links = {}
        self._loaders = {baseurl: UrlModuleLoader(baseurl)}

    def find_module(self, fullname: str, path=None):
        log.debug("find_module: fullname=%r, path=%r", fullname, path)
        if path is None:
            baseurl = self._baseurl
        else:
            if not path[0].startswith(self._baseurl):
                return None
            baseurl = path[0]

        parts = fullname.split(".")
        basename = parts[-1]
        log.debug("find_module: baseurl=%r, basename=%r", baseurl, basename)

        # Check link cache
        if basename not in self._links:
            self._links[baseurl] = _get_links(baseurl)

        # Check if it's a package
        if basename in self._links[baseurl]:
            log.debug("find_module: trying package %r", fullname)
            fullurl = self._baseurl + "/" + basename
            # Attempt to load the package (which accesses __init__.py)
            loader = UrlPackageLoader(fullurl)
            try:
                loader.load_mdule(fullname)
                self._links[fullurl] = _get_links(fullurl)
                self._loaders[fullurl] = UrlModuleLoader(fullurl)
                log.debug("find_module: package %r loaded", fullname)
            except ImportError as e:
                log.debug("find_module: package failed. %s", e)
                loader = None
            return loader

        # Normal module
        filename = basename + ".py"
        if filename in self._links[baseurl]:
            log.debug("find_module: module %r found", fullname)
            return self._loaders[baseurl]
        else:
            log.debug("find_module: module %r not found", fullname)
            return None

    def invalidate_caches(self) -> None:
        log.debug("invalidating link cache")
        self._links.clear()
