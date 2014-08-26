#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Frozen-Blog.
A minimal static blog written with Frozen-Flask and MetaFiles.
"""


import math
import os
import posixpath
import sys
import time
import traceback

from argparse import ArgumentParser, RawDescriptionHelpFormatter


# Information and error messages:

def outln(line):
    """ Write 'line' to stdout, using the platform encoding and newline format. """
    print(line, flush = True)


def errln(line):
    """ Write 'line' to stderr, using the platform encoding and newline format. """
    print('blog.py: error:', line, file = sys.stderr, flush = True)


def warnln(line):
    """ Like errln() but for warning messages. """
    print('blog.py: warning:', line, file = sys.stderr, flush = True)


# Non-builtin imports:

try:
    from flask import Flask, abort, render_template, render_template_string, request, url_for
    from flask_frozen import Freezer
    from MetaFiles import MetaFiles

    import markdown
    import yaml

except ImportError:
    errln('Frozen-Blog requires the following modules:')
    errln('Frozen-Flask 0.11+    - <https://pypi.python.org/pypi/Frozen-Flask>')
    errln('Markdown 2.3.1+       - <https://pypi.python.org/pypi/Markdown>')
    errln('MetaFiles 2014.01.11+ - <https://github.com/Beluki/MetaFiles>')
    errln('PyYAML 3.10+          - <https://pypi.python.org/pypi/PyYAML>')
    sys.exit(1)


# Utils:

def merge_dicts(a, b):
    """
    Merge 'a' and 'b' into a single dict.
    When the same keys are present in both dicts, 'b' has priority.
    """
    return dict(list(a.items()) + list(b.items()))


# Default metadata renderer, YAML:

def meta_renderer(meta):
    metadata = yaml.load(meta)

    # empty metadata:
    if metadata is None:
        return {}

    # dict?
    if not isinstance(metadata, dict):
        raise ValueError('Invalid metadata, not a dict: %s' % str(metadata))

    return metadata


# Default body renderers, none for pages, markdown for posts:

def page_renderer(body):
    return body

def post_renderer(body):
    return markdown.markdown(body, extensions = ['codehilite'])


# Sensible default configuration:

DEFAULT_CONFIGURATION = {
    'DEBUG': True,

    'PAGE_ROOT': 'page',
    'PAGE_EXTENSIONS': '.html',
    'PAGE_ENCODING': 'utf-8-sig',
    'PAGE_META_RENDERER': meta_renderer,
    'PAGE_BODY_RENDERER': page_renderer,

    'POST_ROOT': 'post',
    'POST_EXTENSIONS': '.markdown',
    'POST_ENCODING': 'utf-8-sig',
    'POST_META_RENDERER': meta_renderer,
    'POST_BODY_RENDERER': post_renderer,

    'FREEZER_BASE_URL': 'http://localhost/',
    'FREEZER_DESTINATION': 'build',
    'FREEZER_DESTINATION_IGNORE': ['.*'],
    'FREEZER_RELATIVE_URLS': False,
    'FREEZER_REMOVE_EXTRA_FILES': True,

    'WWW_HOST': '127.0.0.1',
    'WWW_PORT': 8000,
}


# Data representation:

class Target(object):
    """
    A Target is a MetaFile wrapper with an additional 'path'.
    It represents a post or a page in the blog.
    """
    def __init__(self, metafile, path):
        self.metafile = metafile
        self.path = path

    @property
    def meta(self):
        return self.metafile.meta

    @property
    def body(self):
        return self.metafile.body


def metafiles_as_targets(metafiles):
    """
    Iterate 'metafiles', yielding Target items with a 'path' from them.
    The 'path' is the full filepath *without extension* from the
    metafiles root, using posix separators.
    """
    for metafile in metafiles:
        fullbase, extension = os.path.splitext(metafile.filepath)
        path = os.path.relpath(fullbase, metafiles.root)
        path = path.replace(os.sep, posixpath.sep)

        yield Target(metafile, path)


class Context(object):
    """ Maintains the collection of pages and posts in the blog. """

    def __init__(self):
        self.pages = []
        self.pages_by_path = {}

        self.posts = []
        self.posts_by_path = {}
        self.posts_by_tag = {}

        self._pages_metafiles = None
        self._posts_metafiles = None

    def initialize(self, config):
        """ Configure context options from a given 'config' dictionary. """
        self._pages_metafiles = MetaFiles(
            root        = config['PAGE_ROOT'],
            extensions  = config['PAGE_EXTENSIONS'],
            encoding    = config['PAGE_ENCODING'],
            meta_render = config['PAGE_META_RENDERER'],
            body_render = config['PAGE_BODY_RENDERER'])

        self._posts_metafiles = MetaFiles(
            root        = config['POST_ROOT'],
            extensions  = config['POST_EXTENSIONS'],
            encoding    = config['POST_ENCODING'],
            meta_render = config['POST_META_RENDERER'],
            body_render = config['POST_BODY_RENDERER'])

    def load_pages(self):
        """
        Load all the pages in the blog.
        Can be called multiple times to reload.
        On errors, the previous content is preserved.
        """
        self._pages_metafiles.load()

        pages = []
        pages_by_path = {}

        for page in metafiles_as_targets(self._pages_metafiles):
            pages.append(page)
            pages_by_path[page.path] = page

        self.pages = pages
        self.pages_by_path = pages_by_path

    def load_posts(self):
        """
        Load all the posts in the blog, sorting by date and grouping by tag.
        Posts without date are skipped (considered drafts).
        Posts without tags are put in a default ['untagged'].
        Can be called multiple times to reload.
        On errors, the previous content is preserved.
        """
        self._posts_metafiles.load()

        posts = []
        posts_by_path = {}
        posts_by_tag = {}

        for post in metafiles_as_targets(self._posts_metafiles):
            if 'date' in post.meta:
                posts.append(post)
                posts_by_path[post.path] = post

        # sort first so that tags have their posts sorted too:
        posts.sort(key = lambda post: post.meta['date'], reverse = True)

        for post in posts:
            post.meta.setdefault('tags', ['untagged'])
            for tag in post.meta['tags']:
                posts_by_tag.setdefault(tag, [])
                posts_by_tag[tag].append(post)

        self.posts = posts
        self.posts_by_path = posts_by_path
        self.posts_by_tag = posts_by_tag

    def load(self):
        """ Load all the pages and posts in the blog. """
        self.load_pages()
        self.load_posts()

    @property
    def environment(self):
        """ Returns a dict containing all our data, for template rendering. """
        return {
            'pages'         : self.pages,
            'pages_by_path' : self.pages_by_path,
            'posts'         : self.posts,
            'posts_by_path' : self.posts_by_path,
            'posts_by_tag'  : self.posts_by_tag
        }

    def render_template(self, template, **context):
        """
        Like Flask's 'render_template()' but includes our own environment
        as well as the variables passed as parameters.
        """
        environment = merge_dicts(self.environment, context)
        return render_template(template, **environment)


# Pagination:

class Pagination(object):
    """
    Represents the nth 'page' from 'iterable' when split in pages
    containing at least 'per_page' items.
    """
    def __init__(self, iterable, page, per_page):
        self.iterable = iterable
        self.page = page
        self.per_page = per_page

    @property
    def total_pages(self):
        """ Number of available pages. """
        return int(math.ceil(len(self.iterable) / self.per_page))

    @property
    def has_prev(self):
        """ True when there is a previous page. """
        return self.page > 1

    @property
    def has_next(self):
        """ True when there is a next page. """
        return self.page < self.total_pages

    @property
    def items(self):
        """ Get all the items from our iterable for the current page. """
        index = self.page - 1

        offset = index * self.per_page
        length = offset + self.per_page

        return self.iterable[offset:length]


# Flask application:

blog = Flask(__name__)
blog.config.update(DEFAULT_CONFIGURATION)
blog.freezing = False

context = Context()


# Initialization and reloading:

@blog.before_first_request
def init_context():
    context.initialize(blog.config)
    context.load()

@blog.before_request
def auto_update_context():

    # avoid reloading when freezing:
    if blog.freezing:
        return

    # avoid reloading on static files:
    if request.endpoint == 'static':
        return

    # reload on explicit view requests only (e.g. not favicons):
    if request.endpoint in blog.view_functions:
        context.load()


# Template additions:

@blog.template_filter('templatize')
def templatize(text, environment = {}):
    return render_template_string(text, **environment)

@blog.template_filter('paginate')
def paginate(iterable, page, per_page):
    return Pagination(iterable, page, per_page)


# Convenient url_for() wrappers:

def url_index(page = None):
    return url_for('index', page = page)

def url_archive(tag = None):
    return url_for('archive', tag = tag)

def url_page(page):
    return url_for('page', path = page.path)

def url_page_by_path(path):
    return url_for('page', path = path)

def url_post(post):
    return url_for('post', path = post.path)

def url_post_by_path(path):
    return url_for('post', path = path)

def url_static(filename):
    return url_for('static', filename = filename)


# Note that those are provided for both templates and pages/posts,
# given 'templatize' is available:

@blog.context_processor
def url_for_wrappers():
    return {
        'url_index'        : url_index,
        'url_archive'      : url_archive,
        'url_page'         : url_page,
        'url_page_by_path' : url_page_by_path,
        'url_post'         : url_post,
        'url_post_by_path' : url_post_by_path,
        'url_static'       : url_static,
    }


# Routes:

@blog.route('/')
@blog.route('/<int:page>/')
def index(page = 1):
    return context.render_template('index.html', page = page)

@blog.route('/archive/')
@blog.route('/archive/<tag>/')
def archive(tag = None):
    if tag is not None and not tag in context.posts_by_tag:
        abort(404)
    return context.render_template('archive.html', tag = tag)

@blog.route('/page/<path:path>/')
def page(path):
    current_page = context.pages_by_path.get(path) or abort(404)
    return context.render_template('page.html', page = current_page)

@blog.route('/post/<path:path>/')
def post(path):
    current_post = context.posts_by_path.get(path) or abort(404)
    return context.render_template('post.html', post = current_post)


# Running modes:

def run_freezer():
    """ Freeze the current site state to the output folder. """
    blog.config.from_pyfile('freezing.conf', silent = True)

    try:
        outln('Freezing...')

        start = time.clock()
        total = Freezer(blog).freeze()

        outln('Frozen: %s items.' % len(total))
        outln('Time: %s seconds.' % (time.clock() - start))

    except Exception as err:
        errln('Exception while freezing: %s' % str(err))

        if not blog.debug:
            warnln('The following traceback is not comprehensive.')
            warnln('Set DEBUG = True in freezing.conf for a more detailed traceback.')

        errln(traceback.format_exc())
        sys.exit(1)


def run_server():
    """ Run the local web server and watch for changes. """
    blog.run(host = blog.config['WWW_HOST'],
             port = blog.config['WWW_PORT'],

             # also reload on configuration file changes:
             extra_files = ['blog.conf', 'freezing.conf'])


# Parser:

def make_parser():
    parser = ArgumentParser(
        description = __doc__,
        formatter_class = RawDescriptionHelpFormatter,
    )

    group = parser.add_mutually_exclusive_group(required = True)

    group.add_argument('-f', '--freeze',
        help = 'freeze the current site state to the output folder',
        action = 'store_true')

    group.add_argument('-s', '--server',
        help = 'run the local web server and watch for changes',
        action = 'store_true')

    return parser


# Entry point:

def main():
    parser = make_parser()
    options = parser.parse_args()

    blog.config.from_pyfile('blog.conf', silent = True)

    if options.server:
        blog.freezing = False
        run_server()

    if options.freeze:
        blog.freezing = True
        run_freezer()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass

