"use client"

import type React from "react"
import { createContext, useContext, useState, useCallback, useRef } from "react"
import type {
    AutoFigureConfig,
    AutoFigureSession,
    IterationResult,
    EnhancedImage,
    SessionStatus,
    EvaluationResult,
} from "@/lib/autofigure-types"
import { DEFAULT_CONFIG } from "@/lib/autofigure-types"
import { wrapWithMxFile } from "@/lib/utils"

interface AutoFigureContextType {
    // Configuration
    config: AutoFigureConfig
    updateConfig: (updates: Partial<AutoFigureConfig>) => void
    resetConfig: () => void

    // Session state
    session: AutoFigureSession | null
    isGenerating: boolean
    currentXml: string
    updateCurrentXml: (xml: string) => void

    // Actions
    startGeneration: (inputText: string, configOverride?: AutoFigureConfig) => Promise<void>
    continueIteration: (editedXml: string, feedback?: string, score?: number) => Promise<void>
    finalizeLayout: (finalXml: string) => Promise<string | null>
    startEnhancement: (onComplete?: (success: boolean, images: EnhancedImage[]) => void) => Promise<void>
    cancelGeneration: () => void

    // Iteration navigation
    currentIterationIndex: number
    setCurrentIterationIndex: (index: number) => void
    getCurrentIteration: () => IterationResult | null

    // Enhancement
    enhancementProgress: number
    enhancedImages: EnhancedImage[]

    // Error handling
    error: string | null
    setError: (error: string | null) => void
    clearError: () => void
}

const AutoFigureContext = createContext<AutoFigureContextType | undefined>(undefined)

async function getResponseError(response: Response, fallback: string): Promise<string> {
    const data = await response.json().catch(() => null)
    if (data?.error) {
        return data.error
    }
    if (data?.message) {
        return data.message
    }
    return `${fallback}: ${response.statusText}`
}

