/**
 * Centralized error handling utility
 */

export class APIError extends Error {
  constructor(
    message: string,
    public status?: number,
    public code?: string
  ) {
    super(message);
    this.name = 'APIError';
  }
}

export function handleAPIError(error: any): string {
  // Handle network errors
  if (error.code === 'ECONNREFUSED' || error.code === 'ENOTFOUND') {
    return 'Unable to connect to server. Please check if the backend is running.';
  }

  // Handle timeout errors
  if (error.code === 'ETIMEDOUT' || error.code === 'ECONNABORTED') {
    return 'Request timed out. Please try again.';
  }

  // Handle HTTP errors
  if (error.response) {
    const status = error.response.status;
    const data = error.response.data;

    // Check for structured error response
    if (data?.detail) {
      if (typeof data.detail === 'string') {
        return data.detail;
      }
      if (data.detail.detail) {
        return data.detail.detail;
      }
    }

    // Handle specific status codes
    switch (status) {
      case 400:
        return data?.message || 'Invalid request. Please check your input.';
      case 401:
        return 'Unauthorized. Please check your credentials.';
      case 403:
        return 'You do not have permission to perform this action.';
      case 404:
        return data?.message || 'Requested resource not found.';
      case 409:
        return data?.message || 'Conflict with existing resource.';
      case 422:
        return 'Invalid data provided. Please check your input.';
      case 429:
        return 'Too many requests. Please try again later.';
      case 500:
        return 'Server error. Please try again later.';
      case 502:
        return 'Bad gateway. The server is temporarily unavailable.';
      case 503:
        return 'Service unavailable. Please try again later.';
      default:
        return data?.message || `Server error (${status}). Please try again.`;
    }
  }

  // Handle request errors
  if (error.request) {
    return 'No response from server. Please check your connection.';
  }

  // Default error message
  return error.message || 'An unexpected error occurred. Please try again.';
}

export function logError(error: any, context?: string): void {
  const timestamp = new Date().toISOString();
  const errorInfo = {
    timestamp,
    context,
    message: error.message,
    stack: error.stack,
    response: error.response?.data,
    status: error.response?.status,
  };

  console.error('[Error]', errorInfo);

  // In production, you might want to send this to an error tracking service
  if (process.env.NODE_ENV === 'production') {
    // Send to error tracking service
  }
}

export function withErrorHandling<T extends (...args: any[]) => Promise<any>>(
  fn: T,
  context?: string
): T {
  return (async (...args: Parameters<T>) => {
    try {
      return await fn(...args);
    } catch (error) {
      logError(error, context);
      throw new APIError(handleAPIError(error), error.response?.status);
    }
  }) as T;
}