import sys
from PyQt6.QtWidgets import QApplication
from main_window import MainWindow

def main():
    """Entry point for the application."""
    app = QApplication(sys.argv)
    
    # Set application style if needed, e.g. Fusion
    app.setStyle("Fusion")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
