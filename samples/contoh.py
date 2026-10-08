# Buka file ini di Notepad, lalu coba NVDA+shift+K terus W di berbagai baris.
class Greeter:
    """Contoh class sederhana."""

    def __init__(self, names):
        self.names = names

    def hello(self):
        for names in self.names:
            if name:
                print("Halo",
                      name,
                      sep=", ")

def main():
    g = Greeter(["Budi", "Sari"])
    g.hello()

if __name__ == "__main__":
    main()
