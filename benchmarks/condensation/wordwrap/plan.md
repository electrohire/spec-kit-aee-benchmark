# Plan: greedy word wrapper

1. `width < 1` -> ValueError (C02). `words = text.split()` collapses all
   whitespace runs (C04). Empty -> `[]` (C07).
2. Greedy pack (C01): track `current` words and their joined length; a word
   joins the line iff `len + 1 + len(word) <= width`, else flush the line.
3. Long words (C03): while `len(word) > width`: flush any partial line
   first, then emit `word[:width]` as its own line and chop. Pieces are
   content pieces; the width applies to content only.
4. Every emitted line is `indent + " ".join(words)` (C06); `" ".join` never
   leaves trailing spaces (C05).
