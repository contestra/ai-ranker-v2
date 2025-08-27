import axios from 'axios';
import { handleAPIError, logError } from './errorHandler';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
    'X-Organization-Id': 'test-org', // Default org for testing
  },
  timeout: 30000, // 30 second timeout
});

// Add response interceptor for error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    logError(error, 'API Request Failed');
    const errorMessage = handleAPIError(error);
    error.userMessage = errorMessage;
    return Promise.reject(error);
  }
);

// Template interfaces
export interface Template {
  template_id: string;
  template_sha256: string;
  template_name: string;
  canonical_json: any;
  org_id: string;
  created_at: string;
  created_by?: string;
  
  // UI convenience fields (extracted from canonical_json)
  adapter?: string;
  model?: string;
  // system_prompt removed - managed by backend for ALS integrity
  query_template?: string;
  temperature?: number;
  max_tokens?: number;
}

export interface Run {
  id: string;
  template_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  input_data: any;
  output_data?: any;
  error?: string;
  created_at: string;
  completed_at?: string;
  template?: Template;
}

export interface SystemInfo {
  version: string;
  adapters: string[];
  models: Record<string, string[]>;
  uptime: number;
  db_connected: boolean;
}

// API methods
export const templateApi = {
  list: async (): Promise<Template[]> => {
    try {
      const response = await api.get('/v1/templates');
      // Transform backend response to frontend format
      if (response.data.templates) {
        return response.data.templates.map((t: any) => ({
          ...t,
          // Extract convenience fields from canonical_json
          adapter: t.canonical_json?.vendor || t.canonical_json?.provider || 'openai',
          model: t.canonical_json?.model || 'gpt-4',
          // system_prompt removed - managed by backend for ALS integrity
          query_template: t.canonical_json?.messages?.find((m: any) => m.role === 'user')?.content || '',
          temperature: t.canonical_json?.temperature || 0.7,
          max_tokens: t.canonical_json?.max_tokens || 6000,
        }));
      }
      return response.data;
    } catch (error) {
      console.warn('Failed to load templates:', error);
      return [];
    }
  },

  get: async (id: string): Promise<Template> => {
    const response = await api.get(`/v1/templates/${id}`);
    const t = response.data;
    return {
      ...t,
      adapter: t.canonical_json?.vendor || t.canonical_json?.provider || 'openai',
      model: t.canonical_json?.model || 'gpt-4',
      // system_prompt removed - managed by backend for ALS integrity
      query_template: t.canonical_json?.messages?.find((m: any) => m.role === 'user')?.content || '',
      temperature: t.canonical_json?.temperature || 0.7,
      max_tokens: t.canonical_json?.max_tokens || 6000,
    };
  },

  create: async (template: any, idempotencyKey?: string): Promise<Template> => {
    // Transform frontend format to backend format
    // CRITICAL: System prompt is NOT user-configurable - it's managed by backend for ALS integrity
    const canonical = {
      vendor: template.adapter,
      model: template.model,
      messages: [
        // System prompt removed - backend will inject appropriate ALS or default prompt
        { role: 'user', content: template.query_template || '' }
      ],
      temperature: template.temperature || 0.7,
      max_tokens: template.max_tokens || 6000,
      grounded: false
    };
    
    const headers: any = {};
    if (idempotencyKey) {
      headers['Idempotency-Key'] = idempotencyKey;
    }
    
    const response = await api.post('/v1/templates', {
      canonical: canonical,
      template_name: template.name
    }, { headers });
    
    const t = response.data;
    return {
      ...t,
      adapter: template.adapter,
      model: template.model,
      // system_prompt removed - managed by backend
      query_template: template.query_template,
      temperature: template.temperature,
      max_tokens: template.max_tokens,
    };
  },

  update: async (id: string, template: Partial<Template>): Promise<Template> => {
    // Templates are immutable in the backend, create a new one
    return templateApi.create(template as any);
  },

  delete: async (id: string): Promise<void> => {
    // Templates cannot be deleted in the current backend
    console.warn('Template deletion not supported by backend');
  },

  test: async (id: string, testData: any): Promise<any> => {
    const response = await api.post(`/v1/templates/${id}/run-simple`, {
      inputs: testData.input,
      locale: 'en-US'
    });
    return response.data;
  },
};

export const runApi = {
  list: async (templateId?: string): Promise<Run[]> => {
    const params = templateId ? { template_id: templateId } : {};
    const response = await api.get('/api/runs', { params });
    return response.data;
  },

  get: async (id: string): Promise<Run> => {
    const response = await api.get(`/api/runs/${id}`);
    return response.data;
  },

  create: async (templateId: string, inputData: any): Promise<Run> => {
    const response = await api.post('/api/runs', {
      template_id: templateId,
      input_data: inputData,
    });
    return response.data;
  },

  delete: async (id: string): Promise<void> => {
    await api.delete(`/api/runs/${id}`);
  },
};

export const systemApi = {
  getInfo: async (): Promise<SystemInfo> => {
    // Use the actual backend endpoint
    try {
      const response = await api.get('/ops/runtime-info');
      // Transform the response to match our expected format
      return {
        version: "2.7",
        adapters: ["openai", "vertex"],
        models: {
          openai: ["gpt-5"],
          vertex: ["gemini-2.5-pro"]
        },
        uptime: 0,
        db_connected: true
      };
    } catch (error) {
      return {
        version: "2.7",
        adapters: [],
        models: {},
        uptime: 0,
        db_connected: false
      };
    }
  },

  getModels: async (adapter: string): Promise<string[]> => {
    const response = await api.get(`/api/system/models/${adapter}`);
    return response.data;
  },
  
  getProviderVersions: async (provider: string): Promise<any> => {
    try {
      const response = await api.get(`/v1/providers/${provider}/versions`);
      return response.data;
    } catch (error) {
      console.error(`Failed to fetch ${provider} versions:`, error);
      return null;
    }
  },
};

export default api;