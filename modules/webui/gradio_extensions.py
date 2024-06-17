# based on https://github.com/AUTOMATIC1111/stable-diffusion-webui/blob/v1.6.0/modules/ui_gradio_extensions.py

import os
from pathlib import Path

import gradio as gr

from modules import config

from .localization import localization_js

GradioTemplateResponseOriginal = gr.routes.templates.TemplateResponse

WEBUI_DIR_PATH = Path(os.path.dirname(os.path.realpath(__file__)))


def read_file(fp):
    with open(WEBUI_DIR_PATH / fp, "r", encoding="utf-8") as f:
        return f.read()


def javascript_html():
    def s(text: str):
        return f'<script type="text/javascript">{text}</script>\n'

    def src(src: str):
        return f"<script src='{src}'></script>\n"

    def sf(fp: str):
        return s(read_file(fp))

    head = ""
    head += src("https://jsd.onmicrosoft.cn/npm/marked@12.0.2")
    head += s(localization_js(config.runtime_env_vars.language))
    head += sf("js/index.js")
    head += sf("js/localization.js")

    if config.runtime_env_vars.theme:
        head += s(f"set_theme('{config.runtime_env_vars.theme}');")

    return head


def css_html():
    head = f'<style>{read_file("css/style.css")}</style>'
    return head


def reload_javascript():
    js = javascript_html()
    css = css_html()

    def template_response(*args, **kwargs):
        res = GradioTemplateResponseOriginal(*args, **kwargs)
        res.body = res.body.replace(b"</head>", f"{js}</head>".encode("utf8"))
        res.body = res.body.replace(b"</body>", f"{css}</body>".encode("utf8"))
        res.init_headers()
        return res

    gr.routes.templates.TemplateResponse = template_response
