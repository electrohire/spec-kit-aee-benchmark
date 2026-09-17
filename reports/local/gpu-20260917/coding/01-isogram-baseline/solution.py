def is_isogram(phrase):
    # Remove spaces and hyphens from the phrase
    cleaned_phrase = phrase.replace(" ", "").replace("-", "").lower()
    
    # Create a set to store unique characters
    seen_letters = set()
    
    # Iterate over each character in the cleaned phrase
    for char in cleaned_phrase:
        # If the character is already in the set, it's not an isogram
        if char in seen_letters:
            return False
        # Add the character to the set
        seen_letters.add(char)
    
    # If no characters repeat, it's an isogram
    return True
