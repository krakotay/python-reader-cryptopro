import gradio as gr
import os
from tkinter import Tk, filedialog
from process_cryptopro import process_signers


def on_browse():
    root = Tk()
    root.attributes("-topmost", True)
    root.withdraw()
    filename = filedialog.askdirectory()
    if filename:
        if os.path.isdir(filename):
            root.destroy()
            return str(filename)
        else:
            root.destroy()
            return str(filename)
    else:
        filename = "Folder not seleceted"
        root.destroy()
        return str(filename)


def main():
    with gr.Blocks() as demo:
        input_button = gr.Button("Выберите папку")
        path = gr.Textbox(label="Путь к папке", interactive=False)
        process_button = gr.Button("Запустить процесс")
        download_output = gr.File(label="Скачать обработанный файл")

        input_button.click(on_browse, outputs=path)
        process_button.click(fn=process_signers, inputs=path, outputs=download_output)
    return demo


demo = main()
demo.launch(inbrowser=True)
