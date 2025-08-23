import axios from 'axios'
import { Brand, Experiment, Metric, DashboardData, TrendData } from '@/types'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api'

const api = axios.create({
  baseURL: API_BASE,
})

export const brandsApi = {
  list: () => api.get<Brand[]>('/entities/brands').then(res => res.data),
  get: (id: number) => api.get<Brand>(`/entities/brands/${id}`).then(res => res.data),
  create: (brand: Omit<Brand, 'id'>) => api.post<Brand>('/entities/brands', brand).then(res => res.data),
}

export const experimentsApi = {
  list: () => api.get<Experiment[]>('/experiments').then(res => res.data),
  get: (id: number) => api.get<Experiment>(`/experiments/${id}`).then(res => res.data),
  create: (experiment: { title: string; description?: string }) => 
    api.post<Experiment>('/experiments', experiment).then(res => res.data),
  run: (data: any) => api.post('/experiments/run', data).then(res => res.data),
}

export const metricsApi = {
  getByRun: (runId: number) => api.get<Metric[]>(`/metrics/run/${runId}`).then(res => res.data),
  getByBrand: (brandId: number) => api.get<Metric[]>(`/metrics/brand/${brandId}`).then(res => res.data),
  calculate: (runId: number, brandId: number, conceptId?: number) => 
    api.post<Metric>('/metrics/calculate', { run_id: runId, brand_id: brandId, concept_id: conceptId }).then(res => res.data),
}

export const dashboardApi = {
  getOverview: (brandId: number) => api.get<DashboardData>(`/dashboard/overview/${brandId}`).then(res => res.data),
  getTrends: (brandId: number, days: number = 30) => 
    api.get<TrendData[]>(`/dashboard/trends/${brandId}?days=${days}`).then(res => res.data),
  getCompetitors: (brandId: number) => api.get(`/dashboard/competitors/${brandId}`).then(res => res.data),
  getGroundedGap: (brandId: number) => api.get(`/dashboard/grounded-gap/${brandId}`).then(res => res.data),
  getTopEntities: (brandId: number) => api.get(`/dashboard/top-entities/${brandId}`).then(res => res.data),
  getTopBrands: (brandId: number) => api.get(`/dashboard/top-brands/${brandId}`).then(res => res.data),
  getWeeklyTrends: (brandId: number, phraseId: number) => 
    api.get(`/dashboard/weekly-trends/${brandId}/${phraseId}`).then(res => res.data),
}

export const trackedPhrasesApi = {
  list: (brandId: number) => api.get(`/brands/${brandId}/tracked-phrases`).then(res => res.data),
  create: (brandId: number, phrase: any) => 
    api.post(`/brands/${brandId}/tracked-phrases`, phrase).then(res => res.data),
  bulkCreate: (brandId: number, phrases: string[]) => 
    api.post(`/brands/${brandId}/tracked-phrases/bulk`, { phrases }).then(res => res.data),
  delete: (phraseId: number) => api.delete(`/tracked-phrases/${phraseId}`).then(res => res.data),
  toggle: (phraseId: number) => api.put(`/tracked-phrases/${phraseId}/toggle`).then(res => res.data),
  getRankings: (brandId: number, vendor: string) => 
    api.get(`/brands/${brandId}/phrase-rankings/${vendor}`).then(res => res.data),
  runAnalysis: (brandId: number, vendor: string) => 
    api.post(`/brands/${brandId}/run-phrase-analysis?vendor=${vendor}`).then(res => res.data),
}

export const promptsApi = {
  getTemplates: () => api.get('/prompts/templates').then(res => res.data),
  generate: (brand: string, categories: string[]) => 
    api.post('/prompts/generate', { brand, categories }).then(res => res.data),
}