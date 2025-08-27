"use client"

import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { templateApi, Template, systemApi } from '@/lib/api';
import { Plus, Copy, Trash2, Play, Save, X, Hash, AlertCircle } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';

export function TemplatesTabV2() {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState<Template | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [isCloning, setIsCloning] = useState(false);
  const [testResult, setTestResult] = useState<any>(null);
  const [testInput, setTestInput] = useState('{}');
  const [loading, setLoading] = useState(false);
  const [providerVersions, setProviderVersions] = useState<Record<string, any>>({});
  // Idempotency key is now auto-generated, not user-provided
  const generateIdempotencyKey = () => {
    return `template-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  };
  const [formData, setFormData] = useState<any>({
    name: '',
    description: '',
    adapter: 'openai',
    model: 'gpt-5',
    query_template: '',
    // system_prompt removed - managed by backend for ALS
    temperature: 0.7,
    max_tokens: 6000,
    grounded: false,
    json_mode: false,
  });

  useEffect(() => {
    loadTemplates();
    loadProviderVersions();
  }, []);

  const loadTemplates = async () => {
    try {
      setLoading(true);
      const data = await templateApi.list();
      // Deduplicate templates by template_id to prevent React key errors
      const uniqueTemplates = Array.from(
        new Map(data.map(t => [t.template_id, t])).values()
      );
      setTemplates(uniqueTemplates);
    } catch (error: any) {
      console.error('Failed to load templates:', error);
      // Show user-friendly error message
      if (error.userMessage) {
        alert(error.userMessage);
      }
    } finally {
      setLoading(false);
    }
  };

  const loadProviderVersions = async () => {
    // Hard-code the versions per user requirements
    // We only support gpt-5 and gemini-2.5-pro
    setProviderVersions({
      openai: { versions: ['gpt-5'] },
      vertex: { versions: ['gemini-2.5-pro'] },
      google: { versions: ['gemini-2.5-pro'] }
    });
  };

  const handleSelectTemplate = (template: Template) => {
    setSelectedTemplate(template);
    setIsCreating(false);
    setIsCloning(false);
    setTestResult(null);
    setTestInput('{}');
    
    // Parse canonical JSON to populate form for viewing
    const canonical = template.canonical_json;
    setFormData({
      name: template.template_name,
      adapter: canonical.vendor || canonical.provider || 'openai',
      model: canonical.model || 'gpt-5',
      query_template: canonical.messages?.find((m: any) => m.role === 'user')?.content || '',
      // system_prompt removed - managed by backend for ALS
      temperature: canonical.temperature || 0.7,
      max_tokens: canonical.max_tokens || 6000,
      grounded: canonical.grounded || false,
      json_mode: canonical.json_mode || false,
    });
  };

  const handleCreateNew = () => {
    setSelectedTemplate(null);
    setIsCreating(true);
    setIsCloning(false);
    setFormData({
      name: '',
      description: '',
      adapter: 'openai',
      model: 'gpt-5',
      query_template: '',
      // system_prompt removed - managed by backend for ALS
      temperature: 0.7,
      max_tokens: 6000,
      grounded: false,
      json_mode: false,
    });
    // Idempotency key will be generated when saving
  };

  const handleCloneTemplate = () => {
    if (!selectedTemplate) return;
    setIsCloning(true);
    setIsCreating(true);
    setFormData({
      ...formData,
      name: formData.name + ' (Copy)',
    });
    // Idempotency key will be generated when saving
  };

  const handleSave = async () => {
    try {
      setLoading(true);
      // Auto-generate idempotency key for this save operation
      const idempotencyKey = generateIdempotencyKey();
      const newTemplate = await templateApi.create(formData, idempotencyKey);
      
      // Check if it's a duplicate (200 status means existing template returned)
      if (newTemplate.is_new === false) {
        alert('Template with identical configuration already exists. SHA-256: ' + newTemplate.template_sha256);
        // Don't add duplicate template to the list, just select it
        setSelectedTemplate(newTemplate);
      } else {
        // Only add truly new templates to the list, avoiding duplicates
        const updatedTemplates = [...templates.filter(t => t.template_id !== newTemplate.template_id), newTemplate];
        setTemplates(updatedTemplates);
        setSelectedTemplate(newTemplate);
      }
      setIsCreating(false);
      setIsCloning(false);
    } catch (error: any) {
      if (error.response?.status === 409) {
        alert('Idempotency conflict: A different template was already created with this idempotency key');
      } else {
        console.error('Failed to save template:', error);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Templates are immutable and cannot be deleted from the database. Remove from view?')) return;
    setTemplates(templates.filter(t => t.template_id !== id));
    if (selectedTemplate?.template_id === id) {
      setSelectedTemplate(null);
    }
  };

  const handleTest = async () => {
    if (!selectedTemplate || !testInput) return;
    try {
      setLoading(true);
      const result = await templateApi.test(selectedTemplate.template_id, { input: testInput });
      setTestResult(result);
    } catch (error) {
      console.error('Failed to test template:', error);
      setTestResult({ error: 'Test failed' });
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = () => {
    setIsCreating(false);
    setIsCloning(false);
    if (selectedTemplate) {
      handleSelectTemplate(selectedTemplate);
    }
  };

  const getAvailableModels = () => {
    // Per user requirements: we only support gpt-5 and gemini-2.5-pro
    const provider = formData.adapter;
    if (provider === 'openai') {
      return ['gpt-5'];
    } else if (provider === 'vertex' || provider === 'google') {
      return ['gemini-2.5-pro'];
    }
    return [];
  };

  return (
    <div className="grid grid-cols-3 gap-6 h-full">
      {/* Templates List */}
      <div className="col-span-1 space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>Templates (Immutable)</CardTitle>
            <CardDescription>Templates cannot be edited once created</CardDescription>
          </CardHeader>
          <CardContent>
            <Button onClick={handleCreateNew} className="w-full mb-4">
              <Plus className="h-4 w-4 mr-2" />
              New Template
            </Button>
            <div className="space-y-2">
              {templates.map((template) => (
                <div
                  key={template.template_id}
                  className={`p-3 border rounded-lg cursor-pointer hover:bg-accent ${
                    selectedTemplate?.template_id === template.template_id ? 'bg-accent' : ''
                  }`}
                  onClick={() => handleSelectTemplate(template)}
                >
                  <div className="flex justify-between items-start">
                    <div className="flex-1">
                      <p className="font-medium">{template.template_name}</p>
                      <div className="flex gap-2 mt-1">
                        <Badge variant="secondary" className="text-xs">
                          {template.adapter || 'openai'}
                        </Badge>
                        <Badge variant="outline" className="text-xs">
                          {template.model || 'unknown'}
                        </Badge>
                      </div>
                      <div className="flex items-center gap-1 mt-2">
                        <Hash className="h-3 w-3 text-muted-foreground" />
                        <p className="text-xs text-muted-foreground font-mono truncate" title={template.template_sha256}>
                          {template.template_sha256?.substring(0, 16)}...
                        </p>
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDelete(template.template_id);
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

      {/* Template Details */}
      <div className="col-span-2 space-y-4">
        {(selectedTemplate || isCreating) && (
          <>
            <Card>
              <CardHeader>
                <div className="flex justify-between items-center">
                  <div className="flex-1">
                    <CardTitle>
                      {isCreating ? (isCloning ? 'Clone Template' : 'New Template') : selectedTemplate?.template_name}
                    </CardTitle>
                    {selectedTemplate && !isCreating && (
                      <div className="mt-2 space-y-1">
                        <div className="flex items-center gap-2">
                          <Hash className="h-4 w-4 text-muted-foreground" />
                          <p className="text-xs text-muted-foreground font-mono">
                            Template SHA-256: {selectedTemplate.template_sha256}
                          </p>
                        </div>
                        <p className="text-xs text-muted-foreground">
                          ID: {selectedTemplate.template_id}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          Created: {new Date(selectedTemplate.created_at).toLocaleString()}
                        </p>
                      </div>
                    )}
                  </div>
                  <div className="space-x-2">
                    {!isCreating && selectedTemplate && (
                      <Button onClick={handleCloneTemplate} variant="outline">
                        <Copy className="h-4 w-4 mr-2" />
                        Clone
                      </Button>
                    )}
                    {isCreating && (
                      <>
                        <Button onClick={handleCancel} variant="outline">
                          <X className="h-4 w-4 mr-2" />
                          Cancel
                        </Button>
                        <Button onClick={handleSave} disabled={loading}>
                          <Save className="h-4 w-4 mr-2" />
                          Create
                        </Button>
                      </>
                    )}
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                {isCreating && (
                  <Alert>
                    <AlertCircle className="h-4 w-4" />
                    <AlertDescription>
                      Templates are immutable. Once created, they cannot be edited. The same configuration will always produce the same SHA-256 hash.
                    </AlertDescription>
                  </Alert>
                )}

                {/* Idempotency key is now auto-generated internally, not exposed to user */}

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="name">Template Name</Label>
                    <Input
                      id="name"
                      value={formData.name}
                      onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                      disabled={!isCreating}
                      required
                    />
                  </div>
                  <div>
                    <Label htmlFor="description">Description</Label>
                    <Input
                      id="description"
                      value={formData.description || ''}
                      onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                      disabled={!isCreating}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="adapter">Provider</Label>
                    <Select
                      value={formData.adapter}
                      onValueChange={(value) => setFormData({ ...formData, adapter: value })}
                      disabled={!isCreating}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="openai">OpenAI</SelectItem>
                        <SelectItem value="vertex">Vertex AI (Gemini)</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label htmlFor="model">Model</Label>
                    <Select
                      value={formData.model}
                      onValueChange={(value) => setFormData({ ...formData, model: value })}
                      disabled={!isCreating}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {getAvailableModels().map((model: string) => (
                          <SelectItem key={model} value={model}>
                            {model}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="flex items-center space-x-2">
                    <Switch
                      id="grounded"
                      checked={formData.grounded}
                      onCheckedChange={(checked) => setFormData({ ...formData, grounded: checked })}
                      disabled={!isCreating}
                    />
                    <Label htmlFor="grounded">Grounding Mode</Label>
                  </div>
                  <div className="flex items-center space-x-2">
                    <Switch
                      id="json_mode"
                      checked={formData.json_mode}
                      onCheckedChange={(checked) => setFormData({ ...formData, json_mode: checked })}
                      disabled={!isCreating}
                    />
                    <Label htmlFor="json_mode">Strict JSON Output</Label>
                  </div>
                </div>

                {/* System prompt is managed by backend for ALS integrity - NOT user configurable */}

                <div>
                  <Label htmlFor="query_template">Query Template</Label>
                  <Textarea
                    id="query_template"
                    value={formData.query_template}
                    onChange={(e) => setFormData({ ...formData, query_template: e.target.value })}
                    disabled={!isCreating}
                    rows={6}
                    placeholder="Use {{variable}} for template variables"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="temperature">Temperature</Label>
                    <Input
                      id="temperature"
                      type="number"
                      step="0.1"
                      min="0"
                      max="2"
                      value={formData.temperature || 0.7}
                      onChange={(e) => setFormData({ ...formData, temperature: parseFloat(e.target.value) })}
                      disabled={!isCreating}
                    />
                  </div>
                  <div>
                    <Label htmlFor="max_tokens">Max Tokens</Label>
                    <Input
                      id="max_tokens"
                      type="number"
                      value={formData.max_tokens || 6000}
                      onChange={(e) => setFormData({ ...formData, max_tokens: parseInt(e.target.value) })}
                      disabled={!isCreating}
                    />
                  </div>
                </div>

                {selectedTemplate && !isCreating && (
                  <div className="mt-4 p-4 bg-muted rounded-lg">
                    <Label className="text-sm font-medium">Canonical JSON (Immutable Configuration)</Label>
                    <pre className="mt-2 text-xs overflow-auto max-h-60 font-mono">
                      {JSON.stringify(selectedTemplate.canonical_json, null, 2)}
                    </pre>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Test Template */}
            {selectedTemplate && !isCreating && (
              <Card>
                <CardHeader>
                  <CardTitle>Test Template</CardTitle>
                  <CardDescription>Execute a single run to test the template</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <Label htmlFor="test-input">Input Variables (JSON)</Label>
                    <Textarea
                      id="test-input"
                      value={testInput}
                      onChange={(e) => setTestInput(e.target.value)}
                      rows={4}
                      placeholder='{"variable": "value"}'
                    />
                  </div>
                  <Button onClick={handleTest} disabled={loading}>
                    <Play className="h-4 w-4 mr-2" />
                    Run Test
                  </Button>
                  {testResult && (
                    <div className="mt-4 space-y-2">
                      {testResult.run_id && (
                        <div className="p-3 bg-muted rounded-lg">
                          <div className="space-y-2">
                            <div className="flex items-center gap-2">
                              <Hash className="h-4 w-4 text-muted-foreground" />
                              <p className="text-xs font-mono">Run SHA-256: {testResult.run_sha256}</p>
                            </div>
                            <div className="flex items-center gap-2">
                              <Hash className="h-4 w-4 text-muted-foreground" />
                              <p className="text-xs font-mono">Output SHA-256: {testResult.response_output_sha256}</p>
                            </div>
                            <div className="flex gap-2 mt-2">
                              <Badge variant={testResult.grounded_effective ? "default" : "secondary"}>
                                Grounded: {testResult.grounded_effective ? 'Yes' : 'No'}
                              </Badge>
                              {testResult.output_json_valid !== undefined && (
                                <Badge variant={testResult.output_json_valid ? "default" : "destructive"}>
                                  JSON Valid: {testResult.output_json_valid ? 'Yes' : 'No'}
                                </Badge>
                              )}
                            </div>
                            <p className="text-xs text-muted-foreground mt-2">
                              Model Version: {testResult.model_version_effective}
                            </p>
                            {testResult.model_fingerprint && (
                              <p className="text-xs text-muted-foreground">
                                Fingerprint: {testResult.model_fingerprint}
                              </p>
                            )}
                          </div>
                        </div>
                      )}
                      <div className="p-4 bg-muted rounded-lg">
                        <Label>Output:</Label>
                        <pre className="mt-2 text-sm overflow-auto">
                          {testResult.output || JSON.stringify(testResult, null, 2)}
                        </pre>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}
          </>
        )}
      </div>
    </div>
  );
}