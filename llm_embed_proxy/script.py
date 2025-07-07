"""A mitmproxy script to embed and semantically search visited pages."""

from concurrent.futures import ThreadPoolExecutor
import gzip
import json
import logging
import re
import socket
from ipaddress import ip_address
from urllib.parse import urlparse, urlunparse
from urllib.request import urlopen, Request
from typing import Optional

from flask import Flask, render_template, request
import frontmatter # type: ignore
import llm
from mitmproxy import ctx
from mitmproxy.addons.asgiapp import WSGIApp
from mitmproxy.http import HTTPFlow, Headers
from mitmproxy import tls
import sqlite_utils


logger = logging.getLogger(__name__)
# Avoid printing a progress bar during encode
logging.getLogger("sentence_transformers.SentenceTransformer").setLevel('WARNING')


def is_private_host(host: str) -> bool:
    """Return True if host is not publicly reachable."""
    # 1. Obvious local names
    if host == "localhost" or host.endswith(".local"):
        return True
    # 2. Literal IP?
    try:
        return not ip_address(host).is_global
    except ValueError:
        # host is not a literal IP
        pass
    # 3. Resolve hostname
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        # cannot resolve -> treat as private
        return True
    return all(
        not ip_address(sockaddr[0]).is_global
        for *_, sockaddr in infos
    )

# Hosts whose TLS traffic should be tunneled instead of intercepted
IGNORE_TLS_HOSTS = {
    # LLM and AI APIs
    "api.openai.com",
    "api.anthropic.com",
    "api.cohere.ai",
    "api.ai21.com",
    "api.stability.ai",
    "api.replicate.com",
    "api.pinecone.io",
    # Payment / finance
    "api.stripe.com",
    "api.paypal.com",
    # Developer / infrastructure
    "api.github.com",
    # Social / collaboration
    "api.twitter.com",
    "api.snapchat.com",
    # Storage / content
    "api.dropboxapi.com",
    "api.box.com"
}


class EmbedVisitedPages:
    def load(self, loader):
        loader.add_option(
            name='llm_embed_model',
            typespec=str,
            default='text-embedding-3-large',
            help="LLM embedding model"
        )
        loader.add_option(
            name='llm_embed_collection',
            typespec=str,
            default='visited-pages',
            help="Collection to store embeddings in"
        )

    def running(self):
        self.pool = ThreadPoolExecutor(max_workers=1)

    def tls_clienthello(self, data: tls.ClientHelloData):
        if data.context.client.sni in IGNORE_TLS_HOSTS:
            data.ignore_connection = True

    def response(self, flow: HTTPFlow):
        if is_private_host(flow.request.host): return
        if flow.request.method != "GET": return
        if flow.response.status_code != 200: return

        self.pool.submit(embed, flow.copy())

    def done(self):
        # Gracefully shut down the thread pool when mitmproxy exits
        self.pool.shutdown(wait=True)

search = Flask('llm_embed_proxy.script')

@search.route('/')
def search_form() -> str:
    return render_template('index.html')

@search.route('/search', methods=['POST'])
def search_results():
    q = request.form.get('q')
    results = collection().similar(q)

    return render_template('search_results.html', q=q, results=results)

@search.route('/cache', methods=['GET'])
def cached_content():
    content = cached(collection(), request.args['id'])
    if content is None:
        return "not cached", 404
    return content, {'Content-Type': 'text/plain; charset=utf-8'}


addons = [
    EmbedVisitedPages(),
    WSGIApp(search,
        ctx.options.listen_host or "localhost",
        ctx.options.listen_port or 8080
    )
]


#------------------------------------------------------------------------------#


def embed(flow: HTTPFlow) -> None:
    metadata, content = pure.md(flow.request.url, flow.request.headers)
    content = cleanup(content)
    logger.info(f"Embedding {len(content)} characters")
    try:
        collection(create=True).embed(flow.request.url, content, metadata, store=True)
    except Exception as e:
        logger.error(e)
    logger.info("done")


class pure:
    @staticmethod
    def md(url: str, headers) -> tuple[dict[str, str], str]:
        parsed = urlparse(url)
        url = urlunparse((
            parsed.scheme, "pure.md", f'/{parsed.netloc}{parsed.path}',
            parsed.params, parsed.query, ''
        ))
        for header in ('Accept', 'Cache-Control', 'Host', 'Pragma'):
            headers.pop(header, None)
        headers['Accept-Encoding'] = 'gzip'
        with urlopen(Request(url, headers=headers), timeout=30) as response:
            if response.info().get('Content-Encoding') == 'gzip':
                with gzip.open(response, "rt", encoding='utf-8') as decompressed:
                    content = decompressed.read()
            else:
                content = response.read().decode('utf-8')
        try:
            metadata, content = frontmatter.parse(content,
                handler=frontmatter.YAMLHandler()
            )
            metadata = {k: str(v) for k, v in metadata.items()}
            return metadata, content
        except Exception as e:
            logger.error(e)
            return {}, content


def cleanup(content: str) -> str:
    return REMOVE_PATTERN.sub("", content).strip()

REMOVE_PATTERN = re.compile("|".join(map(re.escape, [
    "Output not what you expected? Email puremd@crawlspace.dev",
    "Some privacy related extensions may cause issues on x.com. Please disable them and try again.",
    "Nicht alle Bilder konnten vollständig geladen werden. Bitte schließen Sie die Druckvorschau bis alle Bilder geladen wurden und versuchen Sie es noch einmal."
])))


def collection(create=False):
    return llm.Collection(ctx.options.llm_embed_collection,
        sqlite_utils.Database(llm.user_dir() / "embeddings.db"),
        model_id=ctx.options.llm_embed_model, create=create
    )


def cached(collection, url) -> Optional[str]:
    rows = list(
        collection.db['embeddings'].rows_where(
            "collection_id = ? AND id = ?", (collection.id, url)
        )
    )
    content = None
    if rows:
        row = rows[0]
        if row['metadata']:
            # Reconstruct frontmatter as part of the content
            post = frontmatter.Post(row['content'],
                handler=frontmatter.YAMLHandler(), **json.loads(row['metadata'])
            )
            content = frontmatter.dumps(post)
        else:
            content = row['content']

    return content
