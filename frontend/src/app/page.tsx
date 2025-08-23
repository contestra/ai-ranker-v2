'use client'

import { useState, useEffect } from 'react'
import PromptTracking from '@/components/PromptTracking'
import Settings from '@/components/Settings'
import ExperimentalTools from '@/components/ExperimentalTools'
import SystemStatus from '@/components/SystemStatus'
import { brandsApi } from '@/lib/api'
import { BeakerIcon, Cog6ToothIcon } from '@heroicons/react/24/outline'

export default function Home() {
  const [brandInput, setBrandInput] = useState('')
  const [brandName, setBrandName] = useState('')
  const [brandId, setBrandId] = useState<number>(1)
  const [currentView, setCurrentView] = useState<'prompt-tracking' | 'experimental' | 'settings'>('prompt-tracking')

  return (
    <div className="min-h-screen bg-contestra-gray-100">
      <div className="flex h-screen">
        {/* Left Sidebar */}
        <div className="w-64 bg-white shadow-contestra-lg flex flex-col">
          <div className="p-6 border-b border-black/[0.06]">
            <h1 className="text-2xl font-display font-semibold text-contestra-dark">AI RANKER</h1>
            <p className="text-sm text-contestra-text-meta mt-1 font-body">by Contestra</p>
          </div>
          
          <div className="p-4 flex-1 flex flex-col">
            <div className="mb-6">
              <label className="field-label">
                Enter Your Brand
              </label>
              <input
                type="text"
                value={brandInput}
                onChange={(e) => setBrandInput(e.target.value)}
                onKeyPress={async (e) => {
                  if (e.key === 'Enter' && brandInput.trim()) {
                    const trimmedName = brandInput.trim()
                    setBrandName(trimmedName)
                    
                    // Create or update brand in backend
                    try {
                      const brand = await brandsApi.create({
                        name: trimmedName,
                        domain: '',
                        aliases: [],
                        category: [],
                        wikidata_qid: undefined
                      })
                      setBrandId(brand.id)
                      console.log('Brand created/updated:', brand)
                    } catch (error) {
                      console.error('Failed to create brand:', error)
                      // Use default ID if creation fails
                      setBrandId(1)
                    }
                  }
                }}
                placeholder="e.g., Tesla, Apple, Nike"
                className="input-contestra w-full"
              />
            </div>
            
            {brandName && (
              <div className="bg-spectrum-subtle rounded-xl p-4 space-y-2 mb-6 border border-black/[0.03]">
                <p className="field-label">Active Brand</p>
                <div className="flex items-center justify-between">
                  <p className="text-lg font-display font-semibold text-contestra-accent">{brandName}</p>
                  <button
                    onClick={() => {
                      setBrandName('')
                      setBrandInput('')
                      setCurrentView('prompt-tracking') // Reset to main view
                    }}
                    className="text-xs text-contestra-text-meta hover:text-contestra-accent transition-colors"
                  >
                    Change
                  </button>
                </div>
              </div>
            )}
            
            {/* System Status Panel */}
            <div className="mb-6">
              <SystemStatus />
            </div>
            
            {/* Experimental Tools Button */}
            <button
              onClick={() => setCurrentView('experimental')}
              className={`w-full flex items-center gap-3 px-5 py-3 rounded-[50px] transition-all duration-300 font-mono tracking-[0.02em] ${
                currentView === 'experimental'
                  ? 'bg-spectrum text-contestra-dark border border-black/[0.1] shadow-contestra-md'
                  : 'bg-contestra-gray-100 text-contestra-text-meta hover:bg-contestra-gray-200 border border-black/[0.06]'
              }`}
            >
              <BeakerIcon className="w-5 h-5" />
              <span>Experimental Tools</span>
            </button>
            
            {/* Spacer to push footer to bottom */}
            <div className="flex-1" />
            
            {/* Footer */}
            <div className="text-xs text-contestra-text-meta text-center py-4 border-t border-black/[0.06] font-mono tracking-[0.02em]">
              <p>© 2025 Contestra</p>
              <p className="mt-1">Own the First Answer™</p>
            </div>
          </div>
        </div>

        {/* Main Content */}
        <div className="flex-1 flex flex-col">
          {/* Header with Settings - Only show for Settings and Experimental views */}
          {(currentView === 'settings' || currentView === 'experimental') && (
            <div className="bg-white border-b border-black/[0.06] px-8 py-4">
              <div className="flex items-center justify-between">
                <div>
                  <h1 className="text-3xl font-display font-semibold text-contestra-dark">
                    {currentView === 'settings' ? 'Settings' : 'Experimental Tools'}
                  </h1>
                  <p className="text-sm text-contestra-text-meta mt-1 font-body">
                    {currentView === 'settings' 
                      ? 'Configure your AI Ranker settings' 
                      : 'Advanced analysis and monitoring features'}
                  </p>
                </div>
                
                {/* Settings Button (top-right) */}
                <button
                  onClick={() => setCurrentView(currentView === 'settings' ? 'prompt-tracking' : 'settings')}
                  className={`btn-contestra-primary flex items-center gap-2 ${
                    currentView === 'settings'
                      ? ''
                      : 'bg-contestra-gray-100 text-contestra-dark hover:bg-contestra-gray-200'
                  }`}
                >
                  <Cog6ToothIcon className="w-5 h-5" />
                  <span>Settings</span>
                </button>
              </div>
            </div>
          )}
          
          {/* Minimal header for Prompt Tracking - just Settings button */}
          {currentView === 'prompt-tracking' && (
            <div className="bg-white border-b border-black/[0.06] px-8 py-3">
              <div className="flex items-center justify-end">
                <button
                  onClick={() => setCurrentView('settings')}
                  className="btn-contestra-primary flex items-center gap-2"
                >
                  <Cog6ToothIcon className="w-5 h-5" />
                  <span>Settings</span>
                </button>
              </div>
            </div>
          )}

          {/* Content Area */}
          <div className="flex-1 overflow-auto bg-contestra-gray-100">
            {currentView === 'settings' ? (
              <div className="p-6">
                <Settings brandId={brandId} brandName={brandName} />
              </div>
            ) : currentView === 'experimental' ? (
              <ExperimentalTools 
                brandId={brandId} 
                brandName={brandName} 
                onBack={() => setCurrentView('prompt-tracking')}
              />
            ) : brandName ? (
              <div className="p-6">
                <PromptTracking brandId={brandId} brandName={brandName} />
              </div>
            ) : (
              <div className="flex items-center justify-center h-full">
                <div className="text-center">
                  <p className="text-contestra-text-meta mb-4 font-body">Please enter your brand name to get started</p>
                  <p className="text-sm text-contestra-gray-500 font-body">
                    Track how AI models respond to prompts about your brand,<br />
                    products, and services across different countries and contexts.
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}