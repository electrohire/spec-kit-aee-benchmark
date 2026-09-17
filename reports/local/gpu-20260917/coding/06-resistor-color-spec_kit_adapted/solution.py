# resistor_encoder.py

def color_code(color):
    color_map = {
        "black": 0,
        "brown": 1,
        "red": 2,
        "orange": 3,
        "yellow": 4,
        "green": 5,
        "blue": 6,
        "violet": 7,
        "grey": 8,
        "white": 9
    }
    return color_map.get(color.lower(), None)

def colors():
    return list(color_map.keys())

# Example usage:
# print(color_code('red'))  # Output: 2
# print(colors())  # Output: ['black', 'brown', 'red', 'orange', 'yellow', 'green', 'blue', 'violet', 'grey', 'white']
