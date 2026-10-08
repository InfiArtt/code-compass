# Code Compass practice file. Open it in Notepad and try the things below.
# (Indonesian version: latihan.py.)
#
# control+shift+space (parameter hint): put the caret on a call, for
#   example on "calculate_total" or inside its parentheses in main, and
#   press control+shift+space. Code Compass reads the parameters and
#   which argument you are on. Try Shop("Corner Shop", ...) and
#   shop.add_item(...) too.
# control+space: type "calc" on an empty line, then press control+space
#   a few times.
# F12: with the caret on a called name such as "calculate_total", jump to
#   where it is declared. control+alt+backspace takes you back.
# shift+F12: a list of every line that uses that name.
# F2: rename a name, for example "price" in calculate_total.
# alt+page down and alt+page up: move by function. alt+left arrow: to the
#   function or class around it.
# control+shift+O: the outline. NVDA+shift+K, then F: the family of the
#   function at the caret.
# control+alt+K: set a bookmark. control+alt+L and control+alt+J: jump
#   between bookmarks.
# NVDA+shift+K, then shift+T: the to-do and fixme notes in comments.
# control+F5: run this file. control+S: save and check for problems.
# Want to hear the error sound? Delete any ")" and wait a second.


def calculate_total(price, quantity, discount=0):
    """Total price after a discount, in percent."""
    gross = price * quantity
    reduction = gross * discount / 100
    return gross - reduction


def format_money(amount, with_symbol=True):
    """An amount as money text, for example 1234.5 -> "$1,234.50"."""
    text = f"{amount:,.2f}"
    return f"${text}" if with_symbol else text


class Item:
    def __init__(self, name, price, stock=1):
        self.name = name
        self.price = price
        self.stock = stock

    def in_stock(self):
        return self.stock > 0


class Shop:
    """A small shop with a list of items."""

    def __init__(self, name, city, owner="Rafli"):
        self.name = name
        self.city = city
        self.owner = owner
        self.items = []

    def add_item(self, name, price, stock=1):
        item = Item(name, price, stock)
        self.items.append(item)
        return item

    def find(self, word, in_stock_only=False):
        found = []
        for item in self.items:
            if word.lower() in item.name.lower():
                if in_stock_only and not item.in_stock():
                    continue
                found.append(item)
        return found

    def report(self):
        # TODO: sort the items from the most expensive
        lines = [f"{self.name} in {self.city}, owned by {self.owner}"]
        for number, item in enumerate(self.items, start=1):
            status = "in stock" if item.in_stock() else "sold out"
            lines.append(f"  {number}. {item.name}: {format_money(item.price)} ({status})")
        return "\n".join(lines)


def split_evenly(total, people):
    """Split a total between people; people must not be zero."""
    try:
        return total / people
    except ZeroDivisionError:
        # FIXME: tell the user with a clearer message
        return 0


def main():
    shop = Shop("Corner Shop", "Bandung", owner="Rafli")
    shop.add_item("Arabica Coffee", 12.5, stock=3)
    shop.add_item("Jasmine Tea", 4.75, stock=5)
    shop.add_item("Palm Sugar", 3.2, stock=0)

    print(shop.report())
    print()

    total = calculate_total(15, 3, discount=10)
    print("Total:", format_money(total))
    print("Each:", format_money(split_evenly(total, 2)))

    for item in shop.find("tea", in_stock_only=True):
        print("Found:", item.name)

    # Remove the # on the line below to try an error when running
    # (control+F5), then press F8 to go to its line.
    # print(calculate_total(10, "two"))


if __name__ == "__main__":
    main()
