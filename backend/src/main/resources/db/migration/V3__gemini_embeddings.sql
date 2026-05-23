-- Switch embedding dimension from OpenAI (1536) to Gemini (768)
-- We cannot cleanly cast existing 1536-dim vectors to 768-dim, so we set them to NULL.
-- Since this is an active prototype, recalculation of old vectors is not implemented.

ALTER TABLE claims ALTER COLUMN embedding TYPE VECTOR(768) USING NULL;
