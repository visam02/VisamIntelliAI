import tkinter as tk
from tkinter import messagebox

def main():
    print("Starting Tkinter test...")
    try:
        root = tk.Tk()
        root.title("Tkinter Test")
        root.geometry("300x200")
        label = tk.Label(root, text="If you see this, Tkinter is working!")
        label.pack(pady=20)
        btn = tk.Button(root, text="Click Me", command=lambda: print("Button Clicked!"))
        btn.pack()
        print("Window should be open. Close it to end test.")
        root.mainloop()
    except Exception as e:
        print(f"Tkinter Test Failed: {e}")

if __name__ == "__main__":
    main()
