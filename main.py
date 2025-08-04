import tkinter as tk
from window import MainWindow
from logger import StructuredLogger

if __name__ == "__main__":
    # Setup structured logging for the entire application
    StructuredLogger.setup_logging()

    # Create and run the main application window
    app = MainWindow()
    app.mainloop()