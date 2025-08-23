'use client'

import { useState, useEffect } from 'react'
import Countries from './Countries'
import GroundingTestGrid from './GroundingTestGrid'
import { 
  ExclamationCircleIcon, 
  PlayIcon, 
  PlusIcon, 
  TrashIcon, 
  GlobeAltIcon, 
  CircleStackIcon, 
  ChartBarIcon, 
  MapPinIcon, 
  CheckCircleIcon, 
  XCircleIcon,
  PencilIcon,
  DocumentDuplicateIcon,
  DocumentTextIcon,
  ClipboardDocumentListIcon,
  ChartPieIcon,
  ClockIcon,
  BeakerIcon
} from '@heroicons/react/24/outline'

interface PromptTemplate {
  id: number
  brand_name: string
  template_name: string
  prompt_text: string
  prompt_type: string
  model_name?: string  // Model for this template
  countries: string[]
  grounding_modes: string[]
  is_active: boolean
  created_at: string
}

interface PromptRun {
  id: number
  template_id: number
  template_name?: string  // Will be populated from templates
  brand_name: string
  model_name: string
  country_code: string
  grounding_mode: string
  status: string
  started_at: string | null
  completed_at: string | null
  error_message: string | null
  created_at: string
}

interface PromptResult {
  run_id: number
  country: string
  grounding_mode: string
  brand_mentioned: boolean
  mention_count: number
  response_preview: string
  error?: string
}

interface Analytics {
  brand_name: string
  statistics: {
    total_runs: number
    successful_runs: number
    failed_runs: number
    mention_rate: number
    avg_mentions_per_response: number
    avg_confidence: number
  }
  grounding_comparison: {
    [key: string]: {
      run_count: number
      mention_rate: number
    }
  }
  country_comparison: {
    [key: string]: {
      run_count: number
      mention_rate: number
    }
  }
}

interface PromptTrackingProps {
  brandName: string
  brandId: number
}

