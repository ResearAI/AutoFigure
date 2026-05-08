"use client"

import { useState, useRef, useEffect } from "react"
import {
    ChevronLeft,
    ChevronRight,
    MessageSquare,
    Play,
    Check,
    X,
    Image,
    Settings2,
    ArrowRight,
    Loader2,
    Sparkles,
} from "lucide-react"
import { useAutoFigure } from "@/contexts/autofigure-context"
import ImageGenSettings from "./ImageGenSettings"
import { type ApiProtocol, type LLMProvider } from "@/lib/autofigure-types"

interface IterationControlsFloatingProps {
    onContinue: (feedback?: string, score?: number) => void
    onFinalize: () => void
    onLoadIteration: (xml: string) => void
    onImageGenerated?: (imageBase64: string) => void
}

type BottomBarMode = 'iteration' | 'generation'
type GenerationState = 'idle' | 'generating'

export default function IterationControlsFloating({
    onContinue,
    onFinalize,
    onLoadIteration,
    onImageGenerated,
}: IterationControlsFloatingProps) {
    const {
        session,
        isGenerating,
        currentIterationIndex,
        setCurrentIterationIndex,
    } = useAutoFigure()

    // Mode state
    const [mode, setMode] = useState<BottomBarMode>('iteration')
    const [generationState, setGenerationState] = useState<GenerationState>('idle')

    // Iteration mode state
    const [showFeedback, setShowFeedback] = useState(false)
    const [feedback, setFeedback] = useState("")
    const [score, setScore] = useState<number | undefined>(undefined)

    // Generation mode state
    const [prompt, setPrompt] = useState("")
    const [showSettings, setShowSettings] = useState(false)
    const [imageGenConfig, setImageGenConfig] = useState<{
        provider: LLMProvider
        protocol: ApiProtocol
        apiKey: string
        model: string
        baseUrl: string
    }>({
        provider: 'bianxie',
        protocol: 'openai-compatible',
        apiKey: "",
        model: "",
        baseUrl: "",
    })

    const inputRef = useRef<HTMLInputElement>(null)

    // Load saved config from localStorage (excluding apiKey for security)
    useEffect(() => {
        const savedConfig = localStorage.getItem('autofigure-imagegen-config')
        if (savedConfig) {
            try {
                const parsed = JSON.parse(savedConfig)
                // NEVER load apiKey from localStorage for security
                // This prevents accidentally saved auto-filled apiKeys from being displayed
                const { apiKey, ...safeConfig } = parsed
                setImageGenConfig(prev => ({
                    ...prev,
                    ...safeConfig,
                    apiKey: ""  // Always start with empty apiKey
                }))
            } catch (e) {
                console.error('[ImageGen] Failed to load saved config:', e)
            }
        }
    }, [])

    // Focus input when switching to generation mode
    useEffect(() => {
        if (mode === 'generation' && inputRef.current) {
            inputRef.current.focus()
        }
    }, [mode])

    if (!session) return null

    const totalIterations = session.iterations.length

    const handlePrevious = () => {
        if (currentIterationIndex > 0) {
            const newIndex = currentIterationIndex - 1
            setCurrentIterationIndex(newIndex)
            const iteration = session.iterations[newIndex]
            if (iteration) {
                onLoadIteration(iteration.xml)
            }
        }
    }

    const handleNext = () => {
        if (currentIterationIndex < totalIterations - 1) {
            const newIndex = currentIterationIndex + 1
            setCurrentIterationIndex(newIndex)
            const iteration = session.iterations[newIndex]
            if (iteration) {
                onLoadIteration(iteration.xml)
            }
        }
    }

    const handleContinueWithFeedback = async () => {
        await onContinue(feedback || undefined, score)
        setFeedback("")
        setScore(undefined)
        setShowFeedback(false)
    }

    const getBackendUrl = () => {
        return process.env.NEXT_PUBLIC_AUTOFIGURE_BACKEND_URL ||
               process.env.NEXT_PUBLIC_BACKEND_URL ||
               "http://localhost:8796"
    }

    const getAuthToken = () => {
        return localStorage.getItem("autofigure-token") || ""
    }

    const handleGenerateImage = async () => {
        if (!prompt.trim()) return
        // Require all configuration fields
        if (!imageGenConfig.apiKey || !imageGenConfig.model || !imageGenConfig.baseUrl) {
            setShowSettings(true)
            return
        }

        setGenerationState('generating')

        try {
            // Create AbortController with 5 minute timeout (image generation can take 1-3 minutes)
            const controller = new AbortController()
            const timeoutId = setTimeout(() => controller.abort(), 300000)

            const response = await fetch(`${getBackendUrl()}/api/autofigure/generate-image`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${getAuthToken()}`,
                },
                body: JSON.stringify({
                    prompt: prompt.trim(),
                    provider: imageGenConfig.provider,
                    protocol: imageGenConfig.protocol,
                    api_key: imageGenConfig.apiKey,
                    model: imageGenConfig.model,
                    base_url: imageGenConfig.baseUrl,
                }),
                signal: controller.signal,
            })

            clearTimeout(timeoutId)

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}))
                throw new Error(errorData.error || `Request failed: ${response.status}`)
            }

            const data = await response.json()

            if (data.image_base64) {
                console.log('[ImageGen] Image generated successfully, base64 length:', data.image_base64.length)
                // Call the callback to add image to canvas
                if (onImageGenerated) {
                    console.log('[ImageGen] Calling onImageGenerated callback')
                    onImageGenerated(data.image_base64)
                    console.log('[ImageGen] onImageGenerated callback completed')
                } else {
                    console.warn('[ImageGen] onImageGenerated callback is not defined!')
                }
                // Clear prompt after successful generation
                setPrompt("")
            } else {
                console.error('[ImageGen] No image_base64 in response:', data)
                throw new Error('No image in response')
            }
        } catch (err: any) {
            console.error('[ImageGen] Generation failed:', err)
            alert(`Image generation failed: ${err.message}`)
        } finally {
            setGenerationState('idle')
        }
    }

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            handleGenerateImage()
        } else if (e.key === 'Escape') {
            setMode('iteration')
        }
    }

    const handleSaveSettings = (config: typeof imageGenConfig) => {
        setImageGenConfig(config)
        // Save config WITHOUT apiKey for security
        // This prevents sensitive API keys from being stored in localStorage
        const { apiKey, ...configWithoutApiKey } = config
        localStorage.setItem('autofigure-imagegen-config', JSON.stringify(configWithoutApiKey))
        setShowSettings(false)
    }

    // Render Generation Mode
    if (mode === 'generation') {
        return (
            <>
                <div className="af-iteration-controls af-generation-mode">
                    {/* Back Button */}
                    <button
                        className="af-icon-btn"
                        onClick={() => setMode('iteration')}
                        title="Back to iteration controls"
                        style={{ width: '36px', height: '36px' }}
                    >
                        <ChevronLeft className="w-5 h-5" />
                    </button>

                    {/* Settings Button */}
                    <button
                        className="af-icon-btn"
                        onClick={() => setShowSettings(true)}
                        title="Image generation settings"
                        style={{
                            width: '36px',
                            height: '36px',
                            borderColor: (!imageGenConfig.apiKey || !imageGenConfig.model || !imageGenConfig.baseUrl) ? 'var(--af-accent-primary)' : undefined,
                            color: (!imageGenConfig.apiKey || !imageGenConfig.model || !imageGenConfig.baseUrl) ? 'var(--af-accent-primary)' : undefined,
                        }}
                    >
                        <Settings2 className="w-5 h-5" />
                    </button>

                    {/* Input Field */}
                    <div className="af-gen-input-wrapper">
                        <input
                            ref={inputRef}
                            type="text"
                            className="af-gen-input"
                            value={prompt}
                            onChange={e => setPrompt(e.target.value)}
                            onKeyDown={handleKeyDown}
                            placeholder="Describe the image to generate..."
                            disabled={generationState === 'generating'}
                        />
                    </div>

                    {/* Send Button */}
                    <button
                        className="af-gen-send-btn"
                        onClick={handleGenerateImage}
                        disabled={generationState === 'generating' || !prompt.trim()}
                        title="Generate image (Enter)"
                    >
                        {generationState === 'generating' ? (
                            <Loader2 className="w-5 h-5 animate-spin" />
                        ) : (
                            <ArrowRight className="w-5 h-5" />
                        )}
                    </button>
                </div>

                {/* Settings Modal */}
                <ImageGenSettings
                    isOpen={showSettings}
                    onClose={() => setShowSettings(false)}
                    config={imageGenConfig}
                    onSave={handleSaveSettings}
                />
            </>
        )
    }

    // Render Iteration Mode (default)
    return (
        <>
            {/* Main Floating Controls */}
            <div className="af-iteration-controls">
                {/* Iteration Badge */}
                <div className="af-iteration-info">
                    <span className="af-iteration-badge">
                        Iteration {currentIterationIndex + 1}
                    </span>
                </div>

                {/* Progress Dots */}
                <div className="af-iteration-dots">
                    {session.iterations.map((_, i) => (
                        <button
                            key={i}
                            className={`af-iteration-dot completed ${i === currentIterationIndex ? 'current' : ''}`}
                            onClick={() => {
                                setCurrentIterationIndex(i)
                                const iteration = session.iterations[i]
                                if (iteration) {
                                    onLoadIteration(iteration.xml)
                                }
                            }}
                            title={`Load iteration ${i + 1} from history`}
                            aria-label={`Load iteration ${i + 1} from history`}
                        />
                    ))}
                </div>

                {/* Navigation */}
                <div className="flex items-center gap-1">
                    <button
                        className="af-icon-btn"
                        onClick={handlePrevious}
                        disabled={currentIterationIndex === 0}
                        title="Load the previous generated iteration"
                        aria-label="Load the previous generated iteration"
                        style={{ width: '32px', height: '32px', opacity: currentIterationIndex === 0 ? 0.5 : 1 }}
                    >
                        <ChevronLeft className="w-4 h-4" />
                    </button>
                    <button
                        className="af-icon-btn"
                        onClick={handleNext}
                        disabled={currentIterationIndex >= totalIterations - 1}
                        title="Load the next generated iteration"
                        aria-label="Load the next generated iteration"
                        style={{ width: '32px', height: '32px', opacity: currentIterationIndex >= totalIterations - 1 ? 0.5 : 1 }}
                    >
                        <ChevronRight className="w-4 h-4" />
                    </button>
                </div>

                {/* Actions */}
                <div className="af-iteration-actions">
                    <button
                        className={`af-btn-secondary ${showFeedback ? 'active' : ''}`}
                        onClick={() => setShowFeedback(!showFeedback)}
                        title="Open a feedback box to guide the next layout iteration"
                        aria-label="Open a feedback box to guide the next layout iteration"
                        style={showFeedback ? { borderColor: 'var(--af-accent-primary)', color: 'var(--af-accent-primary)' } : {}}
                    >
                        <MessageSquare className="w-4 h-4 mr-1 inline" />
                        Feedback
                    </button>

                    <button
                        className="af-btn-secondary"
                        onClick={showFeedback ? handleContinueWithFeedback : () => onContinue()}
                        disabled={isGenerating}
                        title={showFeedback ? "Submit feedback and generate the next layout iteration" : "Generate the next layout iteration from the current canvas"}
                        aria-label={showFeedback ? "Submit feedback and generate the next layout iteration" : "Generate the next layout iteration from the current canvas"}
                        style={{ opacity: isGenerating ? 0.5 : 1 }}
                    >
                        {isGenerating ? (
                            <>
                                <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin mr-1 inline-block" />
                                Processing
                            </>
                        ) : (
                            <>
                                <Play className="w-4 h-4 mr-1 inline" />
                                Continue
                            </>
                        )}
                    </button>

                    <button
                        className="af-btn-primary"
                        onClick={onFinalize}
                        disabled={isGenerating}
                        title="Finalize the current layout and open the beautification workflow"
                        aria-label="Finalize the current layout and open the beautification workflow"
                        style={{ opacity: isGenerating ? 0.5 : 1 }}
                    >
                        <Sparkles className="w-4 h-4 mr-1 inline" />
                        Polish
                    </button>

                    {/* Generate Image Button */}
                    <button
                        className="af-icon-btn af-gen-trigger-btn"
                        onClick={() => setMode('generation')}
                        title="Switch to prompt-based image generation and insert the result into the canvas"
                        aria-label="Switch to prompt-based image generation and insert the result into the canvas"
                        style={{
                            width: '40px',
                            height: '40px',
                            background: 'var(--af-bg-glass)',
                            border: '1px solid var(--af-border-primary)',
                        }}
                    >
                        <Image className="w-5 h-5" />
                    </button>
                </div>
            </div>

            {/* Feedback Panel (appears above controls when active) */}
            {showFeedback && (
                <div
                    className="absolute bottom-28 left-1/2 transform -translate-x-1/2 w-96 max-w-[calc(100%-32px)]"
                    style={{
                        background: 'var(--af-bg-elevated)',
                        backdropFilter: 'blur(12px)',
                        padding: '16px',
                        borderRadius: '16px',
                        border: '1px solid var(--af-border-primary)',
                        boxShadow: 'var(--af-shadow-lg)',
                        zIndex: 16,
                    }}
                >
                    <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-2">
                            <MessageSquare className="w-4 h-4" style={{ color: 'var(--af-accent-primary)' }} />
                            <span className="font-medium" style={{ color: 'var(--af-text-primary)' }}>Add Feedback</span>
                        </div>
                        <button
                            className="af-icon-btn"
                            onClick={() => setShowFeedback(false)}
                            style={{ width: '28px', height: '28px' }}
                        >
                            <X className="w-4 h-4" />
                        </button>
                    </div>

                    <textarea
                        value={feedback}
                        onChange={e => setFeedback(e.target.value)}
                        placeholder="Describe what should be improved..."
                        className="af-input"
                        style={{
                            width: '100%',
                            minHeight: '80px',
                            resize: 'vertical',
                            marginBottom: '12px',
                        }}
                    />

                    <div className="flex items-center gap-3">
                        <label className="text-xs" style={{ color: 'var(--af-text-tertiary)' }}>
                            Your Score (optional):
                        </label>
                        <input
                            type="number"
                            min="0"
                            max="10"
                            step="0.5"
                            value={score || ""}
                            onChange={e => setScore(e.target.value ? Number(e.target.value) : undefined)}
                            placeholder="0-10"
                            className="af-input"
                            style={{ width: '80px' }}
                        />
                        <div className="flex-1" />
                        <button
                            className="af-btn-primary"
                            onClick={handleContinueWithFeedback}
                            disabled={isGenerating}
                        >
                            Submit & Continue
                        </button>
                    </div>
                </div>
            )}
        </>
    )
}
