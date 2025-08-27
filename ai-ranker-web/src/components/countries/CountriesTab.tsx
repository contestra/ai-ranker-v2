"use client"

import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Globe, Plus, Edit2, Trash2, Save, X } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import api from '@/lib/api';
import { handleAPIError, logError } from '@/lib/errorHandler';

interface Country {
  id: number;
  code: string;
  name: string;
  emoji: string;
  vat_rate: number;
  plug_types: string;
  emergency_numbers: string;
  locale_code: string;
  is_active: boolean;
}

export function CountriesTab() {
  const [countries, setCountries] = useState<Country[]>([]);
  const [loading, setLoading] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [formData, setFormData] = useState<Partial<Country>>({
    code: '',
    name: '',
    emoji: '',
    vat_rate: 0,
    plug_types: '',
    emergency_numbers: '',
    locale_code: '',
    is_active: true
  });

  // Default countries for ALS testing
  const defaultCountries: Country[] = [
    {
      id: 1,
      code: 'US',
      name: 'United States',
      emoji: '🇺🇸',
      vat_rate: 0,
      plug_types: 'A, B',
      emergency_numbers: '911',
      locale_code: 'en-US',
      is_active: true
    },
    {
      id: 2,
      code: 'GB',
      name: 'United Kingdom',
      emoji: '🇬🇧',
      vat_rate: 20,
      plug_types: 'G',
      emergency_numbers: '999, 112',
      locale_code: 'en-GB',
      is_active: true
    },
    {
      id: 3,
      code: 'DE',
      name: 'Germany',
      emoji: '🇩🇪',
      vat_rate: 19,
      plug_types: 'C, F',
      emergency_numbers: '110, 112',
      locale_code: 'de-DE',
      is_active: true
    },
    {
      id: 4,
      code: 'FR',
      name: 'France',
      emoji: '🇫🇷',
      vat_rate: 20,
      plug_types: 'C, E',
      emergency_numbers: '15, 17, 18, 112',
      locale_code: 'fr-FR',
      is_active: true
    },
    {
      id: 5,
      code: 'JP',
      name: 'Japan',
      emoji: '🇯🇵',
      vat_rate: 10,
      plug_types: 'A, B',
      emergency_numbers: '110, 119',
      locale_code: 'ja-JP',
      is_active: true
    },
    {
      id: 6,
      code: 'CN',
      name: 'China',
      emoji: '🇨🇳',
      vat_rate: 13,
      plug_types: 'A, C, I',
      emergency_numbers: '110, 120',
      locale_code: 'zh-CN',
      is_active: true
    },
    {
      id: 7,
      code: 'BR',
      name: 'Brazil',
      emoji: '🇧🇷',
      vat_rate: 17,
      plug_types: 'C, N',
      emergency_numbers: '190, 192, 193',
      locale_code: 'pt-BR',
      is_active: true
    },
    {
      id: 8,
      code: 'IN',
      name: 'India',
      emoji: '🇮🇳',
      vat_rate: 18,
      plug_types: 'C, D, M',
      emergency_numbers: '100, 108',
      locale_code: 'hi-IN',
      is_active: true
    },
    {
      id: 9,
      code: 'AU',
      name: 'Australia',
      emoji: '🇦🇺',
      vat_rate: 10,
      plug_types: 'I',
      emergency_numbers: '000',
      locale_code: 'en-AU',
      is_active: true
    },
    {
      id: 10,
      code: 'KR',
      name: 'South Korea',
      emoji: '🇰🇷',
      vat_rate: 10,
      plug_types: 'C, F',
      emergency_numbers: '112, 119',
      locale_code: 'ko-KR',
      is_active: true
    }
  ];

  useEffect(() => {
    loadCountries();
  }, []);

  const loadCountries = async () => {
    try {
      setLoading(true);
      // Try to load from API
      const response = await api.get('/api/countries');
      if (response.data && response.data.length > 0) {
        setCountries(response.data);
      } else {
        // Use default countries if API returns empty
        setCountries(defaultCountries);
      }
    } catch (error: any) {
      logError(error, 'Countries API not available');
      // Use defaults silently for countries API since it's optional
      setCountries(defaultCountries);
    } finally {
      setLoading(false);
    }
  };

  const handleEdit = (country: Country) => {
    setEditingId(country.id);
    setFormData(country);
  };

  const handleSave = async () => {
    try {
      setLoading(true);
      if (isCreating) {
        // Add new country
        const newCountry = {
          ...formData,
          id: Math.max(...countries.map(c => c.id)) + 1
        } as Country;
        setCountries([...countries, newCountry]);
        setIsCreating(false);
      } else if (editingId !== null) {
        // Update existing country
        setCountries(countries.map(c => 
          c.id === editingId ? { ...c, ...formData } as Country : c
        ));
        setEditingId(null);
      }
      setFormData({});
    } catch (error: any) {
      logError(error, 'Failed to save country');
      const errorMessage = handleAPIError(error);
      alert(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = (id: number) => {
    if (confirm('Delete this country configuration?')) {
      setCountries(countries.filter(c => c.id !== id));
    }
  };

  const handleCancel = () => {
    setEditingId(null);
    setIsCreating(false);
    setFormData({});
  };

  const handleCreateNew = () => {
    setIsCreating(true);
    setEditingId(null);
    setFormData({
      code: '',
      name: '',
      emoji: '',
      vat_rate: 0,
      plug_types: '',
      emergency_numbers: '',
      locale_code: '',
      is_active: true
    });
  };

  const toggleActive = (id: number) => {
    setCountries(countries.map(c => 
      c.id === id ? { ...c, is_active: !c.is_active } : c
    ));
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex justify-between items-center">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Globe className="h-5 w-5" />
                Countries Configuration (ALS)
              </CardTitle>
              <CardDescription>
                Configure countries for Ambient Location Signals testing. These settings affect locale selection, grounding behavior, and regional compliance.
              </CardDescription>
            </div>
            <Button onClick={handleCreateNew} disabled={isCreating}>
              <Plus className="h-4 w-4 mr-2" />
              Add Country
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <Alert className="mb-4">
            <AlertDescription>
              <strong>ALS (Ambient Location Signals)</strong> use country configurations to simulate regional variations in AI responses. 
              Each country has a locale code that affects language, formatting, and cultural context in template execution.
            </AlertDescription>
          </Alert>

          {isCreating && (
            <Card className="mb-4">
              <CardHeader>
                <CardTitle>New Country Configuration</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="code">Country Code (ISO 3166)</Label>
                    <Input
                      id="code"
                      value={formData.code || ''}
                      onChange={(e) => setFormData({ ...formData, code: e.target.value.toUpperCase() })}
                      placeholder="US"
                      maxLength={2}
                    />
                  </div>
                  <div>
                    <Label htmlFor="name">Country Name</Label>
                    <Input
                      id="name"
                      value={formData.name || ''}
                      onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                      placeholder="United States"
                    />
                  </div>
                  <div>
                    <Label htmlFor="emoji">Flag Emoji</Label>
                    <Input
                      id="emoji"
                      value={formData.emoji || ''}
                      onChange={(e) => setFormData({ ...formData, emoji: e.target.value })}
                      placeholder="🇺🇸"
                    />
                  </div>
                  <div>
                    <Label htmlFor="locale">Locale Code</Label>
                    <Input
                      id="locale"
                      value={formData.locale_code || ''}
                      onChange={(e) => setFormData({ ...formData, locale_code: e.target.value })}
                      placeholder="en-US"
                    />
                  </div>
                  <div>
                    <Label htmlFor="vat">VAT Rate (%)</Label>
                    <Input
                      id="vat"
                      type="number"
                      value={formData.vat_rate || 0}
                      onChange={(e) => setFormData({ ...formData, vat_rate: parseFloat(e.target.value) })}
                      min="0"
                      max="100"
                    />
                  </div>
                  <div>
                    <Label htmlFor="plugs">Plug Types</Label>
                    <Input
                      id="plugs"
                      value={formData.plug_types || ''}
                      onChange={(e) => setFormData({ ...formData, plug_types: e.target.value })}
                      placeholder="A, B"
                    />
                  </div>
                  <div className="col-span-2">
                    <Label htmlFor="emergency">Emergency Numbers</Label>
                    <Input
                      id="emergency"
                      value={formData.emergency_numbers || ''}
                      onChange={(e) => setFormData({ ...formData, emergency_numbers: e.target.value })}
                      placeholder="911"
                    />
                  </div>
                </div>
                <div className="flex justify-end gap-2 mt-4">
                  <Button onClick={handleCancel} variant="outline">
                    <X className="h-4 w-4 mr-2" />
                    Cancel
                  </Button>
                  <Button onClick={handleSave}>
                    <Save className="h-4 w-4 mr-2" />
                    Save
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Country</TableHead>
                  <TableHead>Code</TableHead>
                  <TableHead>Locale</TableHead>
                  <TableHead>VAT</TableHead>
                  <TableHead>Plugs</TableHead>
                  <TableHead>Emergency</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {countries.map((country) => (
                  <TableRow key={country.id}>
                    {editingId === country.id ? (
                      <>
                        <TableCell>
                          <Input
                            value={formData.name || ''}
                            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                            className="w-32"
                          />
                        </TableCell>
                        <TableCell>
                          <Input
                            value={formData.code || ''}
                            onChange={(e) => setFormData({ ...formData, code: e.target.value.toUpperCase() })}
                            className="w-16"
                            maxLength={2}
                          />
                        </TableCell>
                        <TableCell>
                          <Input
                            value={formData.locale_code || ''}
                            onChange={(e) => setFormData({ ...formData, locale_code: e.target.value })}
                            className="w-24"
                          />
                        </TableCell>
                        <TableCell>
                          <Input
                            type="number"
                            value={formData.vat_rate || 0}
                            onChange={(e) => setFormData({ ...formData, vat_rate: parseFloat(e.target.value) })}
                            className="w-16"
                          />
                        </TableCell>
                        <TableCell>
                          <Input
                            value={formData.plug_types || ''}
                            onChange={(e) => setFormData({ ...formData, plug_types: e.target.value })}
                            className="w-20"
                          />
                        </TableCell>
                        <TableCell>
                          <Input
                            value={formData.emergency_numbers || ''}
                            onChange={(e) => setFormData({ ...formData, emergency_numbers: e.target.value })}
                            className="w-24"
                          />
                        </TableCell>
                        <TableCell>
                          <Badge variant={formData.is_active ? "default" : "secondary"}>
                            {formData.is_active ? 'Active' : 'Inactive'}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex justify-end gap-2">
                            <Button size="sm" onClick={handleSave}>
                              <Save className="h-4 w-4" />
                            </Button>
                            <Button size="sm" variant="outline" onClick={handleCancel}>
                              <X className="h-4 w-4" />
                            </Button>
                          </div>
                        </TableCell>
                      </>
                    ) : (
                      <>
                        <TableCell className="font-medium">
                          <span className="flex items-center gap-2">
                            <span className="text-xl">{country.emoji}</span>
                            {country.name}
                          </span>
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline">{country.code}</Badge>
                        </TableCell>
                        <TableCell>
                          <code className="text-sm">{country.locale_code}</code>
                        </TableCell>
                        <TableCell>{country.vat_rate}%</TableCell>
                        <TableCell>{country.plug_types}</TableCell>
                        <TableCell>{country.emergency_numbers}</TableCell>
                        <TableCell>
                          <Badge 
                            variant={country.is_active ? "default" : "secondary"}
                            className="cursor-pointer"
                            onClick={() => toggleActive(country.id)}
                          >
                            {country.is_active ? 'Active' : 'Inactive'}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex justify-end gap-2">
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => handleEdit(country)}
                            >
                              <Edit2 className="h-4 w-4" />
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => handleDelete(country.id)}
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </div>
                        </TableCell>
                      </>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          <div className="mt-4 p-4 bg-muted rounded-lg">
            <h4 className="font-semibold mb-2">ALS Usage in Templates</h4>
            <p className="text-sm text-muted-foreground mb-2">
              When executing templates with ALS enabled, the system will:
            </p>
            <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside">
              <li>Use the country's locale code for language and formatting</li>
              <li>Apply regional grounding preferences (if supported by provider)</li>
              <li>Include locale-specific context in the prompt (VAT rates, emergency numbers, etc.)</li>
              <li>Generate deterministic variations based on the locale seed</li>
              <li>Track locale effectiveness in run results</li>
            </ul>
            <p className="text-sm text-muted-foreground mt-2">
              <strong>Note:</strong> Only active countries will be available for selection in batch runs.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}