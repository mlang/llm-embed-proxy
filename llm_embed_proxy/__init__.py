import click
import llm


@llm.hookimpl
def register_commands(cli):
    @cli.command()
    @click.option('-m', '--model', default="sentence-transformers/Qwen/Qwen3-Embedding-0.6B", show_default=True)
    @click.option('-c', '--collection', default='visited-pages', show_default=True)
    @click.option('--host', default="localhost", show_default=True)
    @click.option('--port', default="8080", show_default=True)
    def embed_proxy(model, collection, host, port):
        """Proxy for similarity search over visited pages"""

        from pathlib import Path
        from mitmproxy.tools.main import mitmdump

        mitmdump([
            '--listen-host', host, '--listen-port', port,
            '--set', f'llm_embed_model={model}',
            '--set', f'llm_embed_collection={collection}',
            '--script', str(Path(__file__).absolute().parent / "script.py")
        ])
