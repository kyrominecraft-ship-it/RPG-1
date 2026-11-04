"""Run the native folder dialog on its own main thread/process."""
import json
import tkinter as tk
from tkinter import filedialog


def main():
    window = tk.Tk()
    window.withdraw()
    try:
        path = filedialog.askdirectory(title='Choose your campaign folder', mustexist=True)
        print(json.dumps({'path': path}))
    finally:
        window.destroy()


if __name__ == '__main__':
    main()
