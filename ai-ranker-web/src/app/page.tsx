"use client"

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { TemplatesTabV2 } from "@/components/templates/TemplatesTabV2"
import { RunTab } from "@/components/run/RunTab"
import { BatchRunTab } from "@/components/run/BatchRunTab"
import { ResultsTab } from "@/components/results/ResultsTab"
import { CountriesTab } from "@/components/countries/CountriesTab"
import { SystemStatusTab } from "@/components/system/SystemStatusTab"
import { FileText, Play, Layers, BarChart3, Globe, Server } from "lucide-react"

export default function Home() {
  return (
    <div className="container mx-auto p-6">
      <div className="mb-8">
        <h1 className="text-4xl font-bold mb-2">AI Ranker V2</h1>
        <p className="text-muted-foreground">
          Unified AI adapter system for managing and executing prompt templates across multiple AI providers
        </p>
      </div>

      <Tabs defaultValue="templates" className="w-full">
        <TabsList className="grid w-full grid-cols-6 mb-6">
          <TabsTrigger value="templates" className="flex items-center gap-2">
            <FileText className="h-4 w-4" />
            Templates
          </TabsTrigger>
          <TabsTrigger value="run" className="flex items-center gap-2">
            <Play className="h-4 w-4" />
            Single Run
          </TabsTrigger>
          <TabsTrigger value="batch" className="flex items-center gap-2">
            <Layers className="h-4 w-4" />
            Batch Run
          </TabsTrigger>
          <TabsTrigger value="results" className="flex items-center gap-2">
            <BarChart3 className="h-4 w-4" />
            Results
          </TabsTrigger>
          <TabsTrigger value="countries" className="flex items-center gap-2">
            <Globe className="h-4 w-4" />
            Countries (ALS)
          </TabsTrigger>
          <TabsTrigger value="system" className="flex items-center gap-2">
            <Server className="h-4 w-4" />
            System
          </TabsTrigger>
        </TabsList>

        <TabsContent value="templates" className="mt-0">
          <TemplatesTabV2 />
        </TabsContent>

        <TabsContent value="run" className="mt-0">
          <RunTab />
        </TabsContent>

        <TabsContent value="batch" className="mt-0">
          <BatchRunTab />
        </TabsContent>

        <TabsContent value="results" className="mt-0">
          <ResultsTab />
        </TabsContent>

        <TabsContent value="countries" className="mt-0">
          <CountriesTab />
        </TabsContent>

        <TabsContent value="system" className="mt-0">
          <SystemStatusTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}