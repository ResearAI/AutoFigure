"use client"

import { useEffect, useRef, useState, useCallback } from "react"
import { useRouter } from "next/navigation"
import { DrawIoEmbed, type DrawIoEmbedRef } from "react-drawio"
import { AutoFigureProvider, useAutoFigure } from "@/contexts/autofigure-context"
import IterationControlsFloating from "@/components/autofigure/IterationControlsFloating"
import BeautificationDialog from "@/components/autofigure/BeautificationDialog"
import EnhancedImageGallery from "@/components/autofigure/EnhancedImageGallery"
import GenerationOverlay from "@/components/autofigure/GenerationOverlay"
import { extractDiagramXML, sanitizeXmlForDrawio } from "@/lib/utils"
import type { AutoFigureConfig } from "@/lib/autofigure-types"
import {
    Sparkles,
    Image,
    Sun,
    Moon,
    ArrowLeft,
} from "lucide-react"
import "../autofigure-theme.css"

const drawioBaseUrl =
    process.env.NEXT_PUBLIC_DRAWIO_BASE_URL || "https://embed.diagrams.net"

function AutoFigureCanvasContent() {
    const router = useRouter()
    const {
        session,
        isGenerating,
        currentXml,
        updateCurrentXml,
        startGeneration,
        continueIteration,
        finalizeLayout,
        startEnhancement,
        getCurrentIteration,
        error,
        setError,
        clearError,
        config,
        updateConfig,
    } = useAutoFigure()

    const [darkMode, setDarkMode] = useState(false)
    const [isLoaded, setIsLoaded] = useState(false)
    const [drawioUi, setDrawioUi] = useState<"min" | "sketch">("min")
    const [isDrawioReady, setIsDrawioReady] = useState(false)
    const [showBeautification, setShowBeautification] = useState(false)
    const [showGallery, setShowGallery] = useState(false)
    const [currentPreviewImage, setCurrentPreviewImage] = useState<string | undefined>()
    const [isConfigLoaded, setIsConfigLoaded] = useState(false)

    const drawioRef = useRef<DrawIoEmbedRef | null>(null)
    const hasCalledOnLoadRef = useRef(false)
    const hasStartedGenerationRef = useRef(false)
    const pendingConfigRef = useRef<AutoFigureConfig | null>(null)
    const xmlResolverRef = useRef<((result: { success: boolean; xml?: string; error?: string }) => void) | null>(null)

    // Load preferences from localStorage (UI only)
    useEffect(() => {
        const savedDarkMode = localStorage.getItem("autofigure-dark-mode")
        if (savedDarkMode !== null) {
            const isDark = savedDarkMode === "true"
            setDarkMode(isDark)
            document.documentElement.classList.toggle("dark", isDark)
        } else {
            document.documentElement.classList.remove("dark")
        }

        const savedUi = localStorage.getItem("drawio-theme")
        if (savedUi === "min" || savedUi === "sketch") {
            setDrawioUi(savedUi)
        }

        // Load pending config from start page
        const pendingConfigStr = localStorage.getItem('autofigure-pending-config')
        if (pendingConfigStr) {
            try {
                const parsedConfig = JSON.parse(pendingConfigStr) as AutoFigureConfig
                console.log('[AutoFigure Canvas] Loaded pending config, inputText length:', parsedConfig.inputText?.length)
                pendingConfigRef.current = parsedConfig
                // Apply config to context
                updateConfig(parsedConfig)
                // Clear from localStorage
                localStorage.removeItem('autofigure-pending-config')
            } catch (e) {
                console.error('[AutoFigure Canvas] Failed to parse pending config:', e)
            }
        }

        setIsLoaded(true)
        // Mark config as loaded after a micro-task to ensure updateConfig has been called
        setTimeout(() => setIsConfigLoaded(true), 0)
    }, [updateConfig])

    // Auto-start generation when DrawIO is ready and config is loaded
    useEffect(() => {
        // Use ref to prevent multiple starts
        if (hasStartedGenerationRef.current) return
        if (!isDrawioReady || !isConfigLoaded) return
        if (session) return // Already have a session

        // Use the ref value directly instead of relying on state
        const pendingConfig = pendingConfigRef.current
        if (pendingConfig && pendingConfig.inputText && pendingConfig.apiKey) {
            console.log('[AutoFigure Canvas] Auto-starting generation with config from ref')
            hasStartedGenerationRef.current = true
            // Pass full config to avoid closure issues
            startGeneration(pendingConfig.inputText, pendingConfig)
        } else if (config.inputText && config.apiKey) {
            // Fallback to state config if ref is empty
            console.log('[AutoFigure Canvas] Auto-starting generation with config from state')
            hasStartedGenerationRef.current = true
            startGeneration(config.inputText, config)
        } else {
            console.log('[AutoFigure Canvas] No valid config found, not starting generation')
        }
    }, [isDrawioReady, isConfigLoaded, session, config.inputText, config.apiKey, startGeneration])

    // Load XML into draw.io when currentXml changes
    useEffect(() => {
        if (drawioRef.current && currentXml && isDrawioReady) {
            const cleanXml = sanitizeXmlForDrawio(currentXml)
            console.log('[AutoFigure Canvas] Loading XML into DrawIO, length:', cleanXml.length)
            drawioRef.current.load({ xml: cleanXml })
        }
    }, [currentXml, isDrawioReady])

    const onDrawioLoad = useCallback(() => {
        if (hasCalledOnLoadRef.current) return
        hasCalledOnLoadRef.current = true
        console.log('[AutoFigure Canvas] DrawIO loaded')
        setIsDrawioReady(true)
    }, [])

    // Handle draw.io save event - update currentXml when user clicks save button
    const handleDrawioSave = useCallback((data: { xml: string }) => {
        console.log('[AutoFigure] DrawIO save triggered, XML length:', data.xml.length)

        // Extract clean XML from draw.io save data
        try {
            const extractedXml = extractDiagramXML(data.xml)
            updateCurrentXml(extractedXml)
            console.log('[AutoFigure] Updated currentXml from save, length:', extractedXml.length)
        } catch (err) {
            console.error('[AutoFigure] Failed to extract XML from save data:', err)
            // Fallback to original XML
            updateCurrentXml(data.xml)
        }
    }, [updateCurrentXml])

    const resetDrawioReady = useCallback(() => {
        hasCalledOnLoadRef.current = false
        setIsDrawioReady(false)
    }, [])

    const toggleDarkMode = () => {
        const newValue = !darkMode
        setDarkMode(newValue)
        localStorage.setItem("autofigure-dark-mode", String(newValue))
        document.documentElement.classList.toggle("dark", newValue)
        resetDrawioReady()
    }

    // Handle draw.io export callback
    const handleDrawioExport = useCallback((data: any) => {
        console.log("[AutoFigure] handleDrawioExport called, hasResolver:", !!xmlResolverRef.current)
        if (xmlResolverRef.current) {
            try {
                const extractedXml = extractDiagramXML(data.data)
                console.log("[AutoFigure] Successfully extracted XML from draw.io, length:", extractedXml.length)
                xmlResolverRef.current({ success: true, xml: extractedXml })
            } catch (error) {
                console.error("[AutoFigure] Failed to extract XML from export:", error)
                xmlResolverRef.current({ success: false, error: String(error) })
            }
            xmlResolverRef.current = null
        }
    }, [])

    // Get current XML from draw.io canvas
    const getCurrentXmlFromDrawio = useCallback((): Promise<string> => {
        console.log("[AutoFigure] getCurrentXmlFromDrawio called, isDrawioReady:", isDrawioReady)
        return new Promise((resolve, reject) => {
            if (!drawioRef.current || !isDrawioReady) {
                const error = "Draw.io is not ready. Please wait for the editor to load."
                console.error("[AutoFigure]", error)
                reject(new Error(error))
                return
            }

            console.log("[AutoFigure] Requesting export from draw.io...")

            xmlResolverRef.current = (result: { success: boolean; xml?: string; error?: string }) => {
                if (result.success && result.xml) {
                    console.log("[AutoFigure] Export successful, XML length:", result.xml.length)
                    resolve(result.xml)
                } else {
                    const error = result.error || "Failed to extract XML from draw.io"
                    console.error("[AutoFigure] Export failed:", error)
                    reject(new Error(error))
                }
            }

            drawioRef.current.exportDiagram({ format: "xmlsvg" })

            setTimeout(() => {
                if (xmlResolverRef.current) {
                    console.error("[AutoFigure] Export timeout (5s)")
                    xmlResolverRef.current = null
                    reject(new Error("Draw.io export timed out. Please try again."))
                }
            }, 5000)
        })
    }, [isDrawioReady])

    const handleContinue = async (feedback?: string, score?: number) => {
        try {
            const editedXml = await getCurrentXmlFromDrawio()
            console.log("[AutoFigure] Continue with edited XML from canvas, length:", editedXml.length)
            await continueIteration(editedXml, feedback, score)
        } catch (err: any) {
            console.error("[AutoFigure] Continue failed:", err)
            setError(err.message || "Failed to get diagram from canvas. Please try again.")
        }
    }

    const handleFinalize = async () => {
        try {
            const finalXml = await getCurrentXmlFromDrawio()
            console.log("[AutoFigure] Finalize with edited XML from canvas, length:", finalXml.length)

            const pngBase64 = await finalizeLayout(finalXml)

            if (pngBase64) {
                setCurrentPreviewImage(`data:image/png;base64,${pngBase64}`)
                console.log("[AutoFigure] Set preview image from finalized XML")
            } else {
                const currentIteration = getCurrentIteration()
                if (currentIteration?.pngBase64) {
                    setCurrentPreviewImage(`data:image/png;base64,${currentIteration.pngBase64}`)
                    console.log("[AutoFigure] Fallback to current iteration PNG")
                }
            }

            setShowBeautification(true)
        } catch (err: any) {
            console.error("[AutoFigure] Finalize failed:", err)
            setError(err.message || "Failed to get diagram from canvas. Please try again.")
        }
    }

    const handleStartBeautification = async () => {
        setShowBeautification(false)
        setShowGallery(true)

        await startEnhancement((success, images) => {
            if (success && images.length > 0) {
                setShowGallery(true)
            }
            console.log(`[AutoFigure] Enhancement completed: success=${success}, images=${images.length}`)
        })
    }

    const loadIteration = (xml: string) => {
        if (drawioRef.current && isDrawioReady) {
            drawioRef.current.load({ xml: sanitizeXmlForDrawio(xml) })
        }
    }

    const handleImageGenerated = async (imageBase64: string) => {
        console.log('[AutoFigure] handleImageGenerated called, base64 length:', imageBase64?.length)

        if (!drawioRef.current || !isDrawioReady) {
            console.error('[AutoFigure] DrawIO not ready for image insertion')
            setError('Draw.io is not ready. Please wait for the editor to load.')
            return
        }

        console.log('[AutoFigure] Inserting generated image into canvas')

        try {
            // CRITICAL: First get the latest XML from draw.io canvas
            // This ensures we capture any user modifications (like moved images)
            // before inserting the new image
            console.log('[AutoFigure] Getting latest XML from draw.io canvas before image insertion...')
            let latestXml: string
            try {
                latestXml = await getCurrentXmlFromDrawio()
                console.log('[AutoFigure] Got latest XML from canvas, length:', latestXml.length)
                // Update context state to keep it in sync with canvas
                updateCurrentXml(latestXml)
            } catch (err) {
                console.warn('[AutoFigure] Failed to get XML from canvas, falling back to context XML:', err)
                // Fallback to context XML if export fails
                if (!currentXml) {
                    setError('No diagram XML available. Please wait for the diagram to load.')
                    return
                }
                latestXml = currentXml
            }

            // Create data URL and encode semicolons for draw.io style format
            // In draw.io's style attribute, semicolons separate properties
            // So we need to encode the semicolon in "data:image/png;base64" to prevent it from being parsed as a separator
            const dataUrl = `data:image/png;base64,${imageBase64}`
            // Encode semicolons as %3B for use in draw.io style attribute
            const encodedDataUrl = dataUrl.replace(/;/g, '%3B')

            console.log('[AutoFigure] Created encoded data URL, length:', encodedDataUrl.length)

            // Generate a unique cell ID
            const cellId = `img-${Date.now()}`

            console.log('[AutoFigure] Using latest canvas XML, length:', latestXml.length)

            // Modify the XML to add the image (use latestXml which contains user's modifications)
            const modifiedXml = insertImageIntoXml(latestXml, encodedDataUrl, cellId)

            if (!modifiedXml) {
                setError('Failed to add image to diagram XML')
                return
            }

            console.log('[AutoFigure] Modified XML created, length:', modifiedXml.length)

            // Update context state FIRST to keep it in sync
            // This is critical because the useEffect monitoring currentXml will use this value
            updateCurrentXml(modifiedXml)
            console.log('[AutoFigure] Updated currentXml state with new image')

            // Load the modified XML into draw.io
            drawioRef.current.load({ xml: modifiedXml })
            console.log('[AutoFigure] Image insertion completed successfully')

        } catch (err: any) {
            console.error('[AutoFigure] Failed to insert image:', err)
            setError(err.message || 'Failed to insert image into canvas')
        }
    }

    // Helper function to insert an image into the mxGraph XML
    const insertImageIntoXml = (xml: string, imageUrl: string, cellId: string): string | null => {
        try {
            console.log('[AutoFigure] insertImageIntoXml called, XML length:', xml.length)

            // Parse the XML
            const parser = new DOMParser()
            const doc = parser.parseFromString(xml, 'text/xml')

            // Check for parse errors
            const parseError = doc.querySelector('parsererror')
            if (parseError) {
                console.error('[AutoFigure] XML parse error:', parseError.textContent)
                return null
            }

            // Find the root element - could be mxGraphModel directly or nested
            let mxGraphModel = doc.querySelector('mxGraphModel')

            // If not found, try to find it as document element
            if (!mxGraphModel && doc.documentElement.tagName === 'mxGraphModel') {
                mxGraphModel = doc.documentElement
            }

            if (!mxGraphModel) {
                console.error('[AutoFigure] Could not find mxGraphModel in XML. Document element:', doc.documentElement?.tagName)
                return null
            }

            // Find the root cell
            const root = mxGraphModel.querySelector('root')
            if (!root) {
                console.error('[AutoFigure] Could not find root in mxGraphModel')
                return null
            }

            console.log('[AutoFigure] Found mxGraphModel and root, adding image cell')

            // Create a new mxCell for the image
            // The imageUrl should already have semicolons encoded as %3B
            const mxCell = doc.createElement('mxCell')
            mxCell.setAttribute('id', cellId)
            mxCell.setAttribute('value', '')
            mxCell.setAttribute('style', `shape=image;image=${imageUrl};imageAspect=0;aspect=fixed;verticalLabelPosition=bottom;verticalAlign=top;`)
            mxCell.setAttribute('vertex', '1')
            mxCell.setAttribute('parent', '1')

            // Create geometry for the cell
            const mxGeometry = doc.createElement('mxGeometry')
            mxGeometry.setAttribute('x', '50')
            mxGeometry.setAttribute('y', '50')
            mxGeometry.setAttribute('width', '150')
            mxGeometry.setAttribute('height', '150')
            mxGeometry.setAttribute('as', 'geometry')

            mxCell.appendChild(mxGeometry)
            root.appendChild(mxCell)

            // Serialize back to string
            const serializer = new XMLSerializer()
            const modifiedXml = serializer.serializeToString(doc)

            console.log('[AutoFigure] Modified XML length:', modifiedXml.length, 'Added cell ID:', cellId)
            return modifiedXml
        } catch (err) {
            console.error('[AutoFigure] Error inserting image into XML:', err)
            return null
        }
    }

    const handleBack = () => {
        router.push('/autofigure')
    }

    return (
        <div className="autofigure-page">
            {/* Header */}
            <header className="af-header">
                <div className="af-header-left">
                    <button
                        className="af-back-btn"
                        onClick={handleBack}
                        title="Back to Start"
                    >
                        <ArrowLeft className="w-4 h-4" />
                        <span className="hidden sm:inline">Back</span>
                    </button>
                    <div className="af-logo">
                        <div className="af-logo-icon">
                            <Sparkles className="w-4 h-4 text-white" />
                        </div>
                        <span className="af-logo-text">AutoFigure</span>
                    </div>
                </div>

                <div className="af-header-right">
                    {session?.status === "completed" && (
                        <button
                            className="af-gallery-btn"
                            onClick={() => setShowGallery(true)}
                        >
                            <Image className="w-4 h-4" />
                            <span className="hidden sm:inline">View Gallery</span>
                        </button>
                    )}

                    <button
                        className="af-icon-btn"
                        onClick={toggleDarkMode}
                        title={darkMode ? "Light Mode" : "Dark Mode"}
                    >
                        {darkMode ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
                    </button>

                    <a
                        href="https://westlakenlp.com/"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="af-external-link"
                    >
                        <img src="/westlakenlp.png" alt="WestlakeNLP" className="af-external-link-icon" />
                        <span className="hidden sm:inline">WestlakeNLP</span>
                    </a>

                    <a
                        href="https://github.com/ResearAI"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="af-external-link"
                    >
                        <img src="/github.png" alt="GitHub" className="af-external-link-icon" />
                        <span className="hidden sm:inline">AutoFigure</span>
                    </a>
                </div>
            </header>

            {/* Error Banner */}
            {error && (
                <div className="af-error-banner">
                    <span>{error}</span>
                    <button className="af-error-dismiss" onClick={clearError}>
                        Dismiss
                    </button>
                </div>
            )}

            {/* Canvas Area - Use original CSS structure */}
            <div className="af-canvas-wrapper">
                <div className="af-canvas-container">
                    {isLoaded ? (
                        <DrawIoEmbed
                            key={`${drawioUi}-${darkMode}`}
                            ref={drawioRef}
                            onLoad={onDrawioLoad}
                            onExport={handleDrawioExport}
                            onSave={handleDrawioSave}
                            baseUrl={drawioBaseUrl}
                            urlParameters={{
                                ui: drawioUi,
                                spin: true,
                                libraries: false,
                                saveAndExit: false,
                                noExitBtn: true,
                                dark: darkMode,
                            }}
                        />
                    ) : (
                        <div className="h-full w-full flex items-center justify-center bg-gray-50">
                            <div className="animate-spin h-8 w-8 border-4 border-sky-500 border-t-transparent rounded-full" />
                        </div>
                    )}
                </div>

                {/* Floating Iteration Controls */}
                {session && !isGenerating && (
                    <IterationControlsFloating
                        onContinue={handleContinue}
                        onFinalize={handleFinalize}
                        onLoadIteration={loadIteration}
                        onImageGenerated={handleImageGenerated}
                    />
                )}
            </div>

            {/* Generation Overlay */}
            <GenerationOverlay />

            {/* Beautification Dialog */}
            <BeautificationDialog
                isOpen={showBeautification}
                onClose={() => setShowBeautification(false)}
                onStart={handleStartBeautification}
                previewImage={currentPreviewImage}
            />

            {/* Enhanced Image Gallery */}
            <EnhancedImageGallery
                isOpen={showGallery}
                onClose={() => setShowGallery(false)}
            />
        </div>
    )
}

export default function AutoFigureCanvasPage() {
    return (
        <AutoFigureProvider>
            <AutoFigureCanvasContent />
        </AutoFigureProvider>
    )
}
