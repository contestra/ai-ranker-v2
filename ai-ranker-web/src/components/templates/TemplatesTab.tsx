"use client"

import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { templateApi, Template, systemApi } from '@/lib/api';
import { Plus, Edit2, Trash2, Play, Save, X } from 'lucide-react';

export function TemplatesTab() {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState<Template | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [testResult, setTestResult] = useState<any>(null);
  const [testInput, setTestInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [adapters, setAdapters] = useState<string[]>([]);
  const [models, setModels] = useState<Record<string, string[]>>({});
  const [formData, setFormData] = useState<any>({
    name: '',
    description: '',
    adapter: 'openai',
    model: 'gpt-4',
    query_template: '',
    system_prompt: '',
    temperature: 0.7,
    max_tokens: 1000,
  });

  useEffect(() => {
    loadTemplates();
    loadSystemInfo();
  }, []);

  const loadTemplates = async () => {
    try {
      setLoading(true);
      const data = await templateApi.list();
      // If no templates from backend, add some demo templates
      setTemplates(data);
    } catch (error) {
      console.error('Failed to load templates:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadSystemInfo = async () => {
    try {
      const info = await systemApi.getInfo();
      setAdapters(info.adapters);
      setModels(info.models);
    } catch (error) {
      console.error('Failed to load system info:', error);
    }
  };

  const handleSelectTemplate = (template: Template) => {
    setSelectedTemplate(template);
    setFormData({
      name: template.template_name,
      adapter: template.adapter || 'openai',
      model: template.model || 'gpt-4',
      query_template: template.query_template || '',
      system_prompt: template.system_prompt || '',
      temperature: template.temperature || 0.7,
      max_tokens: template.max_tokens || 1000,
    });
    setIsEditing(false);
    setIsCreating(false);
    setTestResult(null);
    setTestInput('');
  };

  const handleCreateNew = () => {
    setSelectedTemplate(null);
    setIsCreating(true);
    setIsEditing(false);
    setFormData({
      name: '',
      description: '',
      adapter: 'openai',
      model: 'gpt-4',
      query_template: '',
      system_prompt: '',
      temperature: 0.7,
      max_tokens: 1000,
    });
  };

  const handleSave = async () => {
    try {
      setLoading(true);
      if (isCreating) {
        const newTemplate = await templateApi.create(formData);
        setTemplates([...templates, newTemplate]);
        setSelectedTemplate(newTemplate);
        setIsCreating(false);
      } else if (selectedTemplate) {
        const updated = await templateApi.update(selectedTemplate.template_id, formData);
        setTemplates(templates.map(t => t.template_id === updated.template_id ? updated : t));
        setSelectedTemplate(updated);
        setIsEditing(false);
      }
    } catch (error) {
      console.error('Failed to save template:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Templates cannot be deleted once created. Remove from view?')) return;
    try {
      setLoading(true);
      // Just remove from local state since backend doesn't support deletion
      setTemplates(templates.filter(t => t.template_id !== id));
      if (selectedTemplate?.template_id === id) {
        setSelectedTemplate(null);
      }
    } catch (error) {
      console.error('Failed to delete template:', error);
    } finally {
      setLoading(false);
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
    if (isCreating) {
      setIsCreating(false);
      setSelectedTemplate(null);
      setFormData({});
    } else {
      setIsEditing(false);
      if (selectedTemplate) {
        setFormData({
          name: selectedTemplate.template_name,
          adapter: selectedTemplate.adapter || 'openai',
          model: selectedTemplate.model || 'gpt-4',
          query_template: selectedTemplate.query_template || '',
          system_prompt: selectedTemplate.system_prompt || '',
          temperature: selectedTemplate.temperature || 0.7,
          max_tokens: selectedTemplate.max_tokens || 1000,
        });
      }
    }
  };

  return (
    <div className="grid grid-cols-3 gap-6 h-full">
      {/* Templates List */}
      <div className="col-span-1 space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>Templates</CardTitle>
            <CardDescription>Manage your AI prompt templates</CardDescription>
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
                      <p className="text-sm text-muted-foreground">{template.adapter} / {template.model}</p>
                      <p className="text-xs text-muted-foreground mt-1 font-mono truncate" title={template.template_sha256}>
                        SHA: {template.template_sha256?.substring(0, 12)}...
                      </p>
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
                  <div>
                    <CardTitle>{isCreating ? 'New Template' : selectedTemplate?.template_name}</CardTitle>
                    {selectedTemplate && (
                      <div className="mt-2 space-y-1">
                        <p className="text-xs text-muted-foreground font-mono">
                          Template ID: {selectedTemplate.template_id}
                        </p>
                        <p className="text-xs text-muted-foreground font-mono">
                          SHA-256: {selectedTemplate.template_sha256}
                        </p>
                      </div>
                    )}
                  </div>
                  <div className="space-x-2">
                    {!isEditing && !isCreating && (
                      <Button onClick={() => setIsEditing(true)} variant="outline">
                        <Edit2 className="h-4 w-4 mr-2" />
                        Edit
                      </Button>
                    )}
                    {(isEditing || isCreating) && (
                      <>
                        <Button onClick={handleCancel} variant="outline">
                          <X className="h-4 w-4 mr-2" />
                          Cancel
                        </Button>
                        <Button onClick={handleSave}>
                          <Save className="h-4 w-4 mr-2" />
                          Save
                        </Button>
                      </>
                    )}
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="name">Name</Label>
                    <Input
                      id="name"
                      value={formData.name}
                      onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                      disabled={!isEditing && !isCreating}
                    />
                  </div>
                  <div>
                    <Label htmlFor="description">Description</Label>
                    <Input
                      id="description"
                      value={formData.description || ''}
                      onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                      disabled={!isEditing && !isCreating}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="adapter">Adapter</Label>
                    <Select
                      value={formData.adapter}
                      onValueChange={(value) => setFormData({ ...formData, adapter: value })}
                      disabled={!isEditing && !isCreating}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {adapters.map((adapter) => (
                          <SelectItem key={adapter} value={adapter}>
                            {adapter}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label htmlFor="model">Model</Label>
                    <Select
                      value={formData.model}
                      onValueChange={(value) => setFormData({ ...formData, model: value })}
                      disabled={!isEditing && !isCreating}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {(models[formData.adapter || ''] || []).map((model) => (
                          <SelectItem key={model} value={model}>
                            {model}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div>
                  <Label htmlFor="system_prompt">System Prompt</Label>
                  <Textarea
                    id="system_prompt"
                    value={formData.system_prompt || ''}
                    onChange={(e) => setFormData({ ...formData, system_prompt: e.target.value })}
                    disabled={!isEditing && !isCreating}
                    rows={4}
                  />
                </div>

                <div>
                  <Label htmlFor="query_template">Query Template</Label>
                  <Textarea
                    id="query_template"
                    value={formData.query_template}
                    onChange={(e) => setFormData({ ...formData, query_template: e.target.value })}
                    disabled={!isEditing && !isCreating}
                    rows={6}
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
                      disabled={!isEditing && !isCreating}
                    />
                  </div>
                  <div>
                    <Label htmlFor="max_tokens">Max Tokens</Label>
                    <Input
                      id="max_tokens"
                      type="number"
                      value={formData.max_tokens || 1000}
                      onChange={(e) => setFormData({ ...formData, max_tokens: parseInt(e.target.value) })}
                      disabled={!isEditing && !isCreating}
                    />
                  </div>
                </div>

                {selectedTemplate && !isCreating && (
                  <div className="mt-4 p-3 bg-muted rounded-lg">
                    <Label className="text-sm font-medium">Canonical JSON (Immutable)</Label>
                    <pre className="mt-2 text-xs overflow-auto max-h-40">
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
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <Label htmlFor="test-input">Test Input (JSON)</Label>
                    <Textarea
                      id="test-input"
                      value={testInput}
                      onChange={(e) => setTestInput(e.target.value)}
                      rows={4}
                      placeholder='{"key": "value"}'
                    />
                  </div>
                  <Button onClick={handleTest} disabled={loading}>
                    <Play className="h-4 w-4 mr-2" />
                    Run Test
                  </Button>
                  {testResult && (
                    <div className="mt-4 p-4 bg-muted rounded-lg">
                      <Label>Result:</Label>
                      <pre className="mt-2 text-sm overflow-auto">
                        {JSON.stringify(testResult, null, 2)}
                      </pre>
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