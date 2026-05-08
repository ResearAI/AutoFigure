"use client"

import { useState } from "react"
import {
    X,
    Wand2,
    Image,
    FileText,
    Palette,
    Layers,
    Key,
    Bot,
    Sparkles,
} from "lucide-react"
import { useAutoFigure } from "@/contexts/autofigure-context"
import { type ApiProtocol, type EnhancementMode, type LLMProvider, LLM_PROVIDERS } from "@/lib/autofigure-types"

interface BeautificationDialogProps {
    isOpen: boolean
    onClose: () => void
    onStart: () => void
    previewImage?: string
}

export default function BeautificationDialog({
    isOpen,
    onClose,
    onStart,
    previewImage,
}: BeautificationDialogProps) {
    const { config, updateConfig, isGenerating } = useAutoFigure()
    const [selectedMode, setSelectedMode] = useState<EnhancementMode>(config.enhancementMode)

    if (!isOpen) return null

    const handleModeChange = (mode: EnhancementMode) => {
        setSelectedMode(mode)
        updateConfig({ enhancementMode: mode })
    }

    const handleStart = () => {
        onStart()
    }

    const canStart = config.artStyle.trim() &&
                     config.imageGenApiKey.trim() &&
                     (selectedMode === 'none' || config.enhancementLlmApiKey.trim())
    const protocolOptions: { value: ApiProtocol; label: string }[] = [
        { value: "openai-compatible", label: "OpenAI Compatible" },
        { value: "gemini-native", label: "Gemini Native" },
    ]

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
            {/* Backdrop */}
            <div
                className="absolute inset-0 backdrop-blur-sm"
                style={{ background: 'rgba(15, 23, 42, 0.4)' }}
                onClick={onClose}
            />

            {/* Dialog */}
            <div
                className="relative w-full max-w-3xl mx-4 rounded-2xl shadow-2xl overflow-hidden max-h-[90vh] overflow-y-auto"
                style={{
                    background: 'var(--af-bg-elevated)',
                    border: '1px solid var(--af-border-primary)',
                }}
            >
                {/* Header */}
                <div
                    className="sticky top-0 z-10 flex items-center justify-between px-6 py-4 backdrop-blur-sm"
                    style={{
                        borderBottom: '1px solid var(--af-border-primary)',
                        background: 'linear-gradient(135deg, rgba(14, 165, 233, 0.1) 0%, rgba(56, 189, 248, 0.05) 100%)',
                    }}
                >
                    <div className="flex items-center gap-3">
                        <div
                            className="p-2 rounded-lg"
                            style={{
                                background: 'linear-gradient(135deg, var(--af-accent-primary) 0%, var(--af-accent-secondary) 100%)',
                                boxShadow: 'var(--af-shadow-button)',
                            }}
                        >
                            <Wand2 className="h-5 w-5 text-white" />
                        </div>
                        <div>
                            <h2 className="text-lg font-semibold" style={{ color: 'var(--af-text-primary)' }}>
                                Beautification Options
                            </h2>
                            <p className="text-sm" style={{ color: 'var(--af-text-tertiary)' }}>
                                Configure enhancement settings and API keys
                            </p>
                        </div>
                    </div>
                    <button
                        onClick={onClose}
                        className="af-icon-btn"
                        style={{ width: '36px', height: '36px' }}
                    >
                        <X className="h-5 w-5" />
                    </button>
                </div>

                {/* Content */}
                <div className="p-6 space-y-6">
                    {/* Preview */}
                    {previewImage && (
                        <div
                            className="aspect-video rounded-xl overflow-hidden"
                            style={{
                                background: 'var(--af-bg-tertiary)',
                                border: '1px solid var(--af-border-primary)',
                            }}
                        >
                            <img
                                src={previewImage}
                                alt="Figure Preview"
                                className="w-full h-full object-contain"
                            />
                        </div>
                    )}

                    {/* Enhancement Mode */}
                    <div>
                        <label className="block text-sm font-medium mb-3" style={{ color: 'var(--af-text-primary)' }}>
                            Enhancement Mode
                        </label>
                        <div className="grid grid-cols-2 gap-3">
                            {/* None Mode */}
                            <button
                                onClick={() => handleModeChange("none")}
                                className="p-4 rounded-xl border-2 transition-all text-left"
                                style={{
                                    borderColor: selectedMode === "none" ? 'var(--af-accent-primary)' : 'var(--af-border-primary)',
                                    background: selectedMode === "none" ? 'rgba(14, 165, 233, 0.1)' : 'var(--af-bg-glass)',
                                }}
                            >
                                <div className="flex items-center gap-3 mb-2">
                                    <div
                                        className="p-2 rounded-lg"
                                        style={{
                                            background: selectedMode === "none" ? 'rgba(14, 165, 233, 0.2)' : 'var(--af-bg-tertiary)',
                                            color: selectedMode === "none" ? 'var(--af-accent-primary)' : 'var(--af-text-tertiary)',
                                        }}
                                    >
                                        <Image className="h-5 w-5" />
                                    </div>
                                    <span
                                        className="font-medium"
                                        style={{ color: selectedMode === "none" ? 'var(--af-accent-primary)' : 'var(--af-text-primary)' }}
                                    >
                                        Direct Beautification
                                    </span>
                                </div>
                                <p className="text-xs" style={{ color: 'var(--af-text-muted)' }}>
                                    Apply art style directly to the layout (requires only Image Gen API)
                                </p>
                            </button>

                            {/* Code2Prompt Mode */}
                            <button
                                onClick={() => handleModeChange("code2prompt")}
                                className="p-4 rounded-xl border-2 transition-all text-left"
                                style={{
                                    borderColor: selectedMode === "code2prompt" ? 'var(--af-accent-primary)' : 'var(--af-border-primary)',
                                    background: selectedMode === "code2prompt" ? 'rgba(14, 165, 233, 0.1)' : 'var(--af-bg-glass)',
                                }}
                            >
                                <div className="flex items-center gap-3 mb-2">
                                    <div
                                        className="p-2 rounded-lg"
                                        style={{
                                            background: selectedMode === "code2prompt" ? 'rgba(14, 165, 233, 0.2)' : 'var(--af-bg-tertiary)',
                                            color: selectedMode === "code2prompt" ? 'var(--af-accent-primary)' : 'var(--af-text-tertiary)',
                                        }}
                                    >
                                        <FileText className="h-5 w-5" />
                                    </div>
                                    <span
                                        className="font-medium"
                                        style={{ color: selectedMode === "code2prompt" ? 'var(--af-accent-primary)' : 'var(--af-text-primary)' }}
                                    >
                                        Code2Prompt (Recommended)
                                    </span>
                                </div>
                                <p className="text-xs" style={{ color: 'var(--af-text-muted)' }}>
                                    Use LLM to analyze code and generate prompt (requires both LLM and Image Gen APIs)
                                </p>
                            </button>
                        </div>
                    </div>

                    {/* Image Generation API Config (Required) */}
                    <div
                        className="p-4 rounded-xl"
                        style={{
                            background: 'var(--af-bg-glass)',
                            border: '1px solid var(--af-border-primary)',
                        }}
                    >
                        <div className="flex items-center gap-2 mb-4">
                            <Key className="h-4 w-4" style={{ color: 'var(--af-accent-primary)' }} />
                            <span className="text-sm font-medium" style={{ color: 'var(--af-text-primary)' }}>
                                Image Generation API (Required)
                            </span>
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div className="af-form-group">
                                <label className="af-label">Provider</label>
                                <select
                                    value={config.imageGenProvider || 'bianxie'}
                                    onChange={e => {
                                        const provider = e.target.value as LLMProvider
                                        updateConfig({
                                            imageGenProvider: provider,
                                            imageGenProtocol: LLM_PROVIDERS[provider].defaultProtocol,
                                            imageGenBaseUrl: LLM_PROVIDERS[provider].defaultBaseUrl,
                                        })
                                    }}
                                    className="af-input"
                                >
                                    {Object.entries(LLM_PROVIDERS).map(([key, value]) => (
                                        <option key={key} value={key}>
                                            {value.name}
                                        </option>
                                    ))}
                                </select>
                            </div>
                            <div className="af-form-group">
                                <label className="af-label">Protocol</label>
                                <select
                                    value={config.imageGenProtocol}
                                    onChange={e => updateConfig({ imageGenProtocol: e.target.value as ApiProtocol })}
                                    className="af-input"
                                >
                                    {protocolOptions.map(option => (
                                        <option key={option.value} value={option.value}>
                                            {option.label}
                                        </option>
                                    ))}
                                </select>
                            </div>
                            <div className="af-form-group">
                                <label className="af-label">API Key *</label>
                                <input
                                    type="password"
                                    value={config.imageGenApiKey}
                                    onChange={e => updateConfig({ imageGenApiKey: e.target.value })}
                                    placeholder="Enter your API key"
                                    className="af-input"
                                    autoComplete="new-password"
                                    autoCorrect="off"
                                    autoCapitalize="off"
                                    spellCheck={false}
                                    data-lpignore="true"
                                    data-form-type="other"
                                    data-1p-ignore="true"
                                    name={`beautify-imggen-credential-${Date.now()}`}
                                />
                            </div>
                            <div className="af-form-group">
                                <label className="af-label">Model</label>
                                <input
                                    type="text"
                                    value={config.imageGenModel}
                                    onChange={e => updateConfig({ imageGenModel: e.target.value })}
                                    placeholder={config.imageGenProvider === 'openrouter'
                                        ? 'e.g., google/gemini-3.1-flash-image-preview'
                                        : config.imageGenProvider === 'gemini'
                                        ? 'e.g., gemini-3.1-flash-image-preview'
                                        : 'e.g., gemini-3.1-flash-image-preview'}
                                    className="af-input"
                                />
                            </div>
                            <div className="af-form-group">
                                <label className="af-label">Base URL</label>
                                <input
                                    type="text"
                                    value={config.imageGenBaseUrl}
                                    onChange={e => updateConfig({ imageGenBaseUrl: e.target.value })}
                                    placeholder={config.imageGenProvider === 'openrouter'
                                        ? 'https://openrouter.ai/api/v1'
                                        : config.imageGenProvider === 'gemini'
                                        ? 'https://generativelanguage.googleapis.com/v1beta'
                                        : 'https://api.bianxie.ai/v1/chat/completions'}
                                    className="af-input"
                                />
                            </div>
                        </div>
                    </div>

                    {/* Code2Prompt LLM Config (Required for code2prompt mode) */}
                    {selectedMode === "code2prompt" && (
                        <div
                            className="p-4 rounded-xl"
                            style={{
                                background: 'var(--af-bg-glass)',
                                border: '1px solid var(--af-border-primary)',
                            }}
                        >
                            <div className="flex items-center gap-2 mb-4">
                                <Bot className="h-4 w-4" style={{ color: 'var(--af-accent-primary)' }} />
                                <span className="text-sm font-medium" style={{ color: 'var(--af-text-primary)' }}>
                                    Code2Prompt LLM API (Required for this mode)
                                </span>
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <div className="af-form-group">
                                    <label className="af-label">Provider</label>
                                    <select
                                        value={config.enhancementLlmProvider || 'bianxie'}
                                        onChange={e => {
                                            const provider = e.target.value as LLMProvider
                                            updateConfig({
                                                enhancementLlmProvider: provider,
                                                enhancementLlmProtocol: LLM_PROVIDERS[provider].defaultProtocol,
                                                enhancementLlmBaseUrl: config.enhancementLlmBaseUrl || LLM_PROVIDERS[provider].defaultBaseUrl,
                                            })
                                        }}
                                        className="af-input"
                                    >
                                        {Object.entries(LLM_PROVIDERS).map(([key, value]) => (
                                            <option key={key} value={key}>
                                                {value.name}
                                            </option>
                                        ))}
                                    </select>
                                </div>
                                <div className="af-form-group">
                                    <label className="af-label">Protocol</label>
                                    <select
                                        value={config.enhancementLlmProtocol}
                                        onChange={e => updateConfig({ enhancementLlmProtocol: e.target.value as ApiProtocol })}
                                        className="af-input"
                                    >
                                        {protocolOptions.map(option => (
                                            <option key={option.value} value={option.value}>
                                                {option.label}
                                            </option>
                                        ))}
                                    </select>
                                </div>
                                <div className="af-form-group">
                                    <label className="af-label">API Key *</label>
                                    <input
                                        type="password"
                                        value={config.enhancementLlmApiKey}
                                        onChange={e => updateConfig({ enhancementLlmApiKey: e.target.value })}
                                        placeholder="Enter your API key"
                                        className="af-input"
                                        autoComplete="new-password"
                                        autoCorrect="off"
                                        autoCapitalize="off"
                                        spellCheck={false}
                                        data-lpignore="true"
                                        data-form-type="other"
                                        data-1p-ignore="true"
                                        name={`beautify-llm-credential-${Date.now()}`}
                                    />
                                </div>
                                <div className="af-form-group">
                                    <label className="af-label">Model</label>
                                    <input
                                        type="text"
                                        value={config.enhancementLlmModel}
                                        onChange={e => updateConfig({ enhancementLlmModel: e.target.value })}
                                        placeholder={config.enhancementLlmProvider === 'openrouter'
                                            ? 'e.g., google/gemini-3.1-pro-preview'
                                            : config.enhancementLlmProvider === 'gemini'
                                            ? 'e.g., gemini-3.1-pro-preview'
                                            : 'e.g., gemini-3.1-pro-preview'}
                                        className="af-input"
                                    />
                                </div>
                                <div className="af-form-group">
                                    <label className="af-label">Base URL (optional)</label>
                                    <input
                                        type="text"
                                        value={config.enhancementLlmBaseUrl}
                                        onChange={e => updateConfig({ enhancementLlmBaseUrl: e.target.value })}
                                        placeholder={config.enhancementLlmProvider === 'openrouter'
                                            ? 'https://openrouter.ai/api/v1'
                                            : config.enhancementLlmProvider === 'gemini'
                                            ? 'https://generativelanguage.googleapis.com/v1beta'
                                            : 'https://api.bianxie.ai/v1'}
                                        className="af-input"
                                    />
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Art Style - Fully Customizable */}
                    <div>
                        <label className="block text-sm font-medium mb-2" style={{ color: 'var(--af-text-primary)' }}>
                            <div className="flex items-center gap-2">
                                <Palette className="h-4 w-4" style={{ color: 'var(--af-accent-primary)' }} />
                                Art Style Description *
                            </div>
                        </label>
                        <textarea
                            value={config.artStyle}
                            onChange={e => updateConfig({ artStyle: e.target.value })}
                            placeholder=""
                            className="af-input"
                            style={{ minHeight: '100px', resize: 'vertical', width: '100%' }}
                        />
                    </div>

                    {/* Variant Count */}
                    <div>
                        <label className="block text-sm font-medium mb-3" style={{ color: 'var(--af-text-primary)' }}>
                            <div className="flex items-center gap-2">
                                <Layers className="h-4 w-4" style={{ color: 'var(--af-accent-primary)' }} />
                                Number of Variants
                            </div>
                        </label>
                        <div className="flex items-center gap-3">
                            <input
                                type="number"
                                min="1"
                                value={config.enhancementCount}
                                onChange={e => {
                                    const val = parseInt(e.target.value, 10)
                                    if (!isNaN(val) && val >= 1) {
                                        updateConfig({ enhancementCount: val })
                                    }
                                }}
                                className="af-input w-20 text-center"
                            />
                            <div className="flex gap-1">
                                {[1, 3, 5, 10].map(n => (
                                    <button
                                        key={n}
                                        onClick={() => updateConfig({ enhancementCount: n })}
                                        className="px-3 h-8 rounded-lg text-sm font-medium transition-all"
                                        style={{
                                            background: config.enhancementCount === n
                                                ? 'linear-gradient(135deg, var(--af-accent-primary) 0%, var(--af-accent-secondary) 100%)'
                                                : 'var(--af-bg-glass)',
                                            color: config.enhancementCount === n ? 'white' : 'var(--af-text-secondary)',
                                            border: config.enhancementCount === n ? 'none' : '1px solid var(--af-border-primary)',
                                        }}
                                    >
                                        {n}
                                    </button>
                                ))}
                            </div>
                        </div>
                    </div>

                    {/* Validation Warning */}
                    {!canStart && (
                        <div
                            className="p-3 rounded-lg text-sm"
                            style={{
                                background: 'rgba(234, 179, 8, 0.1)',
                                border: '1px solid rgba(234, 179, 8, 0.3)',
                                color: '#ca8a04',
                            }}
                        >
                            Please fill in all required API keys (*) to start beautification.
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div
                    className="sticky bottom-0 flex items-center justify-end gap-3 px-6 py-4 backdrop-blur-sm"
                    style={{
                        borderTop: '1px solid var(--af-border-primary)',
                        background: 'var(--af-bg-elevated)',
                    }}
                >
                    <button
                        onClick={onClose}
                        className="af-btn-secondary"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={handleStart}
                        disabled={isGenerating || !canStart}
                        className="af-btn-primary flex items-center gap-2 px-6"
                        style={{ opacity: (isGenerating || !canStart) ? 0.5 : 1 }}
                    >
                        {isGenerating ? (
                            <>
                                <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                                Processing...
                            </>
                        ) : (
                            <>
                                <Sparkles className="h-5 w-5" />
                                Start Beautification
                            </>
                        )}
                    </button>
                </div>
            </div>
        </div>
    )
}
