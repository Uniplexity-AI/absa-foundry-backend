CREATE TABLE IF NOT EXISTS public.faq_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename VARCHAR(255) NOT NULL,
    mime_type VARCHAR(100),
    file_data BYTEA,
    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    uploaded_by VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS public.faq_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES public.faq_documents(id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    text_content TEXT NOT NULL,
    embedding FLOAT8[]
);
