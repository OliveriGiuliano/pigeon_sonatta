# txt.py

import os
import pyperclip

def main():
    current_file = os.path.basename(__file__)
    py_files = [f for f in os.listdir('.') if f.endswith('.py') and f != current_file]

    collected_text = ""
    for filename in py_files:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
        collected_text += f"=== {filename} ===\n{content}\n\n"

    pyperclip.copy(collected_text.strip())
    print(f"Copied content of {len(py_files)} file(s) to clipboard.")

if __name__ == "__main__":
    main()