export default function PromptTracking({ brandName, brandId }: PromptTrackingProps) {
  const [activeTab, setActiveTab] = useState('templates')
  const [templates, setTemplates] = useState<PromptTemplate[]>([])
  const [runs, setRuns] = useState<PromptRun[]>([])
  const [analytics, setAnalytics] = useState<Analytics | null>(null)
  const [loading, setLoading] = useState(false)
  const [runningTemplates, setRunningTemplates] = useState<Set<number>>(new Set())
  const [editingTemplate, setEditingTemplate] = useState<number | null>(null)
  const [expandedResults, setExpandedResults] = useState<{ [key: number]: any }>({})
  const [loadingResults, setLoadingResults] = useState<{ [key: number]: boolean }>({})
  const [duplicateError, setDuplicateError] = useState<{ show: boolean; existingTemplate?: string } | null>(null)
  const [duplicateCheck, setDuplicateCheck] = useState<{
    checking: boolean
    isDuplicate: boolean
    existingTemplate?: { id: number; name: string; created_at: string; model?: string }
    lastChecked?: string
    isCopyOperation?: boolean  // Track if this is from a copy operation
    originalCopiedData?: {  // Store the original copied template data
      prompt_text: string
      model_name: string
      countries: string[]
      grounding_modes: string[]
      prompt_type: string
    }
    sameTextDiffConfig?: boolean  // Same prompt text but different config
    similarTemplates?: Array<{ template_id: number; name: string; model_id: string; countries: string[]; grounding_modes: string[] }>
  }>({ checking: false, isDuplicate: false })
  
  const [nameError, setNameError] = useState<string>('')  // Track template name errors
  
  // Form state for new/edit template
  const [newTemplate, setNewTemplate] = useState({
    template_name: '',
    prompt_text: '',
    prompt_type: 'custom',
    model_name: 'gemini',  // Default model for the template
    countries: ['NONE'],  // Default to base model testing
    grounding_modes: ['off']  // Updated to use new grounding mode
  })
  
  // Model selection state - for running tests only
  const [selectedModel, setSelectedModel] = useState('gemini')
  // Model selection for new template creation
  const [newTemplateModel, setNewTemplateModel] = useState('gemini')

  // Available options
  const countries = [
    { value: 'NONE', label: '🌐 Base Model (No Location)' },
    { value: 'US', label: '🇺🇸 United States' },
    { value: 'GB', label: '🇬🇧 United Kingdom' },
    { value: 'DE', label: '🇩🇪 Germany' },
    { value: 'CH', label: '🇨🇭 Switzerland' },
    { value: 'AE', label: '🇦🇪 UAE' },
    { value: 'SG', label: '🇸🇬 Singapore' },
    { value: 'IT', label: '🇮🇹 Italy' },
    { value: 'FR', label: '🇫🇷 France' }
  ]

  const promptTypes = [
    { value: 'recognition', label: 'Brand Recognition' },
    { value: 'competitive', label: 'Competitor Analysis' },
    { value: 'product', label: 'Product Knowledge' },
    { value: 'industry', label: 'Industry Position' },
    { value: 'custom', label: 'Custom' }
  ]
  
  const models = [
    { value: 'gpt-5', label: 'GPT-5' },
    { value: 'gpt-5-mini', label: 'GPT-5 Mini' },
    { value: 'gpt-5-nano', label: 'GPT-5 Nano' },
    { value: 'gpt-4o', label: 'GPT-4o (Legacy)' },
    { value: 'gpt-4o-mini', label: 'GPT-4o Mini (Legacy)' },
    { value: 'gemini', label: 'Gemini 2.5 Pro' },
    { value: 'gemini-flash', label: 'Gemini 2.0 Flash Exp' }
  ]

  // Fetch templates
  const fetchTemplates = async () => {
    try {
      const response = await fetch(`http://localhost:8000/api/prompt-tracking/templates?brand_name=${brandName}`)
      const data = await response.json()
      console.log('Templates fetched:', data.templates)
      setTemplates(data.templates || [])
    } catch (error) {
      console.error('Failed to fetch templates:', error)
    }
  }

  // Fetch runs
  const fetchRuns = async () => {
    try {
      const response = await fetch(`http://localhost:8000/api/prompt-tracking/runs?brand_name=${brandName}&limit=20`)
      const data = await response.json()
      // Add template names to runs
      const runsWithNames = (data.runs || []).map((run: PromptRun) => {
        const template = templates.find(t => t.id === run.template_id)
        return {
          ...run,
          template_name: template?.template_name || `Template #${run.template_id}`
        }
      })
      setRuns(runsWithNames)
    } catch (error) {
      console.error('Failed to fetch runs:', error)
    }
  }
  
  // Helper to get template name
  const getTemplateName = (templateId: number) => {
    const template = templates.find(t => t.id === templateId)
    return template?.template_name || `Template #${templateId}`
  }

  // Fetch analytics
  const fetchAnalytics = async () => {
    try {
      const response = await fetch(`http://localhost:8000/api/prompt-tracking/analytics/${brandName}`)
      const data = await response.json()
      setAnalytics(data)
    } catch (error) {
      console.error('Failed to fetch analytics:', error)
    }
  }

  useEffect(() => {
    if (brandName) {
      fetchTemplates()
      fetchAnalytics()
    }
  }, [brandName])
  
  // Fetch runs after templates are loaded
  useEffect(() => {
    if (brandName && templates.length >= 0) {
      fetchRuns()
    }
  }, [brandName, templates])

  // Check for duplicate prompts in real-time
  useEffect(() => {
    const checkDuplicate = async () => {
      // Skip all duplicate checking during copy operations
      if (duplicateCheck.isCopyOperation) {
        return
      }

      if (!newTemplate.prompt_text || newTemplate.prompt_text.length < 5) {
        setDuplicateCheck(prev => ({ ...prev, checking: false, isDuplicate: false }))
        return
      }

      // Create a bundle key for caching
      const bundleKey = JSON.stringify({
        prompt_text: newTemplate.prompt_text,
        model_name: newTemplate.model_name,
        countries: newTemplate.countries.sort(),
        grounding_modes: newTemplate.grounding_modes.sort(),
        prompt_type: newTemplate.prompt_type
      })
      
      // Don't re-check the same bundle
      if (duplicateCheck.lastChecked === bundleKey) {
        return
      }

      setDuplicateCheck(prev => ({ ...prev, checking: true }))

      const checkData = {
        brand_name: brandName,
        prompt_text: newTemplate.prompt_text,
        model_name: newTemplate.model_name,
        countries: newTemplate.countries,
        grounding_modes: newTemplate.grounding_modes,
        prompt_type: newTemplate.prompt_type
      }
      
      console.log('Checking duplicate with:', checkData)
      
      try {
        const response = await fetch('http://localhost:8000/api/prompt-tracking/templates/check-duplicate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(checkData)
        })

        if (response.ok) {
          const data = await response.json()
          setDuplicateCheck({
            checking: false,
            isDuplicate: data.is_duplicate || data.exact_match,
            existingTemplate: data.existing_template,
            lastChecked: bundleKey,
            sameTextDiffConfig: data.same_text_diff_config,
            similarTemplates: data.closest
          })
        }
      } catch (error) {
        console.error('Failed to check duplicate:', error)
        setDuplicateCheck({ checking: false, isDuplicate: false })
      }
    }

    // Debounce the check by 500ms
    const timer = setTimeout(checkDuplicate, 500)
    return () => clearTimeout(timer)
  }, [
    newTemplate.prompt_text, 
    newTemplate.model_name,
    newTemplate.prompt_type,
    newTemplate.countries,
    newTemplate.grounding_modes,
    brandName, 
    duplicateCheck.isCopyOperation
  ])
  
  // Clear copy flag when user modifies any key field
  useEffect(() => {
    if (duplicateCheck.isCopyOperation && duplicateCheck.originalCopiedData) {
      const orig = duplicateCheck.originalCopiedData
      const hasChanged = 
        newTemplate.prompt_text !== orig.prompt_text ||
        newTemplate.model_name !== orig.model_name ||
        newTemplate.prompt_type !== orig.prompt_type ||
        JSON.stringify(newTemplate.countries.sort()) !== JSON.stringify(orig.countries.sort()) ||
        JSON.stringify(newTemplate.grounding_modes.sort()) !== JSON.stringify(orig.grounding_modes.sort())
      
      if (hasChanged) {
        // User has modified something - clear the copy flag and reset duplicate state
        setDuplicateCheck(prev => ({ 
          ...prev, 
          isCopyOperation: false,
          originalCopiedData: undefined,
          isDuplicate: false,
          checking: false,
          lastChecked: undefined  // Force re-check with new config
        }))
      }
    }
  }, [newTemplate, duplicateCheck.isCopyOperation, duplicateCheck.originalCopiedData])

  // Check for duplicate template name in real-time
  useEffect(() => {
    if (!newTemplate.template_name) {
      setNameError('')
      return
    }
    
    const duplicateName = templates.find(t => 
      t.brand_name === brandName && 
      t.template_name === newTemplate.template_name && 
      t.id !== editingTemplate
    )
    
    if (duplicateName) {
      setNameError('A template with this name already exists. Please choose a unique name.')
    } else {
      setNameError('')
    }
  }, [newTemplate.template_name, templates, brandName, editingTemplate])

  // Helper to check if template has been modified from copy
  const isUnmodifiedCopy = () => {
    if (!duplicateCheck.isCopyOperation || !duplicateCheck.originalCopiedData) {
      return false
    }
    
    const orig = duplicateCheck.originalCopiedData
    return (
      newTemplate.prompt_text === orig.prompt_text &&
      newTemplate.model_name === orig.model_name &&
      newTemplate.prompt_type === orig.prompt_type &&
      JSON.stringify(newTemplate.countries.sort()) === JSON.stringify(orig.countries.sort()) &&
      JSON.stringify(newTemplate.grounding_modes.sort()) === JSON.stringify(orig.grounding_modes.sort())
    )
  }

  // Create or update template
  const saveTemplate = async () => {
    // Clear any existing error when attempting to save
    setDuplicateError(null)
    
    if (!newTemplate.template_name || !newTemplate.prompt_text) {
      alert('Please fill in template name and prompt text')
      return
    }

    // Check if there's a name error
    if (nameError) {
      alert(nameError)
      return
    }

    // Check if this is an unmodified copy
    if (isUnmodifiedCopy()) {
      const proceed = window.confirm(
        "You haven't modified the copied template. This will create an exact duplicate.\n\n" +
        "Consider changing the model, countries, or grounding modes to create a variation.\n\n" +
        "Do you want to continue anyway?"
      )
      if (!proceed) {
        return
      }
    }

    try {
      const url = editingTemplate 
        ? `http://localhost:8000/api/prompt-tracking/templates/${editingTemplate}`
        : 'http://localhost:8000/api/prompt-tracking/templates'
      
      console.log('Saving template with data:', {
        brand_name: brandName,
        ...newTemplate
      })
      
      const response = await fetch(url, {
        method: editingTemplate ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          brand_name: brandName,
          ...newTemplate
        })
      })
      
      if (response.ok) {
        await fetchTemplates()  // Wait for templates to refresh
        setNewTemplate({
          template_name: '',
          prompt_text: '',
          prompt_type: 'custom',
          model_name: 'gemini',  // Include model_name in reset
          countries: ['NONE'],
          grounding_modes: ['off']  // Updated to new grounding mode
        })
        setEditingTemplate(null)
      } else if (response.status === 409) {
        // Handle duplicate template error
        const errorData = await response.json()
        const detail = errorData.detail
        
        // Set error state to show in UI
        setDuplicateError({
          show: true,
          existingTemplate: detail.existing_template?.name || 'another template'
        })
      } else {
        // Handle other errors
        const errorData = await response.json()
        console.error('Failed to save template:', errorData)
        alert('Failed to save template. Please try again.')
      }
    } catch (error) {
      console.error('Failed to save template:', error)
      alert('An error occurred while saving the template.')
    }
  }

  // Delete template
  const deleteTemplate = async (templateId: number) => {
    if (!confirm('Are you sure you want to delete this template?')) {
      return
    }

    try {
      const response = await fetch(`http://localhost:8000/api/prompt-tracking/templates/${templateId}`, {
        method: 'DELETE'
      })
      
      if (response.ok) {
        fetchTemplates()
      }
    } catch (error) {
      console.error('Failed to delete template:', error)
    }
  }

  // Edit template
  const startEditTemplate = (template: PromptTemplate) => {
    setNewTemplate({
      template_name: template.template_name,
      prompt_text: template.prompt_text,
      prompt_type: template.prompt_type,
      countries: template.countries,
      grounding_modes: template.grounding_modes
    })
    setEditingTemplate(template.id)
  }

  // Copy template
  const copyTemplate = (template: PromptTemplate) => {
    const copiedData = {
      template_name: '',  // Clear the name so user must enter a new one
      prompt_text: template.prompt_text,  // Keep exact text
      prompt_type: template.prompt_type,
      model_name: template.model_name || 'gemini',  // Copy the model from the original template
      countries: template.countries,
      grounding_modes: template.grounding_modes
    }
    
    setNewTemplate(copiedData)
    setEditingTemplate(null)
    
    // Mark this as a copy operation and store original data to check if modified
    setDuplicateCheck({ 
      checking: false, 
      isDuplicate: false,
      isCopyOperation: true,
      originalCopiedData: {
        prompt_text: copiedData.prompt_text,
        model_name: copiedData.model_name,
        countries: [...copiedData.countries],
        grounding_modes: [...copiedData.grounding_modes],
        prompt_type: copiedData.prompt_type
      },
      lastChecked: undefined  // Reset so it will check when user modifies
    })
  }

  // Cancel edit
  const cancelEdit = () => {
    setNewTemplate({
      template_name: '',
      prompt_text: '',
      prompt_type: 'custom',
      countries: ['NONE'],
      grounding_modes: ['off']  // Updated to new grounding mode
    })
    setEditingTemplate(null)
  }

  // Run prompt test
  const runPrompt = async (templateId: number) => {
    console.log(`Starting prompt run for template ${templateId}`)
    setRunningTemplates(prev => new Set([...prev, templateId]))
    
    // Find the template to get its model
    const template = templates.find(t => t.id === templateId)
    const modelToUse = template?.model_name || 'gemini'
    
    try {
      // Add timeout to prevent hanging forever
      const controller = new AbortController()
      const timeout = setTimeout(() => {
        console.log('Request timeout - aborting after 2 minutes')
        controller.abort()
      }, 120000) // 2 minute timeout
      
      console.log(`Sending request to background endpoint with model: ${modelToUse}`)
      const response = await fetch('http://localhost:8000/api/prompt-tracking-background/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          template_id: templateId,
          brand_name: brandName,
          model_name: modelToUse,
          wait_for_completion: true  // Wait for results to avoid complexity
        }),
        signal: controller.signal
      })
      
      clearTimeout(timeout)
      console.log(`Response received: status=${response.status}, ok=${response.ok}`)
      
      if (response.ok) {
        const data = await response.json()
        console.log('Run results:', data)
        // Show success message
        alert(`Test completed successfully! Check the Results tab for details.`)
        // Refresh runs with template names
        setTimeout(() => {
          fetchRuns()
          fetchAnalytics()
        }, 500)
      } else {
        const errorText = await response.text()
        console.error('Run failed:', errorText)
        alert(`Failed to run test: ${errorText || response.statusText}`)
      }
    } catch (error: any) {
      console.error('Failed to run prompt:', error)
      if (error.name === 'AbortError') {
        alert('Request timed out after 2 minutes. The API might be experiencing issues.')
      } else {
        alert(`Failed to run test: ${error.message}`)
      }
    } finally {
      setRunningTemplates(prev => {
        const newSet = new Set(prev)
        newSet.delete(templateId)
        return newSet
      })
    }
  }

  // Fetch detailed result for a run
  const fetchResult = async (runId: number) => {
    console.log(`Fetching result for run ${runId}`)
    if (expandedResults[runId]) {
      // Already loaded, just toggle visibility
      console.log('Result already loaded, toggling visibility')
      setExpandedResults(prev => {
        const newExpanded = { ...prev }
        delete newExpanded[runId]
        return newExpanded
      })
      return
    }

    console.log('Loading result from API...')
    setLoadingResults(prev => ({ ...prev, [runId]: true }))
    try {
      const response = await fetch(`http://localhost:8000/api/prompt-tracking/results/${runId}`)
      console.log(`Result API response: status=${response.status}, ok=${response.ok}`)
      if (response.ok) {
        const data = await response.json()
        console.log('Result data received:', data)
        setExpandedResults(prev => ({ ...prev, [runId]: data.result }))
      } else {
        console.error(`Failed to fetch result: ${response.status} ${response.statusText}`)
      }
    } catch (error) {
      console.error('Failed to fetch result:', error)
    } finally {
      console.log('Setting loading to false')
      setLoadingResults(prev => ({ ...prev, [runId]: false }))
    }
  }

  // Import Lucide icons at the top of the component
  const { FileText, ClipboardList, PieChart, Clock, Globe } = require('lucide-react')
  
  const tabs = [
    { id: 'templates', label: 'Templates', icon: FileText },
    { id: 'results', label: 'Results', icon: ClipboardList },
    { id: 'analytics', label: 'Analytics', icon: PieChart },
    { id: 'countries', label: 'Countries', icon: Globe },
    { id: 'schedule', label: 'Schedule', icon: Clock },
    { id: 'grounding', label: 'Grounding Test', icon: BeakerIcon }
  ]

  return (
    <div className="space-y-6">
      {/* Tab navigation at the top */}
      <div className="bg-white rounded-lg shadow">
        <div className="border-b border-gray-200">
          <nav className="flex">
            {tabs.map((tab) => {
              const Icon = tab.icon
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex-1 flex items-center justify-center gap-2 py-4 px-4 border-b-2 font-medium text-sm transition-colors ${
                    activeTab === tab.id
                      ? 'border-indigo-500 text-indigo-600 bg-indigo-50/50'
                      : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 hover:bg-gray-50'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  {tab.label}
                </button>
              )
            })}
          </nav>
        </div>
      </div>

      {/* Tab content */}
      <div className="mt-4">
        {/* Templates Tab */}
        {activeTab === 'templates' && (
          <div className="space-y-4">
            {/* Create/Edit Template */}
            <div className="bg-white rounded-lg shadow">
              <div className="px-6 py-4 border-b flex justify-between items-start">
                <div>
                  <h3 className="text-lg font-medium">
                    {editingTemplate ? 'Edit Template' : 'Create New Template'}
                  </h3>
                  <p className="text-sm text-gray-500 mt-1">
                    Define prompts to test how AI models respond to questions about your brand
                  </p>
                </div>
                {editingTemplate && (
                  <button
                    onClick={cancelEdit}
                    className="text-sm text-gray-500 hover:text-gray-700"
                  >
                    Cancel
                  </button>
                )}
              </div>
              <div className="p-6 space-y-4">
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label htmlFor="template-name" className="block text-sm font-medium text-gray-700">
                        Template Name
                      </label>
                      {nameError && (
                        <span className="text-xs text-red-600 flex items-center">
                          <ExclamationCircleIcon className="w-3 h-3 mr-1" />
                          {nameError}
                        </span>
                      )}
                    </div>
                    <input
                      type="text"
                      id="template-name"
                      placeholder="e.g., Brand Recognition Test"
                      value={newTemplate.template_name}
                      onChange={(e) => setNewTemplate({ ...newTemplate, template_name: e.target.value })}
                      className={`w-full px-3 py-2 border rounded-md focus:outline-none ${
                        nameError 
                          ? 'border-red-400 focus:ring-red-500 focus:border-red-500 bg-red-50/50' 
                          : 'border-gray-300 focus:ring-indigo-500 focus:border-indigo-500'
                      }`}
                    />
                    {duplicateCheck.isCopyOperation && !newTemplate.template_name && (
                      <p className="text-xs text-amber-600 mt-1">
                        Please enter a unique name for this copied template
                      </p>
                    )}
                  </div>
                  <div>
                    <label htmlFor="model-name" className="block text-sm font-medium text-gray-700 mb-1">
                      AI Model
                    </label>
                    <select
                      id="model-name"
                      value={newTemplate.model_name}
                      onChange={(e) => setNewTemplate({ ...newTemplate, model_name: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
                    >
                      {models.map(model => (
                        <option key={model.value} value={model.value}>
                          {model.label}
                        </option>
                      ))}
                    </select>
                    {/* GPT-5 is now working - removed outdated warning */}
                  </div>
                  <div>
                    <label htmlFor="prompt-type" className="block text-sm font-medium text-gray-700 mb-1">
                      Type
                    </label>
                    <select
                      id="prompt-type"
                      value={newTemplate.prompt_type}
                      onChange={(e) => setNewTemplate({ ...newTemplate, prompt_type: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
                    >
                      {promptTypes.map(type => (
                        <option key={type.value} value={type.value}>
                          {type.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label htmlFor="prompt-text" className="block text-sm font-medium text-gray-700">
                      Prompt Text
                    </label>
                    {duplicateCheck.checking && (
                      <span className="text-xs text-gray-500 flex items-center">
                        <ClockIcon className="w-3 h-3 mr-1 animate-spin" />
                        Checking for duplicates...
                      </span>
                    )}
                    {!duplicateCheck.checking && duplicateCheck.isDuplicate && (
                      <span className="text-xs text-amber-600 flex items-center">
                        <ExclamationCircleIcon className="w-3 h-3 mr-1" />
                        Duplicate found
                      </span>
                    )}
                    {!duplicateCheck.checking && !duplicateCheck.isDuplicate && newTemplate.prompt_text.length > 5 && (
                      <span className="text-xs text-green-600 flex items-center">
                        <CheckCircleIcon className="w-3 h-3 mr-1" />
                        Unique prompt
                      </span>
                    )}
                  </div>
                  <textarea
                    id="prompt-text"
                    placeholder="Use {brand_name} as a placeholder for the brand"
                    value={newTemplate.prompt_text}
                    onChange={(e) => {
                      setNewTemplate({ ...newTemplate, prompt_text: e.target.value })
                      // Clear old error state
                      if (duplicateError?.show) {
                        setDuplicateError(null)
                      }
                    }}
                    rows={3}
                    className={`w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 ${
                      duplicateCheck.isDuplicate ? 'border-amber-400 bg-amber-50' : 'border-gray-300'
                    }`}
                  />
                  
                  {/* Show duplicate info with helpful options - but not when copying */}
                  {duplicateCheck.isDuplicate && duplicateCheck.existingTemplate && !duplicateCheck.isCopyOperation && (
                    <div className="mt-2 p-3 bg-amber-50 border border-amber-200 rounded-md">
                      <div className="flex justify-between items-start">
                        <div className="flex-1">
                          <p className="text-sm font-medium text-amber-800">
                            This prompt already exists
                          </p>
                          <p className="text-sm text-amber-700 mt-1">
                            Template: <span className="font-medium">"{duplicateCheck.existingTemplate.name}"</span>
                          </p>
                          <p className="text-xs text-amber-600 mt-1">
                            Created: {new Date(duplicateCheck.existingTemplate.created_at).toLocaleDateString()}
                          </p>
                        </div>
                        <div className="flex flex-col gap-2 ml-4">
                          <button
                            type="button"
                            onClick={() => {
                              // Find and run the existing template
                              const existing = templates.find(t => t.id === duplicateCheck.existingTemplate?.id)
                              if (existing) {
                                runPrompt(existing.id)
                                // Clear the form
                                setNewTemplate({
                                  template_name: '',
                                  prompt_text: '',
                                  prompt_type: 'custom',
                                  model_name: 'gemini',
                                  countries: ['NONE'],
                                  grounding_modes: ['off']  // Updated to new grounding mode
                                })
                                setDuplicateCheck({ checking: false, isDuplicate: false })
                              }
                            }}
                            className="text-xs px-3 py-1 bg-white border border-amber-300 text-amber-700 rounded hover:bg-amber-100"
                          >
                            Run Existing
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              // Scroll to and highlight the existing template
                              const element = document.getElementById(`template-${duplicateCheck.existingTemplate?.id}`)
                              if (element) {
                                element.scrollIntoView({ behavior: 'smooth', block: 'center' })
                                element.classList.add('ring-2', 'ring-amber-400')
                                setTimeout(() => {
                                  element.classList.remove('ring-2', 'ring-amber-400')
                                }, 3000)
                              }
                            }}
                            className="text-xs px-3 py-1 bg-white border border-amber-300 text-amber-700 rounded hover:bg-amber-100"
                          >
                            View Template
                          </button>
                        </div>
                      </div>
                      <p className="text-xs text-amber-600 mt-2">
                        💡 Tip: Run the existing template with different models, or modify your prompt to create a variation
                      </p>
                    </div>
                  )}
                  
                  {/* Regular tip when no duplicate */}
                  {!duplicateCheck.isDuplicate && (
                    <p className="text-sm text-gray-500 mt-1">
                      Tip: Use {'{brand_name}'} in your prompt and it will be replaced with "{brandName}"
                    </p>
                  )}
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="field-label">Countries</label>
                    <div className="flex flex-wrap gap-2">
                      {countries.map(country => (
                        <button
                          key={country.value}
                          onClick={() => {
                            const updated = newTemplate.countries.includes(country.value)
                              ? newTemplate.countries.filter(c => c !== country.value)
                              : [...newTemplate.countries, country.value]
                            setNewTemplate({ ...newTemplate, countries: updated })
                          }}
                          className={`px-3 py-1 rounded-[50px] text-sm font-display transition-all duration-200 ${
                            newTemplate.countries.includes(country.value)
                              ? 'bg-white text-contestra-gray-900 border border-contestra-gray-900'
                              : 'bg-white text-contestra-text-meta border border-black/[0.06] hover:bg-contestra-gray-100'
                          }`}
                        >
                          {country.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div>
                    <label className="field-label">Grounding Modes</label>
                    <div className="flex gap-2 flex-wrap">
                      <button
                        onClick={() => {
                          const updated = newTemplate.grounding_modes.includes('off')
                            ? newTemplate.grounding_modes.filter(m => m !== 'off')
                            : [...newTemplate.grounding_modes, 'off']
                          setNewTemplate({ ...newTemplate, grounding_modes: updated })
                        }}
                        className={`flex items-center px-3 py-1 rounded-[50px] text-sm font-display transition-all duration-200 ${
                          newTemplate.grounding_modes.includes('off')
                            ? 'bg-white text-contestra-gray-900 border border-contestra-gray-900'
                            : 'bg-white text-contestra-text-meta border border-black/[0.06] hover:bg-contestra-gray-100'
                        }`}
                      >
                        <CircleStackIcon className="w-4 h-4 mr-1" />
                        Ungrounded (Off)
                      </button>
                      <button
                        onClick={() => {
                          const updated = newTemplate.grounding_modes.includes('preferred')
                            ? newTemplate.grounding_modes.filter(m => m !== 'preferred')
                            : [...newTemplate.grounding_modes, 'preferred']
                          setNewTemplate({ ...newTemplate, grounding_modes: updated })
                        }}
                        className={`flex items-center px-3 py-1 rounded-[50px] text-sm font-display transition-all duration-200 ${
                          newTemplate.grounding_modes.includes('preferred')
                            ? 'bg-white text-contestra-gray-900 border border-contestra-gray-900'
                            : 'bg-white text-contestra-text-meta border border-black/[0.06] hover:bg-contestra-gray-100'
                        }`}
                      >
                        <GlobeAltIcon className="w-4 h-4 mr-1" />
                        Grounded (Auto)
                      </button>
                      <button
                        onClick={() => {
                          const updated = newTemplate.grounding_modes.includes('required')
                            ? newTemplate.grounding_modes.filter(m => m !== 'required')
                            : [...newTemplate.grounding_modes, 'required']
                          setNewTemplate({ ...newTemplate, grounding_modes: updated })
                        }}
                        className={`flex items-center px-3 py-1 rounded-[50px] text-sm font-display transition-all duration-200 ${
                          newTemplate.grounding_modes.includes('required')
                            ? 'bg-white text-contestra-gray-900 border border-contestra-gray-900'
                            : 'bg-white text-contestra-text-meta border border-black/[0.06] hover:bg-contestra-gray-100'
                        }`}
                      >
                        <ExclamationCircleIcon className="w-4 h-4 mr-1" />
                        Grounded (Required)
                      </button>
                    </div>
                  </div>
                </div>

                <button
                  onClick={saveTemplate}
                  disabled={(duplicateCheck.isDuplicate && !editingTemplate && !duplicateCheck.isCopyOperation) || !!nameError}
                  className={`w-full flex items-center justify-center ${
                    (duplicateCheck.isDuplicate && !editingTemplate && !duplicateCheck.isCopyOperation) || nameError
                      ? 'bg-gray-300 text-gray-500 cursor-not-allowed py-2 px-4 rounded-md' 
                      : 'btn-contestra-primary'
                  }`}
                  title={
                    nameError 
                      ? nameError 
                      : (duplicateCheck.isDuplicate && !duplicateCheck.isCopyOperation 
                          ? 'This configuration already exists. Modify something to make it unique.' 
                          : '')
                  }
                >
                  {nameError ? (
                    <>
                      <ExclamationCircleIcon className="w-5 h-5 mr-2" />
                      Name Already Exists
                    </>
                  ) : duplicateCheck.isDuplicate && !editingTemplate && !duplicateCheck.isCopyOperation ? (
                    <>
                      <ExclamationCircleIcon className="w-5 h-5 mr-2" />
                      Duplicate - Use Existing or Modify Prompt
                    </>
                  ) : (
                    <>
                      <PlusIcon className="w-5 h-5 mr-2" />
                      {editingTemplate ? 'Update Template' : 'Create Template'}
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Existing Templates */}
            <div className="grid gap-4">
              {templates.filter(t => t.brand_name === brandName).map(template => (
                <div 
                  key={template.id} 
                  id={`template-${template.id}`}
                  className="bg-white rounded-lg shadow transition-all duration-300 hover:shadow-md">
                  <div className="px-6 py-4 flex justify-between items-start">
                    <div className="flex-1">
                      <h4 className="text-lg font-medium">{template.template_name}</h4>
                      <p className="text-gray-600 mt-1">{template.prompt_text}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => copyTemplate(template)}
                        className="p-2 text-gray-600 hover:text-indigo-600 hover:bg-indigo-50 rounded"
                        title="Copy Template"
                      >
                        <DocumentDuplicateIcon className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => startEditTemplate(template)}
                        className="p-2 text-gray-600 hover:text-blue-600 hover:bg-blue-50 rounded"
                        title="Edit Template"
                      >
                        <PencilIcon className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => deleteTemplate(template.id)}
                        className="p-2 text-gray-600 hover:text-red-600 hover:bg-red-50 rounded"
                        title="Delete Template"
                      >
                        <TrashIcon className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => runPrompt(template.id)}
                        disabled={runningTemplates.has(template.id)}
                        className={`flex items-center px-3 py-1 text-white rounded-[50px] hover:opacity-90 disabled:bg-contestra-gray-400 ml-2 transition-all duration-200 ${
                          runningTemplates.has(template.id) ? 'bg-contestra-orange' : 'bg-contestra-green'
                        }`}
                        title={`Run test with ${models.find(m => m.value === selectedModel)?.label || selectedModel}`}
                      >
                        {runningTemplates.has(template.id) ? (
                          <>Running...</>
                        ) : (
                          <>
                            <PlayIcon className="w-4 h-4 mr-1" />
                            Run Test
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                  <div className="px-6 pb-4 flex gap-4 text-sm">
                    <div className="flex items-center gap-2">
                      <MapPinIcon className="w-4 h-4 text-gray-400" />
                      <span>{template.countries.join(', ')}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      {template.grounding_modes.includes('off') && (
                        <span className="flex items-center px-2 py-1 bg-gray-100 rounded text-xs">
                          <CircleStackIcon className="w-3 h-3 mr-1" />
                          Ungrounded
                        </span>
                      )}
                      {template.grounding_modes.includes('preferred') && (
                        <span className="flex items-center px-2 py-1 bg-blue-100 rounded text-xs">
                          <GlobeAltIcon className="w-3 h-3 mr-1" />
                          Auto
                        </span>
                      )}
                      {template.grounding_modes.includes('required') && (
                        <span className="flex items-center px-2 py-1 bg-amber-100 rounded text-xs">
                          <ExclamationCircleIcon className="w-3 h-3 mr-1" />
                          Required
                        </span>
                      )}
                      {/* Legacy support for old templates - only show if new modes aren't present */}
                      {!template.grounding_modes.includes('off') && template.grounding_modes.includes('none') && (
                        <span className="flex items-center px-2 py-1 bg-gray-100 rounded text-xs">
                          <CircleStackIcon className="w-3 h-3 mr-1" />
                          Ungrounded
                        </span>
                      )}
                      {!template.grounding_modes.includes('preferred') && !template.grounding_modes.includes('required') && template.grounding_modes.includes('web') && (
                        <span className="flex items-center px-2 py-1 bg-blue-100 rounded text-xs">
                          <GlobeAltIcon className="w-3 h-3 mr-1" />
                          Grounded
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2 ml-auto">
                      <span className="text-xs text-contestra-text-meta font-mono tracking-[0.02em]">
                        Model: <span className="font-medium text-contestra-accent">{models.find(m => m.value === (template.model_name || 'gemini'))?.label || template.model_name || 'Gemini 2.5 Pro'}</span>
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Results Tab */}
        {activeTab === 'results' && (
          <div className="bg-white rounded-lg shadow">
            <div className="px-6 py-4 border-b flex justify-between items-start">
              <div>
                <h3 className="text-lg font-medium">Recent Test Runs</h3>
                <p className="text-sm text-gray-500 mt-1">
                  View the history of prompt tests for {brandName}
                </p>
              </div>
              <button
                onClick={() => {
                  fetchRuns()
                  fetchAnalytics()
                }}
                className="px-4 py-2 bg-contestra-blue text-white rounded-[50px] hover:opacity-90 text-sm font-mono tracking-[0.02em] transition-all duration-200"
              >
                Refresh Results
              </button>
            </div>
            <div className="p-6">
              <div className="space-y-4">
                {runs.map(run => (
                  <div key={run.id} className="border rounded-lg">
                    <div className="flex items-center justify-between p-4">
                      <div className="flex items-center gap-4">
                        {run.status === 'completed' ? (
                          <CheckCircleIcon className="w-5 h-5 text-green-500" />
                        ) : run.status === 'failed' ? (
                          <XCircleIcon className="w-5 h-5 text-red-500" />
                        ) : (
                          <ExclamationCircleIcon className="w-5 h-5 text-yellow-500" />
                        )}
                        <div>
                          <p className="font-medium">{run.template_name || getTemplateName(run.template_id)}</p>
                          <p className="text-sm text-gray-500">
                            {run.country_code === 'NONE' ? 'Base Model' : run.country_code} • {
                              run.grounding_mode === 'off' || run.grounding_mode === 'none' ? 'Ungrounded' :
                              run.grounding_mode === 'preferred' || run.grounding_mode === 'web' ? 'Grounded (Auto)' :
                              run.grounding_mode === 'required' ? 'Grounded (Required)' :
                              run.grounding_mode
                            } • {run.model_name}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {/* Show warning icon if result had issues */}
                        {expandedResults[run.id] && (expandedResults[run.id].content_filtered || expandedResults[run.id].finish_reason === 'length') && (
                          <ExclamationCircleIcon className="w-5 h-5 text-yellow-500" title="Response had issues - click to view details" />
                        )}
                        <button
                          onClick={() => fetchResult(run.id)}
                          className="px-4 py-2 bg-contestra-blue text-white rounded-[50px] hover:opacity-90 text-sm font-mono tracking-[0.02em] transition-all duration-200"
                        >
                          {expandedResults[run.id] ? 'Hide Response' : 'View Response'}
                        </button>
                        <div className="text-right">
                          <span className={`px-2 py-1 rounded text-xs ${
                            run.status === 'completed' ? 'bg-green-100 text-green-700' :
                            run.status === 'failed' ? 'bg-red-100 text-red-700' :
                            'bg-gray-100 text-gray-700'
                          }`}>
                            {run.status}
                          </span>
                          <p className="text-xs text-gray-500 mt-1">
                            {new Date(run.created_at).toLocaleString()}
                          </p>
                        </div>
                      </div>
                    </div>
                    {(expandedResults[run.id] || loadingResults[run.id]) && (
                      <div className="p-4 bg-gray-50 border-t">
                        {loadingResults[run.id] ? (
                          <p className="text-sm text-gray-500">Loading...</p>
                        ) : expandedResults[run.id] ? (
                          <>
                            <div className="mb-3">
                              <span className="font-semibold text-sm">Prompt:</span>
                              <p className="text-sm mt-1 text-gray-700">{expandedResults[run.id].prompt_text}</p>
                            </div>
                            <div className="mb-3">
                              <span className="font-semibold text-sm">Response:</span>
                              <pre className="text-sm mt-1 whitespace-pre-wrap font-sans text-gray-700 max-h-96 overflow-y-auto">
                                {expandedResults[run.id].model_response}
                              </pre>
                            </div>
                            {/* Safety metadata display */}
                            {(expandedResults[run.id].finish_reason || expandedResults[run.id].content_filtered) && (
                              <div className="mb-3 p-2 bg-yellow-50 border border-yellow-200 rounded">
                                <div className="flex items-start gap-2">
                                  <ExclamationCircleIcon className="w-5 h-5 text-yellow-600 mt-0.5 flex-shrink-0" />
                                  <div className="text-sm">
                                    {expandedResults[run.id].content_filtered ? (
                                      <p className="font-semibold text-yellow-800">Content was filtered</p>
                                    ) : expandedResults[run.id].finish_reason === 'length' ? (
                                      <p className="font-semibold text-yellow-800">Response truncated (token limit reached)</p>
                                    ) : expandedResults[run.id].finish_reason === 'stop' ? (
                                      <p className="text-green-700">Response completed normally</p>
                                    ) : (
                                      <p className="text-yellow-800">Finish reason: {expandedResults[run.id].finish_reason}</p>
                                    )}
                                    {expandedResults[run.id].content_filtered && expandedResults[run.id].finish_reason === 'length' && (
                                      <p className="text-xs text-gray-600 mt-1">
                                        This may indicate token starvation - try increasing max tokens to 4000+
                                      </p>
                                    )}
                                  </div>
                                </div>
                              </div>
                            )}
                            <div className="text-xs text-gray-500 mt-3 pt-3 border-t">
                              Grounding Mode: {
                                run.grounding_mode === 'off' || run.grounding_mode === 'none' ? 'Ungrounded' :
                                run.grounding_mode === 'preferred' || run.grounding_mode === 'web' ? 'Grounded (Auto)' :
                                run.grounding_mode === 'required' ? 'Grounded (Required)' :
                                run.grounding_mode
                              } • 
                              Brand mentioned: {expandedResults[run.id].brand_mentioned ? 'Yes' : 'No'} • 
                              Mention count: {expandedResults[run.id].mention_count} • 
                              Confidence: {(expandedResults[run.id].confidence_score * 100).toFixed(0)}%
                            </div>
                          </>
                        ) : null}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Analytics Tab */}
        {activeTab === 'analytics' && analytics && (
          <>
            {/* Summary Stats */}
            <div className="grid gap-4 md:grid-cols-4 mb-6">
              <div className="bg-white rounded-lg shadow p-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-gray-600">Total Runs</p>
                    <p className="text-2xl font-bold">{analytics.statistics.total_runs}</p>
                    <p className="text-xs text-gray-500">
                      {analytics.statistics.successful_runs} successful
                    </p>
                  </div>
                  <ChartBarIcon className="h-8 w-8 text-gray-400" />
                </div>
              </div>

              <div className="bg-white rounded-lg shadow p-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-gray-600">Mention Rate</p>
                    <p className="text-2xl font-bold">{analytics.statistics.mention_rate.toFixed(1)}%</p>
                    <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
                      <div 
                        className="bg-indigo-600 h-2 rounded-full" 
                        style={{ width: `${analytics.statistics.mention_rate}%` }}
                      />
                    </div>
                  </div>
                  <CheckCircleIcon className="h-8 w-8 text-gray-400" />
                </div>
              </div>

              <div className="bg-white rounded-lg shadow p-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-gray-600">Avg Mentions</p>
                    <p className="text-2xl font-bold">{analytics.statistics.avg_mentions_per_response.toFixed(1)}</p>
                    <p className="text-xs text-gray-500">per response</p>
                  </div>
                  <ExclamationCircleIcon className="h-8 w-8 text-gray-400" />
                </div>
              </div>

              <div className="bg-white rounded-lg shadow p-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-gray-600">Confidence</p>
                    <p className="text-2xl font-bold">{analytics.statistics.avg_confidence.toFixed(0)}%</p>
                    <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
                      <div 
                        className="bg-green-600 h-2 rounded-full" 
                        style={{ width: `${analytics.statistics.avg_confidence}%` }}
                      />
                    </div>
                  </div>
                  <ChartBarIcon className="h-8 w-8 text-gray-400" />
                </div>
              </div>
            </div>

            {/* Comparisons */}
            <div className="grid gap-4 md:grid-cols-2">
              <div className="bg-white rounded-lg shadow">
                <div className="px-6 py-4 border-b">
                  <h3 className="text-lg font-medium">Grounding Mode Comparison</h3>
                </div>
                <div className="p-6 space-y-4">
                  {Object.entries(analytics.grounding_comparison).map(([mode, data]) => (
                    <div key={mode} className="space-y-2">
                      <div className="flex justify-between items-center">
                        <div className="flex items-center gap-2">
                          {mode === 'none' ? (
                            <CircleStackIcon className="w-4 h-4 text-gray-400" />
                          ) : (
                            <GlobeAltIcon className="w-4 h-4 text-gray-400" />
                          )}
                          <span className="text-sm font-medium">
                            {mode === 'none' ? 'Model Knowledge' : 'Grounded (Web Search)'}
                          </span>
                        </div>
                        <span className="text-sm text-gray-500">
                          {data.mention_rate.toFixed(1)}% ({data.run_count} runs)
                        </span>
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-2">
                        <div 
                          className="bg-indigo-600 h-2 rounded-full" 
                          style={{ width: `${data.mention_rate}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="bg-white rounded-lg shadow">
                <div className="px-6 py-4 border-b">
                  <h3 className="text-lg font-medium">Country Comparison</h3>
                </div>
                <div className="p-6 space-y-4">
                  {Object.entries(analytics.country_comparison).map(([country, data]) => (
                    <div key={country} className="space-y-2">
                      <div className="flex justify-between items-center">
                        <div className="flex items-center gap-2">
                          <MapPinIcon className="w-4 h-4 text-gray-400" />
                          <span className="text-sm font-medium">
                            {country === 'NONE' ? 'Base Model' : country}
                          </span>
                        </div>
                        <span className="text-sm text-gray-500">
                          {data.mention_rate.toFixed(1)}% ({data.run_count} runs)
                        </span>
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-2">
                        <div 
                          className="bg-indigo-600 h-2 rounded-full" 
                          style={{ width: `${data.mention_rate}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </>
        )}

        {/* Countries Tab */}
        {activeTab === 'countries' && (
          <Countries />
        )}

        {/* Schedule Tab */}
        {activeTab === 'schedule' && (
          <div className="bg-white rounded-lg shadow">
            <div className="px-6 py-4 border-b">
              <h3 className="text-lg font-medium">Scheduled Tests</h3>
              <p className="text-sm text-gray-500 mt-1">
                Set up automated prompt testing on a regular schedule
              </p>
            </div>
            <div className="p-6">
              <div className="text-center py-8 text-gray-500">
                <ExclamationCircleIcon className="w-12 h-12 mx-auto mb-4 opacity-50" />
                <p>Scheduling feature coming soon</p>
                <p className="text-sm mt-2">
                  You'll be able to run prompt tests daily, weekly, or monthly
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Grounding Test Tab */}
        {activeTab === 'grounding' && (
          <div className="bg-white rounded-lg shadow">
            <div className="px-6 py-4 border-b">
              <h3 className="text-lg font-medium">Grounding Test Grid</h3>
              <p className="text-sm text-gray-500 mt-1">
                Test web search grounding capabilities across GPT-5 and Gemini 2.5 Pro
              </p>
            </div>
            <div className="p-6">
              <GroundingTestGrid />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}