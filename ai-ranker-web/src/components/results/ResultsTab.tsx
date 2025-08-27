"use client"

import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { runApi, templateApi, Run, Template } from '@/lib/api';
import { Download, Trash2, RefreshCw, Search, Filter } from 'lucide-react';
import { format } from 'date-fns';

export function ResultsTab() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedRun, setSelectedRun] = useState<Run | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [runsData, templatesData] = await Promise.all([
        runApi.list(),
        templateApi.list()
      ]);
      setRuns(runsData);
      setTemplates(templatesData);
    } catch (error) {
      console.error('Failed to load data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = () => {
    loadData();
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Are you sure you want to delete this run?')) return;
    
    try {
      await runApi.delete(id);
      setRuns(runs.filter(r => r.id !== id));
      if (selectedRun?.id === id) {
        setSelectedRun(null);
      }
    } catch (error) {
      console.error('Failed to delete run:', error);
    }
  };

  const handleExport = () => {
    const filteredRuns = getFilteredRuns();
    const data = JSON.stringify(filteredRuns, null, 2);
    const blob = new Blob([data], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `runs-export-${new Date().toISOString()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const getFilteredRuns = () => {
    return runs.filter(run => {
      // Template filter
      if (selectedTemplate !== 'all' && run.template_id !== selectedTemplate) {
        return false;
      }
      
      // Status filter
      if (statusFilter !== 'all' && run.status !== statusFilter) {
        return false;
      }
      
      // Search query
      if (searchQuery) {
        const query = searchQuery.toLowerCase();
        const inputStr = JSON.stringify(run.input_data).toLowerCase();
        const outputStr = JSON.stringify(run.output_data).toLowerCase();
        if (!inputStr.includes(query) && !outputStr.includes(query)) {
          return false;
        }
      }
      
      return true;
    });
  };

  const filteredRuns = getFilteredRuns();

  const getTemplateName = (templateId: string) => {
    const template = templates.find(t => t.id === templateId);
    return template?.name || 'Unknown Template';
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed':
        return 'bg-green-100 text-green-800';
      case 'failed':
        return 'bg-red-100 text-red-800';
      case 'running':
        return 'bg-blue-100 text-blue-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  return (
    <div className="grid grid-cols-3 gap-6 h-full">
      {/* Filters and List */}
      <div className="col-span-2 space-y-4">
        <Card>
          <CardHeader>
            <div className="flex justify-between items-center">
              <div>
                <CardTitle>Run History</CardTitle>
                <CardDescription>{filteredRuns.length} runs found</CardDescription>
              </div>
              <div className="flex space-x-2">
                <Button onClick={handleRefresh} variant="outline" size="icon">
                  <RefreshCw className="h-4 w-4" />
                </Button>
                <Button onClick={handleExport} variant="outline">
                  <Download className="h-4 w-4 mr-2" />
                  Export
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {/* Filters */}
            <div className="grid grid-cols-3 gap-4 mb-4">
              <div>
                <Label htmlFor="template-filter">Template</Label>
                <Select value={selectedTemplate} onValueChange={setSelectedTemplate}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Templates</SelectItem>
                    {templates.map(template => (
                      <SelectItem key={template.id} value={template.id}>
                        {template.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label htmlFor="status-filter">Status</Label>
                <Select value={statusFilter} onValueChange={setStatusFilter}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Statuses</SelectItem>
                    <SelectItem value="completed">Completed</SelectItem>
                    <SelectItem value="failed">Failed</SelectItem>
                    <SelectItem value="running">Running</SelectItem>
                    <SelectItem value="pending">Pending</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label htmlFor="search">Search</Label>
                <div className="relative">
                  <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="search"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search in data..."
                    className="pl-8"
                  />
                </div>
              </div>
            </div>

            {/* Results List */}
            <div className="space-y-2 max-h-[600px] overflow-y-auto">
              {filteredRuns.map((run, index) => (
                <div
                  key={`run-${run.id}-${index}`}
                  className={`p-4 border rounded-lg cursor-pointer hover:bg-accent ${
                    selectedRun?.id === run.id ? 'bg-accent' : ''
                  }`}
                  onClick={() => setSelectedRun(run)}
                >
                  <div className="flex justify-between items-start">
                    <div className="flex-1">
                      <div className="flex items-center space-x-2">
                        <p className="font-medium">{getTemplateName(run.template_id)}</p>
                        <span className={`text-xs px-2 py-1 rounded ${getStatusColor(run.status)}`}>
                          {run.status}
                        </span>
                      </div>
                      <p className="text-sm text-muted-foreground mt-1">
                        {format(new Date(run.created_at), 'PPpp')}
                      </p>
                      {run.error && (
                        <p className="text-sm text-destructive mt-1">Error: {run.error}</p>
                      )}
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDelete(run.id);
                      }}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Run Details */}
      <div className="col-span-1">
        {selectedRun ? (
          <Card className="h-full">
            <CardHeader>
              <CardTitle>Run Details</CardTitle>
              <CardDescription>ID: {selectedRun.id}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label>Template</Label>
                <p className="text-sm">{getTemplateName(selectedRun.template_id)}</p>
              </div>
              
              <div>
                <Label>Status</Label>
                <p className={`inline-block text-xs px-2 py-1 rounded ${getStatusColor(selectedRun.status)}`}>
                  {selectedRun.status}
                </p>
              </div>
              
              <div>
                <Label>Created</Label>
                <p className="text-sm">{format(new Date(selectedRun.created_at), 'PPpp')}</p>
              </div>
              
              {selectedRun.completed_at && (
                <div>
                  <Label>Completed</Label>
                  <p className="text-sm">{format(new Date(selectedRun.completed_at), 'PPpp')}</p>
                </div>
              )}
              
              <div>
                <Label>Input Data</Label>
                <pre className="text-xs bg-muted p-2 rounded mt-1 overflow-auto max-h-40">
                  {JSON.stringify(selectedRun.input_data, null, 2)}
                </pre>
              </div>
              
              {selectedRun.output_data && (
                <div>
                  <Label>Output Data</Label>
                  <pre className="text-xs bg-muted p-2 rounded mt-1 overflow-auto max-h-40">
                    {JSON.stringify(selectedRun.output_data, null, 2)}
                  </pre>
                </div>
              )}
              
              {selectedRun.error && (
                <div>
                  <Label>Error</Label>
                  <p className="text-sm text-destructive mt-1">{selectedRun.error}</p>
                </div>
              )}
            </CardContent>
          </Card>
        ) : (
          <Card className="h-full flex items-center justify-center">
            <CardContent>
              <p className="text-muted-foreground">Select a run to view details</p>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}