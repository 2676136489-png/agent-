import { apiGet, apiPost, apiUpload } from './client'
import type { Document, RetrievedChunk } from '../types/knowledge'

export function uploadDocument(file: File): Promise<Document> {
  return apiUpload<Document>('/api/knowledge/documents', file)
}

export function listDocuments(): Promise<Document[]> {
  return apiGet<Document[]>('/api/knowledge/documents')
}

export function searchKnowledge(query: string, topK = 5): Promise<RetrievedChunk[]> {
  return apiPost<RetrievedChunk[]>('/api/knowledge/search', { query, top_k: topK })
}