export function AutoFigureProvider({ children }: { children: React.ReactNode }) {
    // Configuration state
    const [config, setConfig] = useState<AutoFigureConfig>(DEFAULT_CONFIG)

    // Session state
    const [session, setSession] = useState<AutoFigureSession | null>(null)
    const [isGenerating, setIsGenerating] = useState(false)
    const [currentXml, setCurrentXml] = useState("")
    const [currentIterationIndex, setCurrentIterationIndex] = useState(0)

    // Enhancement state
    const [enhancementProgress, setEnhancementProgress] = useState(0)
    const [enhancedImages, setEnhancedImages] = useState<EnhancedImage[]>([])

    // Error state
    const [error, setError] = useState<string | null>(null)

    // Refs for cancellation
    const abortControllerRef = useRef<AbortController | null>(null)

    const getBackendUrl = () => {
        return process.env.NEXT_PUBLIC_AUTOFIGURE_BACKEND_URL ||
               process.env.NEXT_PUBLIC_BACKEND_URL ||
               "http://localhost:8796"
    }

    const getAuthToken = () => {
        return localStorage.getItem("autofigure-token") || ""
    }

    const updateConfig = useCallback((updates: Partial<AutoFigureConfig>) => {
        setConfig(prev => ({ ...prev, ...updates }))
    }, [])

    const resetConfig = useCallback(() => {
        setConfig(DEFAULT_CONFIG)
    }, [])

    const clearError = useCallback(() => {
        setError(null)
    }, [])

    const startGeneration = useCallback(async (inputText: string, configOverride?: AutoFigureConfig) => {
        // Use configOverride if provided, otherwise use current config state
        const effectiveConfig = configOverride || config

        setIsGenerating(true)
        setError(null)
        abortControllerRef.current = new AbortController()

        console.log("[AutoFigure Context] startGeneration called, inputText length:", inputText.length)
        console.log("[AutoFigure Context] Using config with apiKey:", effectiveConfig.apiKey ? "present" : "missing")

        try {
            const response = await fetch(`${getBackendUrl()}/api/autofigure/session/create`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${getAuthToken()}`,
                },
                body: JSON.stringify({
                    config: { ...effectiveConfig, inputText },
                    input_content: inputText,
                    input_type: "text",
                }),
                signal: abortControllerRef.current.signal,
            })

            if (!response.ok) {
                throw new Error(await getResponseError(response, "Failed to create session"))
            }

            const data = await response.json()

            // Start initial generation
            const startResponse = await fetch(
                `${getBackendUrl()}/api/autofigure/session/${data.session_id}/start`,
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Authorization": `Bearer ${getAuthToken()}`,
                    },
                    signal: abortControllerRef.current.signal,
                }
            )

            if (!startResponse.ok) {
                throw new Error(await getResponseError(startResponse, "Failed to start generation"))
            }

            const startData = await startResponse.json()

            const newSession: AutoFigureSession = {
                sessionId: data.session_id,
                status: startData.status as SessionStatus,
                config: { ...effectiveConfig, inputText },
                currentIteration: startData.iteration,
                iterations: [
                    {
                        iteration: startData.iteration,
                        xml: startData.xml,
                        pngBase64: startData.png_base64,
                        evaluation: startData.evaluation,  // Include initial evaluation
                        timestamp: new Date().toISOString(),
                    },
                ],
            }

            setSession(newSession)
            setCurrentXml(startData.xml)
            setCurrentIterationIndex(0)

            console.log("[AutoFigure] Initial evaluation received:", startData.evaluation ? "yes" : "no")
        } catch (err: any) {
            if (err.name !== "AbortError") {
                setError(err.message || "Failed to start generation")
            }
        } finally {
            setIsGenerating(false)
        }
    }, [config])

    const continueIteration = useCallback(async (
        editedXml: string,
        feedback?: string,
        score?: number
    ) => {
        if (!session) return

        setIsGenerating(true)
        setError(null)
        abortControllerRef.current = new AbortController()

        try {
            // Wrap XML with <mxfile> structure before sending to backend
            // Backend validation requires XML to start with <mxfile>
            const wrappedXml = wrapWithMxFile(editedXml)
            console.log("[AutoFigure] Wrapped XML for backend, original starts with:", editedXml.substring(0, 30), "wrapped starts with:", wrappedXml.substring(0, 30))

            const response = await fetch(
                `${getBackendUrl()}/api/autofigure/session/${session.sessionId}/continue`,
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Authorization": `Bearer ${getAuthToken()}`,
                    },
                    body: JSON.stringify({
                        current_xml: wrappedXml,
                        human_feedback: feedback,
                        human_score: score,
                    }),
                    signal: abortControllerRef.current.signal,
                }
            )

            if (!response.ok) {
                throw new Error(`Failed to continue iteration: ${response.statusText}`)
            }

            const data = await response.json()

            const newIteration: IterationResult = {
                iteration: data.iteration,
                xml: data.xml,
                pngBase64: data.png_base64,
                evaluation: data.evaluation as EvaluationResult,
                humanFeedback: feedback,
                humanScore: score,
                timestamp: new Date().toISOString(),
            }

            setSession(prev => {
                if (!prev) return prev
                return {
                    ...prev,
                    status: data.status as SessionStatus,
                    currentIteration: data.iteration,
                    iterations: [...prev.iterations, newIteration],
                }
            })

            setCurrentXml(data.xml)
            setCurrentIterationIndex(prev => prev + 1)
        } catch (err: any) {
            if (err.name !== "AbortError") {
                setError(err.message || "Failed to continue iteration")
            }
        } finally {
            setIsGenerating(false)
        }
    }, [session])

    const finalizeLayout = useCallback(async (finalXml: string): Promise<string | null> => {
        if (!session) return null

        setIsGenerating(true)
        setError(null)

        try {
            // Wrap XML with <mxfile> structure before sending to backend
            const wrappedXml = wrapWithMxFile(finalXml)
            console.log("[AutoFigure] Wrapped final XML for backend")

            const response = await fetch(
                `${getBackendUrl()}/api/autofigure/session/${session.sessionId}/finalize`,
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Authorization": `Bearer ${getAuthToken()}`,
                    },
                    body: JSON.stringify({ final_xml: wrappedXml }),
                }
            )

            if (!response.ok) {
                throw new Error(`Failed to finalize layout: ${response.statusText}`)
            }

            const data = await response.json()

            setSession(prev => {
                if (!prev) return prev
                return {
                    ...prev,
                    status: "waiting_feedback" as SessionStatus,
                    finalXml: finalXml,
                    finalPngBase64: data.png_base64,  // Store the preview of user-edited XML
                }
            })

            // Return the PNG of user-edited XML for immediate use
            return data.png_base64 || null
        } catch (err: any) {
            setError(err.message || "Failed to finalize layout")
            return null
        } finally {
            setIsGenerating(false)
        }
    }, [session])

    const startEnhancement = useCallback(async (
        onComplete?: (success: boolean, images: EnhancedImage[]) => void
    ) => {
        if (!session) return

        setIsGenerating(true)
        setError(null)
        setEnhancementProgress(0)
        setEnhancedImages([])

        try {
            const response = await fetch(
                `${getBackendUrl()}/api/autofigure/session/${session.sessionId}/enhance`,
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Authorization": `Bearer ${getAuthToken()}`,
                    },
                    body: JSON.stringify({
                        mode: config.enhancementMode,
                        art_style: config.artStyle,
                        variant_count: config.enhancementCount,
                        // User-provided LLM config for code2prompt
                        enhancement_llm_provider: config.enhancementLlmProvider,
                        enhancement_llm_protocol: config.enhancementLlmProtocol,
                        enhancement_llm_api_key: config.enhancementLlmApiKey,
                        enhancement_llm_base_url: config.enhancementLlmBaseUrl,
                        enhancement_llm_model: config.enhancementLlmModel,
                        // User-provided image generation config
                        image_gen_provider: config.imageGenProvider,
                        image_gen_protocol: config.imageGenProtocol,
                        image_gen_api_key: config.imageGenApiKey,
                        image_gen_base_url: config.imageGenBaseUrl,
                        image_gen_model: config.imageGenModel,
                    }),
                }
            )

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}))
                throw new Error(errorData.error || `Failed to start enhancement: ${response.statusText}`)
            }

            // Poll for enhancement status
            let pollCount = 0
            const maxPolls = 300 // 10 minutes max (2s * 300)

            const pollInterval = setInterval(async () => {
                pollCount++

                // Safety check for max polling duration
                if (pollCount > maxPolls) {
                    clearInterval(pollInterval)
                    setIsGenerating(false)
                    setError("Enhancement timed out after 10 minutes")
                    onComplete?.(false, [])
                    return
                }

                try {
                    // Add timeout for large responses (images can be several MB)
                    const controller = new AbortController()
                    const timeoutId = setTimeout(() => controller.abort(), 60000) // 60s timeout

                    const statusResponse = await fetch(
                        `${getBackendUrl()}/api/autofigure/session/${session.sessionId}/enhance/status`,
                        {
                            headers: {
                                "Authorization": `Bearer ${getAuthToken()}`,
                            },
                            signal: controller.signal,
                        }
                    )

                    clearTimeout(timeoutId)

                    if (statusResponse.ok) {
                        const statusData = await statusResponse.json()
                        setEnhancementProgress(statusData.progress)
                        setEnhancedImages(statusData.images || [])

                        if (statusData.status === "completed" || statusData.status === "failed") {
                            clearInterval(pollInterval)
                            setIsGenerating(false)

                            const finalImages = statusData.images || []
                            const hasSuccessfulImages = finalImages.some(
                                (img: EnhancedImage) => img.status === "completed" && img.pngBase64
                            )

                            if (statusData.status === "completed") {
                                setSession(prev => {
                                    if (!prev) return prev
                                    return {
                                        ...prev,
                                        status: "completed" as SessionStatus,
                                        enhancedImages: finalImages,
                                    }
                                })
                            } else {
                                // Enhancement failed
                                setError("Enhancement failed. Please check your API keys and try again.")
                            }

                            // Call completion callback
                            onComplete?.(hasSuccessfulImages, finalImages)
                        }
                    } else {
                        console.error("Error polling enhancement status:", statusResponse.statusText)
                    }
                } catch (err: any) {
                    // Don't show error for transient network issues during polling
                    // Only log to console, the polling will retry automatically
                    if (err.name === 'AbortError') {
                        console.warn("Enhancement status poll timed out, will retry...")
                    } else {
                        console.error("Error polling enhancement status:", err)
                    }
                    // Note: Don't stop polling on transient errors, it will retry in 2s
                }
            }, 2000)

        } catch (err: any) {
            setError(err.message || "Failed to start enhancement")
            setIsGenerating(false)
            onComplete?.(false, [])
        }
    }, [session, config])

    const cancelGeneration = useCallback(() => {
        if (abortControllerRef.current) {
            abortControllerRef.current.abort()
        }
        setIsGenerating(false)
    }, [])

    const getCurrentIteration = useCallback(() => {
        if (!session || session.iterations.length === 0) return null
        return session.iterations[currentIterationIndex] || null
    }, [session, currentIterationIndex])

    return (
        <AutoFigureContext.Provider
            value={{
                config,
                updateConfig,
                resetConfig,
                session,
                isGenerating,
                currentXml,
                updateCurrentXml: setCurrentXml,
                startGeneration,
                continueIteration,
                finalizeLayout,
                startEnhancement,
                cancelGeneration,
                currentIterationIndex,
                setCurrentIterationIndex,
                getCurrentIteration,
                enhancementProgress,
                enhancedImages,
                error,
                setError,
                clearError,
            }}
        >
            {children}
        </AutoFigureContext.Provider>
    )
}

export function useAutoFigure() {
    const context = useContext(AutoFigureContext)
    if (context === undefined) {
        throw new Error("useAutoFigure must be used within an AutoFigureProvider")
    }
    return context
}
