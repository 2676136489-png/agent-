/** 与后端 app/rag/schemas.py 对应。 */

export interface Document {
  id: string
  source_id: string
  filename: string
  mime_type: string
  size_bytes: number
  page_count: number | null
  chunk_count: number
  status: string
  error: string | null
  embedding_model: string | null
  created_at: string
}

export interface DocumentChunk {
  id: string
  document_id: string
  chunk_index: number
  content: string
  page: number | null
  char_start: number | null
  char_end: number | null
  token_estimate: number
  created_at: string
}

export interface RetrievedChunk {
  chunk_id: string
  document_id: string
  filename: string
  content: string
  score: number
  page: number | null
  char_start: number | null
  char_end: number | null
  chunk_index: number
}

export interface Citation {
  chunk_id: string
  document_id: string
  filename: string
  page: number | null
  quote: string
  score: number | null
}
