import string

def is_pangram(sentence):
    alphabet = set(string.ascii_lowercase)
    sentence = sentence.lower()
    sentence_set = set(sentence)
    return alphabet.issubset(sentence_set)
