# llm-embed-proxy

A proxy that embeds every web page you visit and lets you run similarity searches.

1. Each successful **HTTP GET 200** response (except for localhost) is re-fetched from [pure.md](https://pure.md/) to obtain clean Markdown.
2. The cleaned text is embedded through [llm](https://github.com/simonw/llm).
3. A minimal Flask UI provides search and cached-page views.

## Installation

This is not a stand-alone program.  It is a plugin for [llm](https://github.com/simonw/llm).  If you are not using `llm` yet, install it with `pipx` first.

```bash
pipx install llm
```

Now you can install this plugin:

```bash
llm install git+https://github.com/mlang/llm-embed-proxy
```

To be able to run a local embedding model, you need to install the `llm-sentence-transformers` plugin and register/download a model.  This step is optional if you happen to have an OpenAI API key and want to use their embedding endpoint.

```bash
llm install llm-sentence-transformers
llm sentence-transformers register Qwen/Qwen3-Embedding-0.6B
```

## Running

```bash
llm embed-proxy --model sentence-transformers/Qwen/Qwen3-Embedding-0.6B
```

Point your browser/system proxy to `localhost:8080` and visit `http://localhost:8080/` to search.

### TLS Certificate

`llm-embed-proxy` uses [mitmproxy](https://mitmproxy.org/) under the hood.
If you haven't used mitmproxy in the past, the first time you launch `llm embed-proxy` `mitmproxy` will generate a CA certificate in `~/.mitmproxy/`.
To avoid certificate warnings, you can add the mitmproxy CA certificate to your system.

Here is how it would work on a Debian system:

```bash
sudo cp ~/.mitmproxy/mitmproxy-ca-cert.pem /usr/local/share/ca-certificates/mitmproxy-ca-cert.crt
sudo /sbin/update-ca-certificates
```
