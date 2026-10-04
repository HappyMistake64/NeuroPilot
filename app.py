"""Optional Gradio frontend. Use server.py for the lightweight offline planner."""
import json
from ai_tools import chat_fn, autonomy_run, fetch_and_sum, load_memory, project_zip


def build_demo():
    import gradio as gr
    def safe(function):
        def wrapped(*args):
            try:
                return function(*args)
            except (ValueError, RuntimeError, OSError) as error:
                raise gr.Error(str(error)) from error
        return wrapped
    with gr.Blocks(title="NeuroPilot", analytics_enabled=False) as demo:
        gr.Markdown("# NeuroPilot\nVolitelné modelové rozhraní. Plánování vytváří textové návrhy; příkazy se neprovádějí. Model nastav přes NEUROPILOT_MODEL.")
        with gr.Tab("Chat"):
            message = gr.Textbox(label="Dotaz", lines=3)
            explain = gr.Checkbox(label="Stručné zdůvodnění")
            output = gr.Textbox(label="Odpověď", lines=10)
            gr.Button("Odeslat").click(safe(chat_fn), [message, explain], output)
        with gr.Tab("Plánování"):
            goal = gr.Textbox(label="Cíl")
            steps = gr.Textbox(label="Počet kroků 1–8", value="4")
            explain = gr.Checkbox(label="Stručné zdůvodnění")
            output = gr.Textbox(label="Návrhy", lines=18)
            gr.Button("Navrhnout plán").click(safe(autonomy_run), [goal, steps, explain], output)
        with gr.Tab("Web research"):
            url = gr.Textbox(label="Veřejná URL")
            text = gr.Textbox(label="Obsah", lines=7)
            summary = gr.Textbox(label="Shrnutí", lines=7)
            memory = gr.Textbox(label="Paměť", lines=10)
            gr.Button("Načíst a shrnout").click(safe(fetch_and_sum), url, [text, summary])
            gr.Button("Zobrazit paměť").click(lambda: json.dumps(load_memory(), ensure_ascii=False, indent=2), None, memory)
        with gr.Tab("Generátor projektu"):
            name = gr.Textbox(label="Název projektu")
            spec = gr.Textbox(label="Specifikace", lines=4)
            output = gr.File(label="ZIP — vygenerovaný kód vyžaduje kontrolu")
            gr.Button("Vytvořit ZIP").click(safe(project_zip), [name, spec], output)
    return demo

if __name__ == "__main__":
    build_demo().launch(server_name="127.0.0.1", share=False)
