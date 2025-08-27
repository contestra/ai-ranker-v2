"use client"

import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { systemApi, SystemInfo } from '@/lib/api';
import { RefreshCw, CheckCircle, XCircle, Server, Database, Cpu } from 'lucide-react';
import { handleAPIError, logError } from '@/lib/errorHandler';

export function SystemStatusTab() {
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');

  useEffect(() => {
    loadSystemInfo();
    // Refresh every 30 seconds
    const interval = setInterval(loadSystemInfo, 30000);
    return () => clearInterval(interval);
  }, []);

  const loadSystemInfo = async () => {
    setLoading(true);
    setError('');
    try {
      const info = await systemApi.getInfo();
      setSystemInfo(info);
    } catch (error: any) {
      logError(error, 'Failed to load system info');
      const errorMessage = handleAPIError(error);
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const formatUptime = (seconds: number) => {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    
    if (days > 0) {
      return `${days}d ${hours}h ${minutes}m`;
    } else if (hours > 0) {
      return `${hours}h ${minutes}m`;
    } else {
      return `${minutes}m`;
    }
  };

  return (
    <div className="space-y-6">
      {/* System Overview */}
      <Card>
        <CardHeader>
          <div className="flex justify-between items-center">
            <div>
              <CardTitle>System Overview</CardTitle>
              <CardDescription>AI Ranker V2 System Status</CardDescription>
            </div>
            <Button onClick={loadSystemInfo} variant="outline" size="icon" disabled={loading}>
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {error && (
            <div className="p-3 bg-destructive/10 text-destructive rounded-lg mb-4">
              {error}
            </div>
          )}
          
          {systemInfo && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="space-y-2">
                <div className="flex items-center space-x-2">
                  <Server className="h-4 w-4 text-muted-foreground" />
                  <p className="text-sm font-medium">API Server</p>
                </div>
                <div className="flex items-center space-x-2">
                  <CheckCircle className="h-4 w-4 text-green-500" />
                  <p className="text-sm">Online</p>
                </div>
              </div>

              <div className="space-y-2">
                <div className="flex items-center space-x-2">
                  <Database className="h-4 w-4 text-muted-foreground" />
                  <p className="text-sm font-medium">Database</p>
                </div>
                <div className="flex items-center space-x-2">
                  {systemInfo.db_connected ? (
                    <>
                      <CheckCircle className="h-4 w-4 text-green-500" />
                      <p className="text-sm">Connected</p>
                    </>
                  ) : (
                    <>
                      <XCircle className="h-4 w-4 text-red-500" />
                      <p className="text-sm">Disconnected</p>
                    </>
                  )}
                </div>
              </div>

              <div className="space-y-2">
                <div className="flex items-center space-x-2">
                  <Cpu className="h-4 w-4 text-muted-foreground" />
                  <p className="text-sm font-medium">Version</p>
                </div>
                <p className="text-sm">{systemInfo.version}</p>
              </div>

              <div className="space-y-2">
                <p className="text-sm font-medium">Uptime</p>
                <p className="text-sm">{formatUptime(systemInfo.uptime)}</p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Available Adapters */}
      <Card>
        <CardHeader>
          <CardTitle>Available Adapters</CardTitle>
          <CardDescription>AI providers and models configured in the system</CardDescription>
        </CardHeader>
        <CardContent>
          {systemInfo && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {systemInfo.adapters.map(adapter => (
                <Card key={adapter}>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base capitalize">{adapter}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-1">
                      {(systemInfo.models[adapter] || []).map(model => (
                        <div key={model} className="flex items-center space-x-2">
                          <div className="w-2 h-2 bg-green-500 rounded-full" />
                          <p className="text-sm">{model}</p>
                        </div>
                      ))}
                      {(!systemInfo.models[adapter] || systemInfo.models[adapter].length === 0) && (
                        <p className="text-sm text-muted-foreground">No models configured</p>
                      )}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* System Configuration */}
      <Card>
        <CardHeader>
          <CardTitle>Configuration Details</CardTitle>
          <CardDescription>Current system configuration and environment</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-sm font-medium mb-1">API Base URL</p>
                <p className="text-sm text-muted-foreground">
                  {process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'}
                </p>
              </div>
              <div>
                <p className="text-sm font-medium mb-1">Environment</p>
                <p className="text-sm text-muted-foreground">
                  {process.env.NODE_ENV || 'development'}
                </p>
              </div>
            </div>

            {systemInfo && (
              <>
                <div>
                  <p className="text-sm font-medium mb-2">Supported Adapters</p>
                  <div className="flex flex-wrap gap-2">
                    {systemInfo.adapters.map(adapter => (
                      <span key={adapter} className="px-2 py-1 bg-secondary text-secondary-foreground rounded-md text-xs">
                        {adapter}
                      </span>
                    ))}
                  </div>
                </div>

                <div>
                  <p className="text-sm font-medium mb-2">Total Models Available</p>
                  <p className="text-2xl font-bold">
                    {Object.values(systemInfo.models).flat().length}
                  </p>
                </div>
              </>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}