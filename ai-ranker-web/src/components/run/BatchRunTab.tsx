"use client"

import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { templateApi, Template, systemApi } from '@/lib/api';
import { handleAPIError, logError } from '@/lib/errorHandler';
import { Play, Hash, Loader2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Checkbox } from '@/components/ui/checkbox';

interface BatchConfig {
  template_id: string;
  models: string[];
  locales: string[];
  replicates: number;
  drift_policy: 'hard' | 'fail' | 'warn';
  grounding_modes: string[];
  inputs: any;
}

export function BatchRunTab() {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState<string>('');
  const [providerVersions, setProviderVersions] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<any[]>([]);
  
  const [batchConfig, setBatchConfig] = useState<BatchConfig>({
    template_id: '',
    models: [],
    locales: ['en-US'],
    replicates: 1,
    drift_policy: 'warn',
    grounding_modes: ['UNGROUNDED'],
    inputs: {}
  });

  const [countries, setCountries] = useState<any[]>([]);
  
  // ALS supported countries based on backend country_codes.py
  const alsCountries = [
    { code: 'DE', name: 'Germany', locale: 'de-DE', emoji: '🇩🇪' },
    { code: 'FR', name: 'France', locale: 'fr-FR', emoji: '🇫🇷' },
    { code: 'IT', name: 'Italy', locale: 'it-IT', emoji: '🇮🇹' },
    { code: 'GB', name: 'United Kingdom', locale: 'en-GB', emoji: '🇬🇧' },
    { code: 'US', name: 'United States', locale: 'en-US', emoji: '🇺🇸' },
    { code: 'CH', name: 'Switzerland', locale: 'de-CH', emoji: '🇨🇭' },
    { code: 'AE', name: 'UAE', locale: 'ar-AE', emoji: '🇦🇪' },
    { code: 'SG', name: 'Singapore', locale: 'en-SG', emoji: '🇸🇬' }
  ];

  const groundingModes = ['UNGROUNDED', 'GROUNDED', 'REQUIRED'];

  useEffect(() => {
    loadTemplates();
    loadProviderVersions();
    loadCountries();
  }, []);

  const loadCountries = async () => {
    try {
      // Try to load countries from API, fallback to ALS defaults
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'}/api/countries`);
      const data = await response.json();
      if (data && data.length > 0) {
        setCountries(data.filter((c: any) => c.is_active));
      } else {
        setCountries(alsCountries);
      }
    } catch (error) {
      console.warn('Countries API not available, using ALS defaults');
      setCountries(alsCountries);
    }
  };

  const loadTemplates = async () => {
    try {
      const data = await templateApi.list();
      setTemplates(data);
    } catch (error: any) {
      logError(error, 'Failed to load templates');
      const errorMessage = handleAPIError(error);
      alert(errorMessage);
    }
  };

  const loadProviderVersions = async () => {
    // Hard-code the versions per user requirements
    // We only support gpt-5 and gemini-2.5-pro  
    setProviderVersions({
      openai: { versions: ['gpt-5'] },
      vertex: { versions: ['gemini-2.5-pro'] }
    });
  };

  const handleTemplateSelect = (templateId: string) => {
    setSelectedTemplate(templateId);
    setBatchConfig({ ...batchConfig, template_id: templateId });
  };

  const handleModelToggle = (model: string) => {
    const models = batchConfig.models.includes(model)
      ? batchConfig.models.filter(m => m !== model)
      : [...batchConfig.models, model];
    setBatchConfig({ ...batchConfig, models });
  };

  const handleLocaleToggle = (locale: string) => {
    const locales = batchConfig.locales.includes(locale)
      ? batchConfig.locales.filter(l => l !== locale)
      : [...batchConfig.locales, locale];
    setBatchConfig({ ...batchConfig, locales });
  };

  const handleGroundingToggle = (mode: string) => {
    const modes = batchConfig.grounding_modes.includes(mode)
      ? batchConfig.grounding_modes.filter(m => m !== mode)
      : [...batchConfig.grounding_modes, mode];
    setBatchConfig({ ...batchConfig, grounding_modes: modes });
  };

  const calculateTotalRuns = () => {
    return batchConfig.models.length * 
           batchConfig.locales.length * 
           batchConfig.grounding_modes.length * 
           batchConfig.replicates;
  };

  const handleRunBatch = async () => {
    if (!selectedTemplate || batchConfig.models.length === 0) {
      alert('Please select a template and at least one model');
      return;
    }

    setLoading(true);
    try {
      // Try to call the actual batch run endpoint
      // Backend now fully supports batch runs
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'}/v1/templates/${selectedTemplate}/batch-run`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Organization-Id': 'test-org'
        },
        body: JSON.stringify({
          models: batchConfig.models,
          locales: batchConfig.locales,
          grounding_modes: batchConfig.grounding_modes,
          replicates: batchConfig.replicates,
          drift_policy: batchConfig.drift_policy,
          inputs: batchConfig.inputs || {}
        })
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        console.error('Batch run failed:', errorData);
        const errorMessage = errorData.detail || errorData.message || JSON.stringify(errorData, null, 2);
        alert(`Batch run failed: ${errorMessage}`);
        return;
      }
      
      const data = await response.json();
      
      if (data && data.batch_id) {
        // Backend returned a successful batch run
        console.log('Batch run successful:', data);
        alert(`✅ Batch run completed!\n\nBatch ID: ${data.batch_id}\nTotal Runs: ${data.total_runs}\nSuccessful: ${data.successful_runs}\nFailed: ${data.failed_runs}`);
        
        // Show run IDs in results  
        if (data.run_ids && data.run_ids.length > 0) {
          const runResults = data.run_ids.map((id: string, index: number) => ({
            run_id: id,
            batch_id: data.batch_id,
            status: 'completed',
            index: index
          }));
          setResults(runResults);
        }
        return;
      }
      
      // Fallback simulation with ALS integration details
      const batchId = `batch-${Date.now()}`;
      const runs = [];
      
      for (const model of batchConfig.models) {
        for (const locale of batchConfig.locales) {
          for (const mode of batchConfig.grounding_modes) {
            for (let i = 0; i < batchConfig.replicates; i++) {
              runs.push({
                run_id: `run-${Date.now()}-${i}`,
                batch_id: batchId,
                model: model,
                locale: locale,
                grounding_mode: mode,
                replicate: i + 1,
                status: 'pending',
                als_enabled: true,
                country_code: countries.find(c => c.locale_code === locale || c.locale === locale)?.code || 'NONE'
              });
            }
          }
        }
      }
      
      setResults(runs);
      alert(`🌍 ALS Batch Run Simulated!\n\nBatch ID: ${batchId}\nTotal Runs: ${runs.length}\n\nEach locale will generate ALS templates with:\n- Country-specific context\n- Locale formatting\n- Regional grounding preferences\n\nNote: Backend batch execution not yet implemented.`);
    } catch (error: any) {
      logError(error, 'Failed to run batch');
      const errorMessage = handleAPIError(error);
      alert(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const getAllModels = () => {
    // Per user requirements: we only support gpt-5 and gemini-2.5-pro
    return ['gpt-5', 'gemini-2.5-pro'];
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Batch Run Configuration</CardTitle>
          <CardDescription>
            Execute template across multiple models, locales, and grounding modes
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Template Selection */}
          <div>
            <Label htmlFor="template">Select Template</Label>
            <Select value={selectedTemplate} onValueChange={handleTemplateSelect}>
              <SelectTrigger>
                <SelectValue placeholder="Choose a template" />
              </SelectTrigger>
              <SelectContent>
                {templates.map((template) => (
                  <SelectItem key={template.template_id} value={template.template_id}>
                    {template.template_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {selectedTemplate && (
              <div className="mt-2 flex items-center gap-2">
                <Hash className="h-3 w-3 text-muted-foreground" />
                <p className="text-xs text-muted-foreground font-mono">
                  {templates.find(t => t.template_id === selectedTemplate)?.template_sha256?.substring(0, 16)}...
                </p>
              </div>
            )}
          </div>

          {/* Model Selection */}
          <div>
            <Label>Select Models (Multiple)</Label>
            <Alert className="mt-2 mb-4">
              <AlertDescription>
                Select multiple models to run the same template across different providers and versions
              </AlertDescription>
            </Alert>
            <div className="grid grid-cols-2 gap-4 max-h-60 overflow-y-auto p-4 border rounded-lg">
              {getAllModels().map((model) => (
                <div key={model} className="flex items-center space-x-2">
                  <Checkbox
                    id={model}
                    checked={batchConfig.models.includes(model)}
                    onCheckedChange={() => handleModelToggle(model)}
                  />
                  <label
                    htmlFor={model}
                    className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
                  >
                    {model}
                  </label>
                </div>
              ))}
            </div>
            <p className="text-sm text-muted-foreground mt-2">
              Selected: {batchConfig.models.length} model(s)
            </p>
          </div>

          {/* ALS Country Selection */}
          <div>
            <Label>Select Countries (ALS)</Label>
            <Alert className="mt-2 mb-4">
              <AlertDescription>
                Select countries for Ambient Location Signals testing. Each country will generate locale-specific ALS templates.
              </AlertDescription>
            </Alert>
            <div className="grid grid-cols-2 gap-2 mt-2">
              {countries.map((country) => {
                const locale = country.locale_code || country.locale;
                return (
                  <Badge
                    key={country.code}
                    variant={batchConfig.locales.includes(locale) ? "default" : "outline"}
                    className="cursor-pointer flex items-center gap-2 p-2"
                    onClick={() => handleLocaleToggle(locale)}
                  >
                    <span>{country.emoji}</span>
                    <span>{country.name} ({locale})</span>
                  </Badge>
                );
              })}
            </div>
            <p className="text-sm text-muted-foreground mt-2">
              Selected: {batchConfig.locales.length} locale(s) - ALS templates will be generated for each
            </p>
          </div>

          {/* Grounding Modes */}
          <div>
            <Label>Grounding Modes</Label>
            <div className="flex gap-4 mt-2">
              {groundingModes.map((mode) => (
                <div key={mode} className="flex items-center space-x-2">
                  <Checkbox
                    id={mode}
                    checked={batchConfig.grounding_modes.includes(mode)}
                    onCheckedChange={() => handleGroundingToggle(mode)}
                  />
                  <label htmlFor={mode} className="text-sm">
                    {mode}
                  </label>
                </div>
              ))}
            </div>
          </div>

          {/* Replicates */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label htmlFor="replicates">Replicates per Configuration</Label>
              <Input
                id="replicates"
                type="number"
                min="1"
                max="10"
                value={batchConfig.replicates}
                onChange={(e) => setBatchConfig({ ...batchConfig, replicates: parseInt(e.target.value) || 1 })}
              />
            </div>
            <div>
              <Label htmlFor="drift">Drift Policy</Label>
              <Select
                value={batchConfig.drift_policy}
                onValueChange={(value: any) => setBatchConfig({ ...batchConfig, drift_policy: value })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="hard">Hard (Stop on drift)</SelectItem>
                  <SelectItem value="fail">Fail (Mark as failed)</SelectItem>
                  <SelectItem value="warn">Warn (Continue with warning)</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Input Variables */}
          <div>
            <Label htmlFor="inputs">Input Variables (JSON)</Label>
            <Textarea
              id="inputs"
              rows={4}
              placeholder='{"variable": "value"}'
              onChange={(e) => {
                try {
                  setBatchConfig({ ...batchConfig, inputs: JSON.parse(e.target.value) });
                } catch (err) {
                  // Invalid JSON, ignore
                }
              }}
            />
          </div>

          {/* Run Summary */}
          <Alert>
            <AlertDescription>
              <strong>Total Runs: {calculateTotalRuns()}</strong>
              <br />
              {batchConfig.models.length} models × {batchConfig.locales.length} locales × 
              {batchConfig.grounding_modes.length} grounding modes × {batchConfig.replicates} replicates
            </AlertDescription>
          </Alert>

          {/* Run Button */}
          <Button
            onClick={handleRunBatch}
            disabled={loading || !selectedTemplate || batchConfig.models.length === 0}
            className="w-full"
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Running Batch...
              </>
            ) : (
              <>
                <Play className="h-4 w-4 mr-2" />
                Execute Batch Run ({calculateTotalRuns()} runs)
              </>
            )}
          </Button>
        </CardContent>
      </Card>

      {/* Results Preview */}
      {results.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Batch Run Results</CardTitle>
            <CardDescription>
              Batch ID: {results[0]?.batch_id}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2 max-h-60 overflow-y-auto">
              {results.slice(0, 10).map((run) => (
                <div key={run.run_id} className="flex items-center justify-between p-2 border rounded">
                  <div className="flex gap-2 flex-wrap">
                    <Badge variant="secondary">{run.model}</Badge>
                    <Badge variant="outline">{run.locale}</Badge>
                    {run.country_code && (
                      <Badge variant="default" className="bg-green-600">
                        🌍 {run.country_code}
                      </Badge>
                    )}
                    <Badge variant="outline">{run.grounding_mode}</Badge>
                    <span className="text-sm text-muted-foreground">Rep #{run.replicate}</span>
                  </div>
                  <Badge variant={run.status === 'pending' ? 'secondary' : 'default'}>
                    {run.status}
                  </Badge>
                </div>
              ))}
              {results.length > 10 && (
                <p className="text-sm text-muted-foreground text-center">
                  ... and {results.length - 10} more runs
                </p>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}