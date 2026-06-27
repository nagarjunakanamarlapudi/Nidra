"""Read-only Gmail/IMAP access + draft creation.

Strictly read + draft-only: INBOX is opened read-only (IMAP EXAMINE, never marks
seen), and the only write is saving a ``\\Draft`` into Drafts. It never sends
mail and never deletes or moves messages. The agent only sees read/draft tools.
"""
