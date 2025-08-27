"use client"

import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { templateApi, runApi, Template, Run } from '@/lib/api';
import { Play, Upload, Download } from 'lucide-react';

export function RunTab() {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState<string>('');
  const [inputType, setInputType] = useState<'manual' | 'file'>('manual');
  const [inputData, setInputData] = useState('');
  const [batchMode, setBatchMode] = useState(false);
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState<any[]>([]);
  const [error, setError] = useState<string>('');

  useEffect(() => {
    loadTemplates();
  }, []);

  const loadTemplates = async () => {
    try {
      const data = await templateApi.list();
      setTemplates(data);
    } catch (error) {
      console.error('Failed to load templates:', error);
      setError('Failed to load templates');
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    try {
      const text = await file.text();
      setInputData(text);
      
      // Auto-detect batch mode if file contains JSON array or JSONL
      try {
        const parsed = JSON.parse(text);
        if (Array.isArray(parsed)) {
          setBatchMode(true);
        }
      } catch {
        // Check if it's JSONL (one JSON object per line)
        const lines = text.split('\n').filter(line => line.trim());
        if (lines.length > 1) {
          try {
            lines.forEach(line => JSON.parse(line));
            setBatchMode(true);
          } catch {
            // Not JSONL
          }
        }
      }
    } catch (error) {
      setError('Failed to read file');
    }
  };

  const parseInputData = (): any[] => {
    if (!inputData.trim()) return [];

    try {
      // Try parsing as JSON array
      const parsed = JSON.parse(inputData);
      if (Array.isArray(parsed)) {
        return parsed;
      }
      // Single JSON object
      return [parsed];
    } catch {
      // Try parsing as JSONL
      const lines = inputData.split('\n').filter(line => line.trim());
      const items: any[] = [];
      
      for (const line of lines) {
        try {
          items.push(JSON.parse(line));
        } catch {
          // Skip invalid lines
        }
      }
      
      if (items.length > 0) {
        return items;
      }
      
      // Treat as raw text
      return [{ input: inputData }];
    }
  };

  const handleRun = async () => {
    if (!selectedTemplate || !inputData.trim()) {
      setError('Please select a template and provide input data');
      return;
    }

    setRunning(true);
    setError('');
    setResults([]);

    try {
      const items = parseInputData();
      
      if (items.length === 0) {
        setError('No valid input data found');
        setRunning(false);
        return;
      }

      const runResults = [];
      
      for (const item of items) {
        try {
          const run = await runApi.create(selectedTemplate, item);
          
          // Poll for completion
          let completedRun = run;
          let attempts = 0;
          const maxAttempts = 60; // 1 minute timeout
          
          while (completedRun.status === 'pending' || completedRun.status === 'running') {
            if (attempts >= maxAttempts) {
              throw new Error('Run timeout');
            }
            
            await new Promise(resolve => setTimeout(resolve, 1000));
            completedRun = await runApi.get(run.id);
            attempts++;
          }
          
          runResults.push(completedRun);
        } catch (error) {
          console.error('Run failed:', error);
          runResults.push({
            input: item,
            error: 'Run failed',
            status: 'failed'
          });
        }
      }
      
      setResults(runResults);
    } catch (error) {
      console.error('Failed to run:', error);
      setError('Failed to execute run');
    } finally {
      setRunning(false);
    }
  };

  const handleDownloadResults = () => {
    const data = JSON.stringify(results, null, 2);
    const blob = new Blob([data], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `results-${new Date().toISOString()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const selectedTemplateObj = templates.find(t => t.id === selectedTemplate);

  return (
    <div className="space-y-6">
      {/* Configuration */}
      <Card>
        <CardHeader>
          <CardTitle>Run Configuration</CardTitle>
          <CardDescription>Configure and execute template runs</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label htmlFor="template">Select Template</Label>
            <Select value={selectedTemplate} onValueChange={setSelectedTemplate}>
              <SelectTrigger>
                <SelectValue placeholder="Choose a template" />
              </SelectTrigger>
              <SelectContent>
                {templates.map((template) => (
                  <SelectItem key={template.template_id} value={template.template_id}>
                    {template.template_name} ({template.adapter || 'openai'}/{template.model || 'gpt-5'})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {selectedTemplateObj && (
            <div className="p-4 bg-muted rounded-lg">
              <p className="text-sm font-medium">{selectedTemplateObj.name}</p>
              <p className="text-sm text-muted-foreground">{selectedTemplateObj.description}</p>
              <p className="text-xs mt-2">Model: {selectedTemplateObj.adapter}/{selectedTemplateObj.model}</p>
            </div>
          )}

          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2">
              <Checkbox
                id="batch"
                checked={batchMode}
                onCheckedChange={(checked) => setBatchMode(checked as boolean)}
              />
              <Label htmlFor="batch">Batch Mode</Label>
            </div>
            <div className="flex items-center space-x-2">
              <Label>Input Type:</Label>
              <Select value={inputType} onValueChange={(value: 'manual' | 'file') => setInputType(value)}>
                <SelectTrigger className="w-32">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="manual">Manual</SelectItem>
                  <SelectItem value="file">File</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Input Data */}
      <Card>
        <CardHeader>
          <CardTitle>Input Data</CardTitle>
          <CardDescription>
            {batchMode 
              ? 'Provide JSON array or JSONL (one JSON object per line)'
              : 'Provide JSON object or raw text'}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {inputType === 'file' ? (
            <div>
              <Input
                type="file"
                accept=".json,.jsonl,.txt"
                onChange={handleFileUpload}
              />
              {inputData && (
                <div className="mt-4">
                  <Label>File Content Preview:</Label>
                  <Textarea
                    value={inputData.slice(0, 500) + (inputData.length > 500 ? '...' : '')}
                    readOnly
                    rows={5}
                    className="mt-2"
                  />
                </div>
              )}
            </div>
          ) : (
            <div>
              <Textarea
                value={inputData}
                onChange={(e) => setInputData(e.target.value)}
                rows={10}
                placeholder={batchMode 
                  ? '[{"key": "value1"}, {"key": "value2"}]' 
                  : '{"key": "value"}'}
              />
            </div>
          )}

          {error && (
            <div className="p-3 bg-destructive/10 text-destructive rounded-lg">
              {error}
            </div>
          )}

          <div className="flex space-x-2">
            <Button 
              onClick={handleRun} 
              disabled={running || !selectedTemplate || !inputData.trim()}
            >
              <Play className="h-4 w-4 mr-2" />
              {running ? 'Running...' : 'Run'}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Results */}
      {results.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex justify-between items-center">
              <div>
                <CardTitle>Results</CardTitle>
                <CardDescription>{results.length} run(s) completed</CardDescription>
              </div>
              <Button onClick={handleDownloadResults} variant="outline">
                <Download className="h-4 w-4 mr-2" />
                Download Results
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {results.map((result, index) => (
                <div key={`result-${index}-${result.run_id || index}`} className="p-4 border rounded-lg">
                  <div className="flex justify-between items-start mb-2">
                    <span className="text-sm font-medium">Run #{index + 1}</span>
                    <span className={`text-xs px-2 py-1 rounded ${
                      result.status === 'completed' ? 'bg-green-100 text-green-800' :
                      result.status === 'failed' ? 'bg-red-100 text-red-800' :
                      'bg-yellow-100 text-yellow-800'
                    }`}>
                      {result.status}
                    </span>
                  </div>
                  {result.output_data && (
                    <pre className="text-sm bg-muted p-2 rounded overflow-auto">
                      {JSON.stringify(result.output_data, null, 2)}
                    </pre>
                  )}
                  {result.error && (
                    <div className="text-sm text-destructive">
                      Error: {result.error}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}